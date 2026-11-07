"""
TikTok Events API v1.3 Service for Tgsims.
Sends server-side conversion events to https://business-api.tiktok.com/open_api/v1.3/event/track/
Supports:
  - ViewContent
  - AddToWishlist
  - Search
  - AddPaymentInfo
  - AddToCart
  - InitiateCheckout
  - PlaceAnOrder
  - CompleteRegistration
  - Purchase
"""
import hashlib
import os
import threading
import time
import uuid
import requests
from flask import has_request_context, request, session
from app.config import Config


class TikTokService:
    """TikTok Events API v1.3 integration."""

    API_URL = 'https://business-api.tiktok.com/open_api/v1.3/event/track/'

    SUPPORTED_EVENTS = {
        'ViewContent',
        'AddToWishlist',
        'Search',
        'AddPaymentInfo',
        'AddToCart',
        'InitiateCheckout',
        'PlaceAnOrder',
        'CompleteRegistration',
        'Purchase',
    }

    @classmethod
    def get_pixel_id(cls) -> str:
        return (os.getenv('TIKTOK_PIXEL_ID') or getattr(Config, 'TIKTOK_PIXEL_ID', '') or '').strip()

    @classmethod
    def get_access_token(cls) -> str:
        return (os.getenv('TIKTOK_ACCESS_TOKEN') or getattr(Config, 'TIKTOK_ACCESS_TOKEN', '') or '').strip()

    @staticmethod
    def sha256_hash(value: str) -> str:
        """Normalizes and hashes PII (email, phone, external_id) with SHA-256 as required by TikTok."""
        if not value:
            return ''
        cleaned = str(value).strip().lower()
        if not cleaned:
            return ''
        return hashlib.sha256(cleaned.encode('utf-8')).hexdigest()

    @classmethod
    def normalize_phone(cls, phone: str) -> str:
        """Normalizes phone number to E.164 format before hashing."""
        if not phone:
            return ''
        digits = ''.join(ch for ch in str(phone) if ch.isdigit() or ch == '+')
        if not digits:
            return ''
        if digits.startswith('0') and len(digits) == 11:
            digits = '+234' + digits[1:]
        elif not digits.startswith('+'):
            digits = '+' + digits
        return digits

    @classmethod
    def _extract_request_context(cls) -> dict:
        """Extracts client IP, User-Agent, URL, referrer, ttp, ttclid, and session user when inside a Flask request."""
        ctx = {
            'ip': '',
            'user_agent': '',
            'url': 'https://tgsims.com/',
            'referrer': '',
            'ttp': '',
            'ttclid': '',
            'email': '',
            'phone': '',
            'external_id': '',
        }
        if not has_request_context():
            return ctx

        try:
            forwarded = request.headers.get('X-Forwarded-For', '')
            ctx['ip'] = (forwarded.split(',')[0].strip() if forwarded else request.remote_addr) or ''
            ctx['user_agent'] = request.headers.get('User-Agent', '') or ''
            ctx['url'] = request.url or 'https://tgsims.com/'
            ctx['referrer'] = request.referrer or ''
            ctx['ttp'] = request.cookies.get('_ttp', '') or ''
            ctx['ttclid'] = (
                request.args.get('ttclid')
                or request.cookies.get('ttclid')
                or request.cookies.get('_ttclid')
                or ''
            )
            user = session.get('user') or {}
            if isinstance(user, dict):
                ctx['external_id'] = str(user.get('id') or '')
                ctx['email'] = str(user.get('email') or '')
                ctx['phone'] = str(user.get('phone_number') or user.get('phone') or '')
        except Exception:
            pass
        return ctx

    @classmethod
    def build_event_payload(
        cls,
        event_name: str,
        event_id: str = None,
        value: float = None,
        currency: str = 'USD',
        content_id: str = 'tgsims_virtual_number',
        content_type: str = 'product',
        content_name: str = 'Tgsims Virtual Number',
        query: str = None,
        url: str = None,
        email: str = None,
        phone_number: str = None,
        external_id: str = None,
        ip: str = None,
        user_agent: str = None,
        ttp: str = None,
        ttclid: str = None,
    ) -> dict:
        """Builds a TikTok Events API v1.3 compliant payload."""
        ctx = cls._extract_request_context()

        raw_email = email if email is not None else ctx['email']
        raw_phone = phone_number if phone_number is not None else ctx['phone']
        raw_ext_id = external_id if external_id is not None else ctx['external_id']

        user_obj = {}
        if raw_email:
            user_obj['email'] = cls.sha256_hash(raw_email)
        if raw_phone:
            norm_phone = cls.normalize_phone(raw_phone)
            if norm_phone:
                user_obj['phone'] = cls.sha256_hash(norm_phone)
        if raw_ext_id:
            user_obj['external_id'] = cls.sha256_hash(raw_ext_id)

        client_ip = ip if ip is not None else ctx['ip']
        client_ua = user_agent if user_agent is not None else ctx['user_agent']
        client_ttp = ttp if ttp is not None else ctx['ttp']
        client_ttclid = ttclid if ttclid is not None else ctx['ttclid']

        if client_ip:
            user_obj['ip'] = client_ip
        if client_ua:
            user_obj['user_agent'] = client_ua
        if client_ttp:
            user_obj['ttp'] = client_ttp
        if client_ttclid:
            user_obj['ttclid'] = client_ttclid

        content_item = {
            'content_id': str(content_id or 'tgsims_virtual_number'),
            'content_type': str(content_type or 'product'),
            'content_name': str(content_name or 'Tgsims Virtual Number'),
        }

        properties = {
            'content_type': str(content_type or 'product'),
            'contents': [content_item],
        }
        if value is not None:
            try:
                properties['value'] = round(float(value), 2)
                content_item['price'] = round(float(value), 2)
            except (ValueError, TypeError):
                pass
        if currency:
            properties['currency'] = str(currency).upper()
        if query:
            properties['query'] = str(query)

        page_obj = {
            'url': url or ctx['url'] or 'https://tgsims.com/',
        }
        if ctx.get('referrer'):
            page_obj['referrer'] = ctx['referrer']

        return {
            'event_source': 'web',
            'event_source_id': cls.get_pixel_id(),
            'data': [
                {
                    'event': event_name,
                    'event_time': int(time.time()),
                    'event_id': str(event_id or uuid.uuid4()),
                    'user': user_obj,
                    'properties': properties,
                    'page': page_obj,
                }
            ],
        }

    @classmethod
    def _send_payload(cls, payload: dict) -> dict:
        token = cls.get_access_token()
        if not token:
            return {'success': False, 'message': 'Missing TIKTOK_ACCESS_TOKEN'}
        headers = {
            'Access-Token': token,
            'Content-Type': 'application/json',
        }
        try:
            resp = requests.post(cls.API_URL, headers=headers, json=payload, timeout=10)
            data = resp.json()
            ok = resp.status_code == 200 and data.get('code') == 0
            return {
                'success': ok,
                'status_code': resp.status_code,
                'response': data,
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}

    @classmethod
    def track_event(cls, event_name: str, async_send: bool = True, **kwargs) -> dict:
        """
        Builds and sends an event to TikTok Events API.
        By default runs asynchronously on a background thread so web requests never block.
        Note: on serverless platforms (Vercel), synchronous execution (or fast timeout) ensures delivery before lambda freeze.
        """
        if not cls.get_access_token() or not cls.get_pixel_id():
            return {'success': False, 'message': 'TikTok Events API not configured'}

        payload = cls.build_event_payload(event_name=event_name, **kwargs)

        # On Vercel serverless functions, background threads may be frozen right after response returns.
        # Use a short synchronous request on Vercel or when async_send=False.
        is_vercel = bool(os.getenv('VERCEL'))
        if not async_send or is_vercel:
            return cls._send_payload(payload)

        t = threading.Thread(target=cls._send_payload, args=(payload,), daemon=True)
        t.start()
        return {'success': True, 'queued': True, 'event_id': payload['data'][0]['event_id']}
