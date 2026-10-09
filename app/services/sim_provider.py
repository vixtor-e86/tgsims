"""Virtual SIM Provider Adapter for Tgsims.
Integrates VirtualSMS.io API with transparent retail markups, slug mapping, error translation,
and complete white-labeling (no third-party provider names disclosed to end users).
"""

import os
import re
import requests
import uuid
import datetime
from typing import Optional, Dict, Any, List
from app.config import Config
from app.services.supabase_client import get_supabase_admin, mock_db


class SMSCodeClient:
    """Low-level HTTP client for SMSCode.gg REST API (v2 USD)."""

    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = (
            api_key
            or getattr(Config, 'SMSCODE_API_KEY', '')
            or os.getenv('SMSCODE_API_KEY', '')
            or getattr(Config, 'SIM_PROVIDER_API_KEY', '')
            or os.getenv('SIM_PROVIDER_API_KEY', '')
        ).strip()
        self.base_url = (
            base_url
            or getattr(Config, 'SMSCODE_BASE_URL', 'https://api.smscode.gg/v2')
            or os.getenv('SMSCODE_BASE_URL', 'https://api.smscode.gg/v2')
        ).strip().rstrip('/')
        self._cached_countries = None
        self._cached_services = None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 20)

    def _headers(self) -> dict:
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

    def get_profile(self) -> dict:
        """Fetch account balance and status."""
        return self.get_balance()

    def get_balance(self) -> dict:
        """Fetch account balance (denominated in USD from v2 API)."""
        if not self.is_configured:
            return {'success': False, 'balance': 0.0, 'message': 'API key not configured'}
        try:
            r = requests.get(f"{self.base_url}/balance", headers=self._headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                bal_obj = data.get('data', {}).get('balance', {})
                bal = float(bal_obj.get('amount') if bal_obj.get('amount') is not None else 0.0)
                return {
                    'success': True,
                    'balance': round(bal, 2),
                    'currency': 'USD',
                    'usd_estimate': round(bal, 2),
                    'raw': data
                }
            return {'success': False, 'balance': 0.0, 'message': r.text, 'status_code': r.status_code}
        except Exception as e:
            return {'success': False, 'balance': 0.0, 'message': str(e)}

    def get_countries(self) -> list:
        """Fetch all supported countries."""
        if self._cached_countries:
            return self._cached_countries
        try:
            r = requests.get(f"{self.base_url}/catalog/countries", headers=self._headers(), timeout=15)
            if r.status_code == 200:
                data = r.json().get('data', [])
                self._cached_countries = data
                return data
            return []
        except Exception as e:
            print(f"[SMSCodeClient] get_countries error: {e}")
            return []

    def get_services(self) -> list:
        """Fetch all supported services."""
        if self._cached_services:
            return self._cached_services
        try:
            r = requests.get(f"{self.base_url}/catalog/services", headers=self._headers(), timeout=15)
            if r.status_code == 200:
                data = r.json().get('data', [])
                self._cached_services = data
                return data
            return []
        except Exception as e:
            print(f"[SMSCodeClient] get_services error: {e}")
            return []

    def get_operators(self, country_id: int, platform_id: int) -> list:
        """Fetch operators for a specific country and service. Excludes 'any'."""
        try:
            url = f"{self.base_url}/catalog/operators?country_id={country_id}&platform_id={platform_id}"
            r = requests.get(url, headers=self._headers(), timeout=10)
            if r.status_code == 200:
                ops = r.json().get('data', [])
                return [op for op in ops if op.get('code') != 'any' and op.get('operator_id') is not None]
            return []
        except Exception as e:
            print(f"[SMSCodeClient] get_operators error: {e}")
            return []

    def get_products(self, country_id: int, platform_id: int, operator_id: int = None, limit: int = 50) -> list:
        """Fetch available product tiers for a country + service."""
        try:
            url = f"{self.base_url}/catalog/products?country_id={country_id}&platform_id={platform_id}&limit={limit}"
            if operator_id is not None:
                url += f"&operator_id={operator_id}"
            r = requests.get(url, headers=self._headers(), timeout=10)
            if r.status_code == 200:
                return r.json().get('data', [])
            return []
        except Exception as e:
            print(f"[SMSCodeClient] get_products error: {e}")
            return []

    def get_country_id(self, code_or_slug: str) -> int:
        c_str = str(code_or_slug or '').strip().upper()
        common = {'US': 188, 'USA': 188, 'GB': 17, 'UK': 17, 'NG': 20, 'IN': 23, 'ID': 7, 'CA': 1, 'DE': 44, 'FR': 43}
        if c_str in common:
            return common[c_str]
        countries = self.get_countries()
        for c in countries:
            if c.get('code', '').upper() == c_str or c.get('name', '').lower() == c_str.lower():
                return c['id']
        return 188

    def get_platform_id(self, service_code: str) -> int:
        s_clean = str(service_code or '').strip().lower()
        if s_clean.isdigit():
            return int(s_clean)
        core_map = {
            'whatsapp': 1, 'wa': 1, 'wa_biz': 1, 'whatsapp business': 1,
            'telegram': 2, 'tg': 2,
            'google': 5, 'gmail': 5, 'youtube': 5, 'go': 5, 'google-youtube-gmail': 5,
            'instagram': 3, 'ig': 3, 'threads': 3, 'instagram-threads': 3,
            'twitter': 6, 'tw': 6, 'x': 6, 'twitter-x': 6,
            'facebook': 4, 'fb': 4, 'meta': 4,
            'openai': 20, 'chatgpt': 20, 'dr': 20, 'openai-chatgpt': 20,
            'tiktok': 7, 'tiktok-douyin': 7, 'douyin': 7, 'lf': 7,
            'discord': 8, 'ds': 8,
            'apple': 12, 'icloud': 12, 'wx': 12, 'apple-icloud': 12,
            'paypal': 10, 'netflix': 15, 'uber': 18, 'snapchat': 13,
            'tinder': 9, 'microsoft': 11, 'amazon': 14
        }
        if s_clean in core_map:
            return core_map[s_clean]
        services = self.get_services()
        # 1. Exact match on code or name
        for s in services:
            if s.get('code', '').lower() == s_clean or s.get('name', '').lower() == s_clean:
                return s['id']
        # 2. Match without hyphens or spaces
        clean_norm = s_clean.replace('-', '').replace(' ', '')
        for s in services:
            s_norm = s.get('code', '').lower().replace('-', '').replace(' ', '')
            n_norm = s.get('name', '').lower().replace('-', '').replace(' ', '')
            if s_norm == clean_norm or n_norm == clean_norm:
                return s['id']
        # 3. Substring match
        for s in services:
            if s_clean in s.get('code', '').lower() or s_clean in s.get('name', '').lower():
                return s['id']
        return 1

    def create_order(
        self,
        catalog_product_id: int = None,
        product_id: int = None,
        operator_id: int = None,
        max_price: str = None,
        prefer_provider: str = None,
        policy: str = 'cheapest'
    ) -> dict:
        """Create a new number order using SMSCode v2 API."""
        if not self.is_configured:
            return {'success': False, 'message': 'API key not configured'}

        headers = self._headers()
        headers['Idempotency-Key'] = str(uuid.uuid4())

        payload = {'quantity': 1}
        if product_id is not None:
            payload['product_id'] = int(product_id)
        elif catalog_product_id is not None:
            payload['catalog_product_id'] = int(catalog_product_id)
            payload['policy'] = policy or 'cheapest'
            if operator_id is not None:
                payload['operator_id'] = int(operator_id)
            if max_price:
                payload['max_price'] = str(max_price)
            if prefer_provider:
                payload['prefer_provider'] = str(prefer_provider)
        else:
            return {'success': False, 'message': 'catalog_product_id or product_id is required'}

        try:
            url = f"{self.base_url}/orders/create"
            r = requests.post(url, headers=headers, json=payload, timeout=20)
            if r.status_code in (200, 201):
                res_data = r.json().get('data', {})
                orders = res_data.get('orders', [])
                if orders:
                    ord0 = orders[0]
                    phone = ord0.get('phone_number', '')
                    order_id = str(ord0.get('id', ''))
                    cost = float(ord0.get('amount', {}).get('amount') or 0.0)
                    expires = ord0.get('expires_at')
                    op_name = ord0.get('operator_name')
                    return {
                        'success': True,
                        'provider_order_id': order_id,
                        'phone_number': phone,
                        'operator': op_name or 'standard',
                        'operator_id': ord0.get('operator_id'),
                        'provider_cost': cost,
                        'expires_at': expires,
                        'raw': ord0
                    }
                return {'success': False, 'message': 'No number allocated in order response'}

            err_data = {}
            try:
                err_data = r.json()
            except Exception:
                pass
            raw_msg = err_data.get('message') or err_data.get('error') or r.text
            err_lower = str(raw_msg).lower()
            if 'stock' in err_lower or 'no available' in err_lower or 'not found' in err_lower or r.status_code == 404:
                msg = 'No numbers currently available on this operator route. Please try another operator or check back shortly.'
            elif 'balance' in err_lower or r.status_code == 402:
                msg = 'System inventory temporarily replenishing balance. Please try again shortly.'
            else:
                msg = f"Allocation temporarily unavailable ({raw_msg}). Please try another operator."

            return {'success': False, 'message': msg, 'raw_error': raw_msg, 'status_code': r.status_code}
        except Exception as e:
            return {'success': False, 'message': f"Connection error: {e}"}

    def buy_activation(
        self,
        country_code: str = 'US',
        service_code: str = 'whatsapp',
        operator: str = None,
        operator_id: int = None,
        catalog_product_id: int = None,
        product_id: int = None,
        **kwargs
    ) -> dict:
        """Unified method for number allocation."""
        if not self.is_configured:
            return {'success': False, 'message': 'Provider client not configured'}

        cid = self.get_country_id(country_code)
        pid = self.get_platform_id(service_code)

        # If product_id or catalog_product_id not provided, find cheapest catalog_product_id
        if not product_id and not catalog_product_id:
            products = self.get_products(cid, pid, operator_id=operator_id, limit=10)
            if products:
                products.sort(key=lambda p: float(p.get('price', {}).get('amount', 999)))
                cheapest = products[0]
                catalog_product_id = cheapest.get('catalog_product_id')
                if operator_id is None and cheapest.get('operator_id'):
                    operator_id = cheapest.get('operator_id')
            else:
                return {'success': False, 'message': 'No numbers currently available for this service/country.'}

        return self.create_order(
            catalog_product_id=catalog_product_id,
            product_id=product_id,
            operator_id=operator_id,
            policy='cheapest'
        )

    def check_order(self, provider_order_id: str) -> dict:
        """Poll order status and SMS OTP code."""
        if not self.is_configured or not provider_order_id:
            return {'success': False, 'has_sms': False}
        try:
            url = f"{self.base_url}/orders/{provider_order_id}"
            r = requests.get(url, headers=self._headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                order = data.get('data') or {}
                status = str(order.get('status', 'ACTIVE')).upper()
                otp_code = order.get('otp_code')
                otp_text = order.get('otp_message')
                if not otp_code and otp_text:
                    otp_code = self._extract_otp_code(otp_text)
                has_sms = bool(otp_code)
                return {
                    'success': True,
                    'status': status,
                    'has_sms': has_sms,
                    'sms_code': otp_code,
                    'full_sms': otp_text or (f"Your verification code is: {otp_code}" if otp_code else None),
                    'phone_number': order.get('phone_number'),
                    'provider_sms_id': str(order.get('id', provider_order_id))
                }
            return {'success': False, 'has_sms': False, 'message': r.text}
        except Exception as e:
            return {'success': False, 'has_sms': False, 'message': str(e)}

    def cancel_order(self, provider_order_id: str) -> dict:
        """Cancel an order before receiving SMS (triggers instant provider refund)."""
        if not self.is_configured or not provider_order_id:
            return {'success': False, 'message': 'Client not configured'}
        try:
            url = f"{self.base_url}/orders/cancel"
            r = requests.post(url, headers=self._headers(), json={'id': int(provider_order_id)}, timeout=10)
            if r.status_code in (200, 204):
                return {'success': True, 'data': r.json() if r.text else {}}
            return {'success': False, 'message': r.text}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def finish_order(self, provider_order_id: str) -> dict:
        """Finalize order after SMS has been received."""
        if not self.is_configured or not provider_order_id:
            return {'success': True}
        try:
            url = f"{self.base_url}/orders/finish"
            r = requests.post(url, headers=self._headers(), json={'id': int(provider_order_id)}, timeout=10)
            return {'success': r.status_code in (200, 204)}
        except Exception:
            return {'success': True}

    def ban_order(self, provider_order_id: str) -> dict:
        return self.cancel_order(provider_order_id)

    @staticmethod
    def _extract_otp_code(text: str) -> Optional[str]:
        if not text:
            return None
        text_clean = str(text).strip()
        m = re.search(r'(?:code|codice|código|pin|verification\s*code|is)[:\s]+([A-Za-z0-9\-]{4,10})', text_clean, re.I)
        if m:
            c = m.group(1).strip()
            if any(ch.isdigit() for ch in c):
                return c
        m = re.search(r'\b(\d{3}-\d{3})\b', text_clean)
        if m:
            return m.group(1).strip()
        m = re.search(r'\b(\d{4,8})\b', text_clean)
        if m:
            return m.group(1).strip()
        return None


# Backward compatibility aliases
VirtualSMSClient = SMSCodeClient
FiveSimClient = SMSCodeClient


class SIMProviderService:
    """High-level service interface for Tgsims virtual number purchasing and catalog."""

    # ISO Country Code -> Metadata mapping for all VirtualSMS.io supported countries
    COUNTRY_SLUGS = {
        'US': {'slug': 'usa', 'name': 'United States', 'flag': '🇺🇸', 'dial': '+1'},
        'AO': {'slug': 'angola', 'name': 'Angola', 'flag': '🇦🇴', 'dial': '+244'},
        'AR': {'slug': 'argentina', 'name': 'Argentina', 'flag': '🇦🇷', 'dial': '+54'},
        'AT': {'slug': 'austria', 'name': 'Austria', 'flag': '🇦🇹', 'dial': '+43'},
        'BD': {'slug': 'bangladesh', 'name': 'Bangladesh', 'flag': '🇧🇩', 'dial': '+880'},
        'BE': {'slug': 'belgium', 'name': 'Belgium', 'flag': '🇧🇪', 'dial': '+32'},
        'BA': {'slug': 'bosniaandherzegovina', 'name': 'Bosnia and Herzegovina', 'flag': '🇧🇦', 'dial': '+387'},
        'BR': {'slug': 'brazil', 'name': 'Brazil', 'flag': '🇧🇷', 'dial': '+55'},
        'BG': {'slug': 'bulgaria', 'name': 'Bulgaria', 'flag': '🇧🇬', 'dial': '+359'},
        'CM': {'slug': 'cameroon', 'name': 'Cameroon', 'flag': '🇨🇲', 'dial': '+237'},
        'CA': {'slug': 'canada', 'name': 'Canada', 'flag': '🇨🇦', 'dial': '+1'},
        'TD': {'slug': 'chad', 'name': 'Chad', 'flag': '🇹🇩', 'dial': '+235'},
        'CN': {'slug': 'china', 'name': 'China', 'flag': '🇨🇳', 'dial': '+86'},
        'CO': {'slug': 'colombia', 'name': 'Colombia', 'flag': '🇨🇴', 'dial': '+57'},
        'HR': {'slug': 'croatia', 'name': 'Croatia', 'flag': '🇭🇷', 'dial': '+385'},
        'CZ': {'slug': 'czechrepublic', 'name': 'Czech Republic', 'flag': '🇨🇿', 'dial': '+420'},
        'EG': {'slug': 'egypt', 'name': 'Egypt', 'flag': '🇪🇬', 'dial': '+20'},
        'EE': {'slug': 'estonia', 'name': 'Estonia', 'flag': '🇪🇪', 'dial': '+372'},
        'FR': {'slug': 'france', 'name': 'France', 'flag': '🇫🇷', 'dial': '+33'},
        'GE': {'slug': 'georgia', 'name': 'Georgia', 'flag': '🇬🇪', 'dial': '+995'},
        'DE': {'slug': 'germany', 'name': 'Germany', 'flag': '🇩🇪', 'dial': '+49'},
        'GR': {'slug': 'greece', 'name': 'Greece', 'flag': '🇬🇷', 'dial': '+30'},
        'HK': {'slug': 'hongkong', 'name': 'Hong Kong', 'flag': '🇭🇰', 'dial': '+852'},
        'HU': {'slug': 'hungary', 'name': 'Hungary', 'flag': '🇭🇺', 'dial': '+36'},
        'IN': {'slug': 'india', 'name': 'India', 'flag': '🇮🇳', 'dial': '+91'},
        'ID': {'slug': 'indonesia', 'name': 'Indonesia', 'flag': '🇮🇩', 'dial': '+62'},
        'IQ': {'slug': 'iraq', 'name': 'Iraq', 'flag': '🇮🇶', 'dial': '+964'},
        'IE': {'slug': 'ireland', 'name': 'Ireland', 'flag': '🇮🇪', 'dial': '+353'},
        'IL': {'slug': 'israel', 'name': 'Israel', 'flag': '🇮🇱', 'dial': '+972'},
        'IT': {'slug': 'italy', 'name': 'Italy', 'flag': '🇮🇹', 'dial': '+39'},
        'KZ': {'slug': 'kazakhstan', 'name': 'Kazakhstan', 'flag': '🇰🇿', 'dial': '+7'},
        'KE': {'slug': 'kenya', 'name': 'Kenya', 'flag': '🇰🇪', 'dial': '+254'},
        'KG': {'slug': 'kyrgyzstan', 'name': 'Kyrgyzstan', 'flag': '🇰🇬', 'dial': '+996'},
        'LV': {'slug': 'latvia', 'name': 'Latvia', 'flag': '🇱🇻', 'dial': '+371'},
        'LR': {'slug': 'liberia', 'name': 'Liberia', 'flag': '🇱🇷', 'dial': '+231'},
        'LT': {'slug': 'lithuania', 'name': 'Lithuania', 'flag': '🇱🇹', 'dial': '+370'},
        'MY': {'slug': 'malaysia', 'name': 'Malaysia', 'flag': '🇲🇾', 'dial': '+60'},
        'MX': {'slug': 'mexico', 'name': 'Mexico', 'flag': '🇲🇽', 'dial': '+52'},
        'MD': {'slug': 'moldova', 'name': 'Moldova', 'flag': '🇲🇩', 'dial': '+373'},
        'MA': {'slug': 'morocco', 'name': 'Morocco', 'flag': '🇲🇦', 'dial': '+212'},
        'NL': {'slug': 'netherlands', 'name': 'Netherlands', 'flag': '🇳🇱', 'dial': '+31'},
        'NZ': {'slug': 'newzealand', 'name': 'New Zealand', 'flag': '🇳🇿', 'dial': '+64'},
        'NG': {'slug': 'nigeria', 'name': 'Nigeria', 'flag': '🇳🇬', 'dial': '+234'},
        'PE': {'slug': 'peru', 'name': 'Peru', 'flag': '🇵🇪', 'dial': '+51'},
        'PH': {'slug': 'philippines', 'name': 'Philippines', 'flag': '🇵🇭', 'dial': '+63'},
        'PL': {'slug': 'poland', 'name': 'Poland', 'flag': '🇵🇱', 'dial': '+48'},
        'PT': {'slug': 'portugal', 'name': 'Portugal', 'flag': '🇵🇹', 'dial': '+351'},
        'RO': {'slug': 'romania', 'name': 'Romania', 'flag': '🇷🇴', 'dial': '+40'},
        'SK': {'slug': 'slovakia', 'name': 'Slovakia', 'flag': '🇸🇰', 'dial': '+421'},
        'SI': {'slug': 'slovenia', 'name': 'Slovenia', 'flag': '🇸🇮', 'dial': '+386'},
        'ZA': {'slug': 'southafrica', 'name': 'South Africa', 'flag': '🇿🇦', 'dial': '+27'},
        'ES': {'slug': 'spain', 'name': 'Spain', 'flag': '🇪🇸', 'dial': '+34'},
        'SE': {'slug': 'sweden', 'name': 'Sweden', 'flag': '🇸🇪', 'dial': '+46'},
        'TH': {'slug': 'thailand', 'name': 'Thailand', 'flag': '🇹🇭', 'dial': '+66'},
        'TR': {'slug': 'turkey', 'name': 'Turkey', 'flag': '🇹🇷', 'dial': '+90'},
        'UA': {'slug': 'ukraine', 'name': 'Ukraine', 'flag': '🇺🇦', 'dial': '+380'},
        'GB': {'slug': 'unitedkingdom', 'name': 'United Kingdom', 'flag': '🇬🇧', 'dial': '+44'},
        'UZ': {'slug': 'uzbekistan', 'name': 'Uzbekistan', 'flag': '🇺🇿', 'dial': '+998'},
        'VN': {'slug': 'vietnam', 'name': 'Vietnam', 'flag': '🇻🇳', 'dial': '+84'},
    }

    # Common service display name -> VirtualSMS service code mapping
    SERVICE_SLUGS = {
        'wa': {'code': 'wa', 'name': 'WhatsApp'},
        'whatsapp': {'code': 'wa', 'name': 'WhatsApp'},
        'wa_biz': {'code': 'wa_biz', 'name': 'WhatsApp Business'},
        'whatsapp business': {'code': 'wa_biz', 'name': 'WhatsApp Business'},
        'tg': {'code': 'tg', 'name': 'Telegram'},
        'telegram': {'code': 'tg', 'name': 'Telegram'},
        'go': {'code': 'go', 'name': 'Google / Gmail / YouTube'},
        'google': {'code': 'go', 'name': 'Google / Gmail / YouTube'},
        'gmail': {'code': 'go', 'name': 'Google / Gmail / YouTube'},
        'youtube': {'code': 'go', 'name': 'Google / Gmail / YouTube'},
        'dr': {'code': 'dr', 'name': 'OpenAI / ChatGPT'},
        'openai': {'code': 'dr', 'name': 'OpenAI / ChatGPT'},
        'chatgpt': {'code': 'dr', 'name': 'OpenAI / ChatGPT'},
        'ig': {'code': 'ig', 'name': 'Instagram / Threads'},
        'instagram': {'code': 'ig', 'name': 'Instagram / Threads'},
        'threads': {'code': 'ig', 'name': 'Instagram / Threads'},
        'lf': {'code': 'lf', 'name': 'TikTok'},
        'tiktok': {'code': 'lf', 'name': 'TikTok'},
        'douyin': {'code': 'lf', 'name': 'TikTok'},
        'fb': {'code': 'fb', 'name': 'Facebook / Meta'},
        'facebook': {'code': 'fb', 'name': 'Facebook / Meta'},
        'meta': {'code': 'fb', 'name': 'Facebook / Meta'},
        'tw': {'code': 'tw', 'name': 'Twitter / X'},
        'twitter': {'code': 'tw', 'name': 'Twitter / X'},
        'x': {'code': 'tw', 'name': 'Twitter / X'},
        'oi': {'code': 'oi', 'name': 'Tinder'},
        'tinder': {'code': 'oi', 'name': 'Tinder'},
        'ds': {'code': 'ds', 'name': 'Discord'},
        'discord': {'code': 'ds', 'name': 'Discord'},
        'fu': {'code': 'fu', 'name': 'Snapchat'},
        'snapchat': {'code': 'fu', 'name': 'Snapchat'},
        'nf': {'code': 'nf', 'name': 'Netflix'},
        'netflix': {'code': 'nf', 'name': 'Netflix'},
        'ub': {'code': 'ub', 'name': 'Uber'},
        'uber': {'code': 'ub', 'name': 'Uber'},
        'wx': {'code': 'wx', 'name': 'Apple ID / iCloud'},
        'apple': {'code': 'wx', 'name': 'Apple ID / iCloud'},
        'icloud': {'code': 'wx', 'name': 'Apple ID / iCloud'},
        'mm': {'code': 'mm', 'name': 'Microsoft'},
        'microsoft': {'code': 'mm', 'name': 'Microsoft'},
        'am': {'code': 'am', 'name': 'Amazon'},
        'amazon': {'code': 'am', 'name': 'Amazon'},
        'ts': {'code': 'ts', 'name': 'PayPal'},
        'paypal': {'code': 'ts', 'name': 'PayPal'},
        'mb': {'code': 'mb', 'name': 'Yahoo'},
        'yahoo': {'code': 'mb', 'name': 'Yahoo'},
        'mt': {'code': 'mt', 'name': 'Steam'},
        'steam': {'code': 'mt', 'name': 'Steam'},
        'li': {'code': 'li', 'name': 'LinkedIn'},
        'linkedin': {'code': 'li', 'name': 'LinkedIn'},
        'bl': {'code': 'bl', 'name': 'Bigo Live'},
        'bigo live': {'code': 'bl', 'name': 'Bigo Live'},
        're': {'code': 're', 'name': 'Reddit'},
        'reddit': {'code': 're', 'name': 'Reddit'},
        'bank verification': {'code': 'ot', 'name': 'Bank Verification'},
        'bank': {'code': 'ot', 'name': 'Bank Verification'},
        'other': {'code': 'ot', 'name': 'Other Platforms'},
        'ot': {'code': 'ot', 'name': 'Other Platforms'}
    }

    _client = None
    _tv_client = None

    @classmethod
    def get_textverified_client(cls):
        if cls._tv_client is not None:
            return cls._tv_client
        import os
        try:
            from textverified import TextVerified
        except ImportError:
            return None
        
        api_key = (os.getenv('TEXTVERIFIED_API_KEY') or getattr(Config, 'TEXTVERIFIED_API_KEY', '')).strip()
        api_username = (os.getenv('TEXTVERIFIED_USERNAME') or getattr(Config, 'TEXTVERIFIED_USERNAME', '')).strip()
        if not api_key or not api_username:
            return None
        try:
            cls._tv_client = TextVerified(api_key=api_key, api_username=api_username)
            return cls._tv_client
        except Exception as e:
            print(f"[SIMProviderService] Error initializing TextVerified: {e}")
            return None

    @classmethod
    def get_smscode_client(cls) -> SMSCodeClient:
        if cls._client is None:
            cls._client = SMSCodeClient()
        return cls._client

    @classmethod
    def get_virtualsms_client(cls) -> SMSCodeClient:
        return cls.get_smscode_client()

    @classmethod
    def get_client(cls) -> SMSCodeClient:
        return cls.get_smscode_client()

    @classmethod
    def calculate_retail_price(cls, base_cost: float, service_code: str = None, provider_type: str = 'smscode', country_code: str = 'US') -> tuple[float, float]:
        """Calculates retail price and profit margin in USD using admin-configured markup and overrides.
        Fixed service price overrides apply exclusively to US numbers (Basic & TextVerified US Reliable).
        Global numbers (GB, NG, etc.) strictly follow provider dynamic markup.
        """
        if base_cost <= 0:
            return 1.50, 1.50

        try:
            from app.services.settings_service import SettingsService
            if provider_type == 'textverified':
                pct, floor = SettingsService.get_textverified_markup()
            else:
                pct, floor = SettingsService.get_smscode_markup()

            # Overrides apply strictly to US numbers
            is_us = (provider_type == 'textverified') or (country_code and str(country_code).strip().upper() in ('US', 'USA'))
            if is_us and service_code:
                sc = service_code.strip().lower()
                all_overrides = SettingsService.get_price_overrides()
                overrides = {
                    o['service_code'].strip().lower(): float(o['override_price_usd'])
                    for o in all_overrides
                    if o.get('provider_type') in (provider_type, '5sim', 'virtualsms', 'smscode', 'all') and o.get('is_active', True)
                }
                if sc in overrides:
                    override_p = overrides[sc]
                    return override_p, round(override_p - base_cost, 4)
        except Exception:
            pct, floor = 0.0, 0.0

        if pct <= 0.0 and floor <= 0.0:
            retail_price = round(base_cost, 2)
            profit_margin = 0.0
        else:
            mult = 1.0 + (pct / 100.0)
            markup = max(base_cost * mult, base_cost + floor)
            retail_price = round(markup, 2)
            profit_margin = round(retail_price - base_cost, 4)
        return retail_price, profit_margin

    _cached_raw_catalog = None
    _cached_whatsapp_operators = None
    _cached_telegram_operators = None

    @classmethod
    def get_whatsapp_operator_info(cls, country_slug: str) -> dict:
        """Retrieves the 2nd cheapest clean operator route for WhatsApp in a given country to bypass recycled numbers."""
        if cls._cached_whatsapp_operators is None:
            import json
            data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'whatsapp_operators.json')
            if os.path.exists(data_path):
                try:
                    with open(data_path, 'r', encoding='utf-8') as f:
                        cls._cached_whatsapp_operators = json.load(f)
                except Exception as e:
                    print(f"[SIMProviderService] Error loading whatsapp_operators.json: {e}")
                    cls._cached_whatsapp_operators = {}
            else:
                cls._cached_whatsapp_operators = {}

        c_clean = (country_slug or '').lower().replace(' ', '').replace('_', '')
        alias_map = {
            'uk': 'england',
            'unitedkingdom': 'england',
            'greatbritain': 'england',
            'gb': 'england',
            'us': 'usa',
            'unitedstates': 'usa'
        }
        lookup_key = alias_map.get(c_clean, c_clean)
        return cls._cached_whatsapp_operators.get(lookup_key) or {}

    @classmethod
    def get_telegram_operator_info(cls, country_slug: str) -> dict:
        """Retrieves the 2nd cheapest clean operator route for Telegram in a given country to bypass recycled numbers."""
        if cls._cached_telegram_operators is None:
            import json
            data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'telegram_operators.json')
            if os.path.exists(data_path):
                try:
                    with open(data_path, 'r', encoding='utf-8') as f:
                        cls._cached_telegram_operators = json.load(f)
                except Exception as e:
                    print(f"[SIMProviderService] Error loading telegram_operators.json: {e}")
                    cls._cached_telegram_operators = {}
            else:
                cls._cached_telegram_operators = {}

        c_clean = (country_slug or '').lower().replace(' ', '').replace('_', '')
        alias_map = {
            'uk': 'england',
            'unitedkingdom': 'england',
            'greatbritain': 'england',
            'gb': 'england',
            'us': 'usa',
            'unitedstates': 'usa'
        }
        lookup_key = alias_map.get(c_clean, c_clean)
        return cls._cached_telegram_operators.get(lookup_key) or {}

    @classmethod
    def _load_raw_catalog(cls):
        if cls._cached_raw_catalog is not None:
            return cls._cached_raw_catalog

        import json
        json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'catalog.json')
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        # Filter out US from countries list (handled separately in US page)
                        raw_countries = data.get('countries', [])
                        filtered_countries = [c for c in raw_countries if c.get('country_code', '').upper() != 'US']
                        data['countries'] = filtered_countries
                        cls._cached_raw_catalog = data
                        return data
                    elif isinstance(data, list) and len(data) > 0:
                        filtered_data = [c for c in data if c.get('country_code', '').upper() != 'US']
                        cls._cached_raw_catalog = filtered_data
                        return filtered_data
            except Exception as e:
                print(f"[SIMProviderService] Error reading catalog.json: {e}")
        return []

    _cached_dynamic_catalog = None

    @classmethod
    def get_catalog(cls):
        """Returns country and service catalog loaded from app/data/catalog.json.
        Covers all 242 countries and all 1,236 SMSCode services with dynamic markups and overrides applied.
        """
        if cls._cached_dynamic_catalog is not None:
            return cls._cached_dynamic_catalog

        raw_data = cls._load_raw_catalog()
        if not raw_data:
            return {
                'countries': [
                    {
                        'country_code': 'GB',
                        'country_name': 'United Kingdom',
                        'country_slug': 'england',
                        'flag': '🇬🇧',
                        'dial': '+44',
                    }
                ],
                'services': [
                    {'name': 'WhatsApp', 'code': 'whatsapp', 'platform_id': 1, 'is_core': True, 'base_cost': 0.50, 'price': 0.50, 'available': 1000},
                    {'name': 'Telegram', 'code': 'telegram', 'platform_id': 2, 'is_core': True, 'base_cost': 0.30, 'price': 0.30, 'available': 1000},
                    {'name': 'Google / Gmail', 'code': 'google', 'platform_id': 5, 'is_core': True, 'base_cost': 0.20, 'price': 0.20, 'available': 1000}
                ]
            }

        try:
            from app.services.settings_service import SettingsService
            try:
                pct, floor = SettingsService.get_smscode_markup()
            except Exception:
                pct, floor = SettingsService.get_fivesim_markup()
            all_overrides = SettingsService.get_price_overrides()
            overrides = {
                o['service_code'].strip().lower(): float(o['override_price_usd'])
                for o in all_overrides
                if o.get('provider_type') in ('smscode', 'virtualsms', '5sim', 'all') and o.get('is_active', True) and o.get('service_code')
            }
        except Exception:
            pct, floor = 0.0, 0.0
            overrides = {}

        mult = 1.0 + (pct / 100.0)

        if isinstance(raw_data, dict):
            countries = raw_data.get('countries', [])
            raw_services = raw_data.get('services', [])
            processed_services = []
            for s in raw_services:
                s_copy = dict(s)
                s_code = (s.get('code') or '').lower().strip()
                base = float(s.get('base_cost') or s.get('base_price') or s.get('price', 0.20))
                s_copy['base_cost'] = base

                if s_code in overrides:
                    s_copy['price'] = overrides[s_code]
                    s_copy['is_override'] = True
                elif pct <= 0.0 and floor <= 0.0:
                    s_copy['price'] = round(base, 2)
                else:
                    s_copy['price'] = round(max(base * mult, base + floor), 2)
                processed_services.append(s_copy)

            res = {'countries': countries, 'services': processed_services}
            cls._cached_dynamic_catalog = res
            return res

        # Legacy list of country dicts
        dynamic_catalog = []
        for c in raw_data:
            c_copy = dict(c)
            services_list = []
            for s in c.get('services', []):
                s_copy = dict(s)
                s_code = (s.get('code') or '').lower().strip()
                base = float(s.get('base_cost') or s.get('base_price') or s.get('price', 0.20))
                s_copy['base_cost'] = base

                if s_code in overrides:
                    s_copy['price'] = overrides[s_code]
                    s_copy['is_override'] = True
                elif pct <= 0.0 and floor <= 0.0:
                    s_copy['price'] = round(base, 2)
                else:
                    s_copy['price'] = round(max(base * mult, base + floor), 2)
                services_list.append(s_copy)
            c_copy['services'] = services_list
            dynamic_catalog.append(c_copy)
        return dynamic_catalog

    @classmethod
    def purchase_number(
        cls,
        country_code: str,
        service_name: str,
        operator: str = 'any',
        service_code: str = None,
        operator_id: int = None,
        catalog_product_id: int = None,
        product_id: int = None
    ) -> dict:
        """Allocates a virtual number using SMSCode.gg API.
        Falls back to local preview mode if API key is not configured.
        """
        client = cls.get_client()
        cc_clean = (country_code or 'US').upper().strip()
        svc_clean = (service_name or 'WhatsApp').strip()

        # Map country to metadata and slug
        c_meta = cls.COUNTRY_SLUGS.get(cc_clean)
        if c_meta:
            country_slug = c_meta['slug']
            country_name = c_meta['name']
        else:
            cat = cls.get_catalog()
            country_list = cat.get('countries', []) if isinstance(cat, dict) else cat
            matched = next((c for c in country_list if c.get('country_code', '').upper() == cc_clean or c.get('country_slug', '').lower() == cc_clean.lower()), None)
            if matched:
                country_slug = matched.get('country_slug', cc_clean.lower())
                country_name = matched.get('country_name', cc_clean)
            else:
                country_slug = cc_clean.lower()
                country_name = cc_clean

        # Resolve service code
        if service_code:
            svc_code_clean = str(service_code).strip().lower()
        else:
            svc_lookup = svc_clean.lower().split('/')[0].strip()
            s_meta = cls.SERVICE_SLUGS.get(svc_lookup)
            if s_meta:
                svc_code_clean = s_meta['code']
            else:
                svc_code_clean = svc_lookup.replace(' ', '').replace('-', '').lower()

        # Handle numeric operator string passed as operator
        if operator_id is None and operator and str(operator).isdigit():
            try:
                operator_id = int(operator)
            except Exception:
                pass

        order_ref = f"TGS-SIM-{uuid.uuid4().hex[:6].upper()}"

        # If SMSCode client is configured, make live API purchase
        if client.is_configured:
            buy_res = client.buy_activation(
                country_code=cc_clean,
                service_code=svc_code_clean,
                operator_id=operator_id,
                operator=operator,
                catalog_product_id=catalog_product_id,
                product_id=product_id
            )
            if not buy_res.get('success'):
                return buy_res

            prov_id = buy_res.get('provider_order_id')
            phone = buy_res.get('phone_number')
            prov_cost = float(buy_res.get('provider_cost') or 0.0)
            allocated_op = buy_res.get('operator') or (str(operator) if operator and operator != 'any' else 'standard')
            retail_price, margin = cls.calculate_retail_price(
                base_cost=prov_cost,
                service_code=svc_code_clean,
                provider_type='smscode',
                country_code=cc_clean
            )

            return {
                'success': True,
                'order_reference': order_ref,
                'phone_number': phone,
                'provider_order_id': prov_id,
                'country_code': cc_clean,
                'country_name': country_name,
                'country_slug': country_slug,
                'service_name': svc_clean,
                'service_code': svc_code_clean,
                'operator': allocated_op,
                'provider_cost': prov_cost,
                'retail_price': retail_price,
                'profit_margin': margin,
                'expires_at': buy_res.get('expires_at'),
                'is_esim': False,
                'status': 'pending'
            }

        # Fallback simulation for sandbox / preview before live funding
        prefix = c_meta.get('dial', '+1') if c_meta else '+1'
        import random
        random_digits = f"{random.randint(100, 999)} {random.randint(1000, 9999)}"
        phone_number = f"{prefix} 555-{random_digits}"
        prov_id = f"SIM-{uuid.uuid4().hex[:8].upper()}"

        return {
            'success': True,
            'order_reference': order_ref,
            'phone_number': phone_number,
            'provider_order_id': prov_id,
            'country_code': cc_clean,
            'country_name': c_meta['name'] if c_meta else country_name,
            'country_slug': country_slug,
            'service_name': svc_clean,
            'service_code': svc_code_clean,
            'operator': 'standard',
            'provider_cost': 0.50,
            'retail_price': 1.00,
            'profit_margin': 0.50,
            'is_esim': False,
            'status': 'pending'
        }

    @classmethod
    def check_sms(cls, order_id: str) -> dict:
        """Polls 5sim for incoming SMS."""
        client = cls.get_client()

        # Find order in DB to get provider_order_id and created_at
        from app.services.supabase_client import get_supabase_admin, reset_supabase_admin
        admin = get_supabase_admin()
        prov_order_id = None
        order = None
        if admin:
            for attempt in range(2):
                try:
                    import uuid
                    is_valid_uuid = False
                    try:
                        uuid.UUID(str(order_id))
                        is_valid_uuid = True
                    except (ValueError, TypeError):
                        is_valid_uuid = False

                    if is_valid_uuid:
                        q = admin.table('sim_orders').select('*').or_(f"id.eq.{order_id},order_reference.eq.{order_id}")
                    else:
                        q = admin.table('sim_orders').select('*').eq('order_reference', order_id)
                    res = q.limit(1).execute()
                    if res.data and len(res.data) > 0:
                        order = res.data[0]
                        prov_order_id = order.get('provider_order_id')
                    break
                except Exception as e:
                    err_str = str(e).lower()
                    if ('10054' in err_str or 'connection' in err_str or 'closed' in err_str) and attempt == 0:
                        reset_supabase_admin()
                        admin = get_supabase_admin(fresh=True)
                        continue
                    print(f"[check_sms] error looking up order: {e}")
                    break

        if not prov_order_id:
            for o in mock_db.sim_orders:
                if o.get('id') == order_id or o.get('order_reference') == order_id:
                    order = o
                    prov_order_id = o.get('provider_order_id')
                    break

        if prov_order_id and prov_order_id.startswith('TXTV-'):
            tv_id = prov_order_id[5:]
            if tv_id.startswith('DEMO-'):
                return {
                    'has_sms': False,
                    'sms_code': None,
                    'full_sms': None,
                    'status': 'PENDING'
                }
            tv_client = cls.get_textverified_client()
            if tv_client:
                try:
                    import dateutil.parser
                    verification = tv_client.verifications.details(tv_id)
                    sms_list = tv_client.sms.list(data=verification)
                    items = list(sms_list)
                    if items:
                        # Sort newest SMS first
                        items.sort(
                            key=lambda s: getattr(s, 'created_at', None) or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc),
                            reverse=True
                        )
                        sms = items[0]  # Absolute newest SMS received

                        # Check if order was reactivated and if this SMS arrived during current activation window
                        order_created = order.get('created_at') if order else None
                        if order_created and hasattr(sms, 'created_at') and sms.created_at:
                            try:
                                if isinstance(order_created, str):
                                    order_dt = dateutil.parser.parse(order_created)
                                else:
                                    order_dt = order_created
                                if order_dt.tzinfo is None:
                                    order_dt = order_dt.replace(tzinfo=datetime.timezone.utc)
                                sms_dt = sms.created_at
                                if sms_dt.tzinfo is None:
                                    sms_dt = sms_dt.replace(tzinfo=datetime.timezone.utc)

                                # If latest SMS is older than order activation window (with 15s grace), wait for new code!
                                if (sms_dt - order_dt).total_seconds() < -15:
                                    return {
                                        'has_sms': False,
                                        'sms_code': None,
                                        'full_sms': None,
                                        'status': 'PENDING'
                                    }
                            except Exception as ex:
                                print(f"[SIMProviderService] Reactivation date check error: {ex}")

                        code = sms.parsed_code
                        text = sms.sms_content
                        sms_id = getattr(sms, 'id', str(len(items)))
                        return {
                            'has_sms': True,
                            'sms_code': code,
                            'full_sms': text or (f"Your verification code is: {code}" if code else None),
                            'provider_sms_id': sms_id
                        }
                    else:
                        st = verification.state.value if hasattr(verification.state, 'value') else str(verification.state)
                        return {
                            'has_sms': False,
                            'sms_code': None,
                            'full_sms': None,
                            'status': st
                        }
                except Exception as e:
                    print(f"[SIMProviderService] TextVerified check_sms error: {e}")

        if client.is_configured and prov_order_id and not prov_order_id.startswith('SIM-') and not prov_order_id.startswith('USCA-'):
            check_res = client.check_order(prov_order_id)
            if check_res.get('has_sms'):
                return check_res
            return {
                'has_sms': False,
                'sms_code': None,
                'full_sms': None,
                'status': check_res.get('status', 'PENDING')
            }

        return {
            'has_sms': False,
            'sms_code': None,
            'full_sms': None,
            'status': 'PENDING'
        }

    @classmethod
    def cancel_order(cls, provider_order_id: str) -> dict:
        """Cancels order with provider."""
        if provider_order_id and provider_order_id.startswith('TXTV-'):
            tv_id = provider_order_id[5:]
            tv_client = cls.get_textverified_client()
            if tv_client:
                try:
                    verification = tv_client.verifications.details(tv_id)
                    verification.cancel()
                    return {'success': True}
                except Exception as e:
                    print(f"[SIMProviderService] TextVerified cancel_order error: {e}")
                    return {'success': False, 'message': str(e)}

        client = cls.get_client()
        if client.is_configured and provider_order_id and not provider_order_id.startswith('SIM-') and not provider_order_id.startswith('USCA-'):
            return client.cancel_order(provider_order_id)
        return {'success': True}

    @classmethod
    def finish_order(cls, provider_order_id: str) -> dict:
        """Finishes order with 5sim."""
        client = cls.get_client()
        if client.is_configured and provider_order_id and not provider_order_id.startswith('SIM-'):
            return client.finish_order(provider_order_id)
        return {'success': True}

    @classmethod
    def ban_order(cls, provider_order_id: str) -> dict:
        """Bans order with provider and triggers refund."""
        client = cls.get_client()
        if client.is_configured and provider_order_id and not provider_order_id.startswith('SIM-'):
            return client.ban_order(provider_order_id)
        return {'success': True}

    # =========================================================================
    # Dedicated US & Canada Reliability Service (Tiers, Packages, Providers)
    # =========================================================================
    US_CANADA_PACKAGES = [
        {
            'id': 'basic_pool',
            'name': 'Basic Package',
            'badge': 'Economy',
            'badge_class': 'badge-neutral',
            'description': 'Standard pool virtual numbers with automatic carrier rotation. Ideal for general platform verifications and everyday accounts.',
            'features': [
                'Cheapest high-availability virtual routes',
                'Multi-carrier rotation for maximum availability',
                'Instant auto-refund to wallet if no SMS received'
            ],
            'price_range_label': '₦800 – ₦3,000',
            'price_range_usd': '$0.50 – $1.85',
        },
        {
            'id': 'reliable_non_voip',
            'name': 'Reliable Package',
            'badge': 'Recommended',
            'badge_class': 'badge-brand',
            'description': 'Screened 100% Non-VoIP real cellular lines (AT&T, Verizon, T-Mobile). Supports number reactivation to request additional OTP codes on the same number.',
            'features': [
                '100% Non-VoIP real cellular carrier numbers',
                'Screened unbanned guarantee for WhatsApp & Banking',
                'Supports reactivation for additional OTP codes',
                'Dedicated 1-to-1 reliable carrier routing',
                'Instant auto-refund to wallet if no SMS received'
            ],
            'price_range_label': '₦4,000 – ₦6,000',
            'price_range_usd': '$2.50 – $3.75',
        },
    ]

    FIVESIM_US_SERVICES_WITH_ROUTES = [
        {'id': 'whatsapp_virtual28', 'service_name': 'WhatsApp', 'service_code': 'whatsapp', 'operator': 'virtual28', 'name': 'WhatsApp', 'quality': 'Economy Pool', 'price_usd': 1.92},
        {'id': 'wabiz_virtual28', 'service_name': 'WhatsApp Business', 'service_code': 'whatsapp', 'operator': 'virtual28', 'name': 'WhatsApp Business', 'quality': 'Economy Pool', 'price_usd': 1.92},
        {'id': 'telegram_virtual28', 'service_name': 'Telegram', 'service_code': 'telegram', 'operator': 'virtual28', 'name': 'Telegram', 'quality': 'Economy Pool', 'price_usd': 0.89},
        {'id': 'google_virtual28', 'service_name': 'Google / Gmail / YouTube', 'service_code': 'google', 'operator': 'virtual28', 'name': 'Google / Gmail / YouTube', 'quality': 'Economy Pool', 'price_usd': 0.38},
        {'id': 'openai_virtual63', 'service_name': 'OpenAI / ChatGPT', 'service_code': 'openai', 'operator': 'virtual63', 'name': 'OpenAI / ChatGPT', 'quality': 'Economy Pool', 'price_usd': 0.15},
        {'id': 'instagram_virtual8', 'service_name': 'Instagram', 'service_code': 'instagram', 'operator': 'virtual8', 'name': 'Instagram', 'quality': 'Economy Pool', 'price_usd': 0.15},
        {'id': 'twitter_virtual8', 'service_name': 'Twitter / X', 'service_code': 'twitter', 'operator': 'virtual8', 'name': 'Twitter / X', 'quality': 'Economy Pool', 'price_usd': 0.20},
        {'id': 'tiktok_virtual8', 'service_name': 'TikTok', 'service_code': 'tiktok', 'operator': 'virtual8', 'name': 'TikTok', 'quality': 'Economy Pool', 'price_usd': 0.15},
        {'id': 'fb_virtual8', 'service_name': 'Facebook', 'service_code': 'facebook', 'operator': 'virtual8', 'name': 'Facebook', 'quality': 'Economy Pool', 'price_usd': 0.15},
        {'id': 'tinder_virtual8', 'service_name': 'Tinder', 'service_code': 'tinder', 'operator': 'virtual8', 'name': 'Tinder', 'quality': 'Economy Pool', 'price_usd': 0.55},
        {'id': 'apple_virtual8', 'service_name': 'Apple ID / iCloud', 'service_code': 'apple', 'operator': 'virtual8', 'name': 'Apple ID / iCloud', 'quality': 'Economy Pool', 'price_usd': 0.40},
        {'id': 'paypal_virtual8', 'service_name': 'PayPal', 'service_code': 'paypal', 'operator': 'virtual8', 'name': 'PayPal', 'quality': 'Economy Pool', 'price_usd': 0.85},
        {'id': 'amazon_virtual8', 'service_name': 'Amazon', 'service_code': 'amazon', 'operator': 'virtual8', 'name': 'Amazon', 'quality': 'Economy Pool', 'price_usd': 0.35},
        {'id': 'uber_virtual8', 'service_name': 'Uber / Lyft', 'service_code': 'uber', 'operator': 'virtual8', 'name': 'Uber / Lyft', 'quality': 'Economy Pool', 'price_usd': 0.30},
        {'id': 'discord_virtual8', 'service_name': 'Discord', 'service_code': 'discord', 'operator': 'virtual8', 'name': 'Discord', 'quality': 'Economy Pool', 'price_usd': 0.25},
        {'id': 'other_virtual8', 'service_name': 'Other Platforms', 'service_code': 'other', 'operator': 'virtual8', 'name': 'Other Platforms', 'quality': 'Economy Pool', 'price_usd': 0.40},
    ]

    TEXTVERIFIED_US_SERVICES = [
        {'id': 'tv_whatsapp', 'service_name': 'WhatsApp', 'service_code': 'whatsapp', 'name': 'WhatsApp (Dedicated Non-VoIP Line)', 'price_usd': 2.50},
        {'id': 'tv_wabiz', 'service_name': 'WhatsApp Business', 'service_code': 'whatsapp', 'name': 'WhatsApp Business (Dedicated Non-VoIP)', 'price_usd': 2.75},
        {'id': 'tv_bank', 'service_name': 'Bank Verification', 'service_code': 'bank', 'name': 'Bank Verification (Chase, Wells Fargo, Chime)', 'price_usd': 3.50},
        {'id': 'tv_fintech', 'service_name': 'PayPal / CashApp / Venmo / Zelle', 'service_code': 'paypal', 'name': 'PayPal / CashApp / Venmo / Zelle', 'price_usd': 3.25},
        {'id': 'tv_google', 'service_name': 'Google / Gmail / YouTube', 'service_code': 'google', 'name': 'Google / Gmail / YouTube (Dedicated Cellular)', 'price_usd': 2.50},
        {'id': 'tv_telegram', 'service_name': 'Telegram', 'service_code': 'telegram', 'name': 'Telegram (Dedicated Cellular Line)', 'price_usd': 2.60},
        {'id': 'tv_openai', 'service_name': 'OpenAI / ChatGPT / Codex', 'service_code': 'openai', 'name': 'OpenAI / ChatGPT (Dedicated Cellular)', 'price_usd': 2.75},
        {'id': 'tv_apple', 'service_name': 'Apple ID / iCloud', 'service_code': 'apple', 'name': 'Apple ID / iCloud (Dedicated Cellular)', 'price_usd': 2.80},
        {'id': 'tv_tinder', 'service_name': 'Tinder / Bumble / Hinge', 'service_code': 'tinder', 'name': 'Tinder / Bumble / Hinge', 'price_usd': 2.75},
        {'id': 'tv_uber', 'service_name': 'Uber / Lyft', 'service_code': 'uber', 'name': 'Uber / Lyft (Dedicated Cellular)', 'price_usd': 2.60},
        {'id': 'tv_facebook', 'service_name': 'Facebook / Instagram', 'service_code': 'facebook', 'name': 'Facebook / Instagram (Real Cellular)', 'price_usd': 2.50},
        {'id': 'tv_twitter', 'service_name': 'Twitter / X', 'service_code': 'twitter', 'name': 'Twitter / X (Real Cellular Line)', 'price_usd': 2.50},
        {'id': 'tv_amazon', 'service_name': 'Amazon / AWS', 'service_code': 'amazon', 'name': 'Amazon / AWS Verification', 'price_usd': 2.50},
        {'id': 'tv_discord', 'service_name': 'Discord', 'service_code': 'discord', 'name': 'Discord Phone Verification', 'price_usd': 2.50},
        {'id': 'tv_craigslist', 'service_name': 'Craigslist', 'service_code': 'craigslist', 'name': 'Craigslist (Non-VoIP Dedicated)', 'price_usd': 2.75},
        {'id': 'tv_microsoft', 'service_name': 'Microsoft / Outlook / Office365', 'service_code': 'microsoft', 'name': 'Microsoft / Outlook / Office365', 'price_usd': 2.50},
        {'id': 'tv_other', 'service_name': 'Other Platforms', 'service_code': 'other', 'name': 'Other Platforms (Guaranteed Cellular)', 'price_usd': 2.75},
    ]

    _cached_5sim_us_services_raw = None
    _cached_textverified_us_services_raw = None

    @classmethod
    def _load_raw_5sim_us_services(cls) -> list:
        if cls._cached_5sim_us_services_raw is not None:
            return cls._cached_5sim_us_services_raw

        raw = []
        # 1. Attempt loading directly from Supabase database table service_catalog
        try:
            from app.services.supabase_client import get_supabase_admin
            admin = get_supabase_admin()
            if admin:
                res = admin.table('service_catalog').select('*').eq('country_code', 'US').eq('is_active', True).execute()
                if res.data and len(res.data) > 0:
                    for row in res.data:
                        raw.append({
                            'id': f"{row['service_code']}_us",
                            'service_name': row['service_name'],
                            'service_code': row['service_code'],
                            'operator': row.get('operator') or 'standard',
                            'name': row['service_name'],
                            'quality': 'Economy Pool',
                            'price_usd': float(row.get('retail_price') or 1.00),
                            'base_cost_usd': float(row.get('provider_cost') or 0.20),
                            'count': int(row.get('available_count') or 100)
                        })
        except Exception as e:
            print(f"[SIMProviderService] Error querying service_catalog from Supabase: {e}")

        # 2. Fallback to cached JSON file if DB query returned nothing
        if not raw:
            import json
            import os
            data_path = os.path.join(os.path.dirname(__file__), '..', 'data', '5sim_us_services.json')
            if os.path.exists(data_path):
                try:
                    with open(data_path, 'r', encoding='utf-8') as f:
                        raw = json.load(f)
                except Exception as e:
                    print(f"[SIMProviderService] Error loading 5sim_us_services.json: {e}")

        if not raw:
            raw = cls.FIVESIM_US_SERVICES_WITH_ROUTES

        # Deduplicate to single selected option per service code
        grouped = {}
        for item in raw:
            sc = item.get('service_code')
            if not sc:
                continue
            if sc not in grouped:
                grouped[sc] = []
            grouped[sc].append(item)

        cheapest_list = []
        for sc, items in grouped.items():
            best = dict(items[0])
            svc_name = best.get('service_name') or best.get('name') or sc.title()
            best['name'] = svc_name
            best['service_name'] = svc_name
            best['quality'] = 'Economy Pool'
            cheapest_list.append(best)

        # Priority ordering: popular services top, then alphabetical, Any Other at bottom
        POPULAR_KEYS = {
            'wa': 1, 'wa_biz': 2, 'whatsapp': 1, 'telegram': 3, 'tg': 3, 'google': 4, 'go': 4,
            'instagram': 5, 'ig': 5, 'twitter': 6, 'tw': 6, 'openai': 7, 'dr': 7, 'tiktok': 8, 'lf': 8,
            'facebook': 9, 'fb': 9, 'tinder': 10, 'oi': 10, 'apple': 11, 'wx': 11, 'discord': 12, 'ds': 12,
            'uber': 13, 'ub': 13, 'amazon': 14, 'am': 14, 'netflix': 15, 'nf': 15, 'paypal': 16, 'ts': 16,
            'ot': 99, 'other': 99
        }
        cheapest_list.sort(key=lambda x: (
            0 if POPULAR_KEYS.get(str(x.get('service_code')).lower(), 50) < 50 else (2 if POPULAR_KEYS.get(str(x.get('service_code')).lower()) == 99 else 1),
            POPULAR_KEYS.get(str(x.get('service_code')).lower(), 50),
            str(x.get('service_name', '')).lower()
        ))
        cls._cached_5sim_us_services_raw = cheapest_list
        return cls._cached_5sim_us_services_raw

    _cached_smscode_us_services_raw = None

    @classmethod
    def get_smscode_us_services(cls, apply_markup: bool = True) -> list:
        """Loads the 10 core USA services from app/data/usa_core_services.json with multiple operators per service,
        plus all 1,226 non-core services with 2 server routes, applying dynamic admin markup and price overrides.
        """
        if apply_markup and cls._cached_smscode_us_services_raw is not None:
            return cls._cached_smscode_us_services_raw

        import json
        data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'usa_core_services.json')
        if not os.path.exists(data_path):
            return cls.FIVESIM_US_SERVICES_WITH_ROUTES

        try:
            with open(data_path, 'r', encoding='utf-8') as f:
                raw_map = json.load(f)
        except Exception as e:
            print(f"[SIMProviderService] Error loading usa_core_services.json: {e}")
            return cls.FIVESIM_US_SERVICES_WITH_ROUTES

        pct = 0.0
        floor = 0.0
        overrides = {}
        if apply_markup:
            try:
                from app.services.settings_service import SettingsService
                pct, floor = SettingsService.get_smscode_markup()
                all_overrides = SettingsService.get_price_overrides()
                overrides = {
                    o['service_code'].strip().lower(): float(o['override_price_usd'])
                    for o in all_overrides
                    if o.get('provider_type') in ('smscode', 'virtualsms', '5sim', 'all') and o.get('is_active', True) and o.get('service_code')
                }
            except Exception:
                pct, floor = 0.0, 0.0

        mult = 1.0 + (pct / 100.0)

        ORDER = ['whatsapp', 'telegram', 'google-youtube-gmail', 'instagram-threads', 'twitter', 'facebook', 'openai', 'tiktok-douyin', 'discord', 'apple']
        DISPLAY_NAMES = {
            'whatsapp': 'WhatsApp',
            'telegram': 'Telegram',
            'google-youtube-gmail': 'Google / Gmail / YouTube',
            'instagram-threads': 'Instagram / Threads',
            'twitter': 'Twitter / X',
            'facebook': 'Facebook / Meta',
            'openai': 'OpenAI / ChatGPT',
            'tiktok-douyin': 'TikTok',
            'discord': 'Discord',
            'apple': 'Apple ID / iCloud'
        }

        services_list = []
        for key in ORDER:
            data = raw_map.get(key)
            if not data:
                continue
            sc = key
            std_code = {
                'google-youtube-gmail': 'google',
                'instagram-threads': 'instagram',
                'tiktok-douyin': 'tiktok'
            }.get(sc, sc)

            svc_name = DISPLAY_NAMES.get(key, data.get('service_name', key.title()))
            raw_ops = data.get('operators', [])

            processed_ops = []
            for op in raw_ops:
                base_cost = float(op.get('base_price_usd', 0.50))
                if std_code in overrides:
                    op_retail = overrides[std_code]
                elif sc in overrides:
                    op_retail = overrides[sc]
                elif not apply_markup:
                    op_retail = round(base_cost, 2)
                elif pct <= 0.0 and floor <= 0.0:
                    op_retail = round(base_cost, 2)
                else:
                    op_retail = round(max(base_cost * mult, base_cost + floor), 2)

                clean_op = dict(op)
                clean_op['base_cost_usd'] = base_cost
                clean_op['price_usd'] = op_retail
                clean_op['price'] = op_retail

                raw_name = op.get('operator_name', '')
                op_code = op.get('operator_code', '').lower()
                if 'tmobile' in op_code or 't-mobile' in raw_name.lower():
                    clean_op['is_tmobile'] = True
                    clean_op['operator_name'] = 'T-Mobile'
                elif 'at_t' in op_code or 'at&t' in raw_name.lower():
                    clean_op['operator_name'] = 'AT&T'
                elif 'verizon' in op_code or 'verizon' in raw_name.lower():
                    clean_op['operator_name'] = 'Verizon'
                elif 'mint' in op_code or 'mint' in raw_name.lower():
                    clean_op['operator_name'] = 'Mint Mobile'
                elif 'textnow' in op_code or 'textnow' in raw_name.lower():
                    clean_op['operator_name'] = 'TextNow'
                elif 'us_mobile' in op_code or 'us mobile' in raw_name.lower():
                    clean_op['operator_name'] = 'US Mobile'
                elif 'physic' in raw_name.lower():
                    clean_op['operator_name'] = 'Physical SIM Route'
                processed_ops.append(clean_op)

            # Sort operators so T-Mobile is first if present, then sorted by price ascending
            processed_ops.sort(key=lambda o: (0 if o.get('is_tmobile') else 1, o['price_usd']))

            default_op = processed_ops[0] if processed_ops else {}

            item = {
                'id': f"{std_code}_basic",
                'service_name': svc_name,
                'name': svc_name,
                'service_code': std_code,
                'catalog_slug': sc,
                'quality': 'Economy Pool',
                'is_core': True,
                'price_usd': default_op.get('price_usd', 1.00),
                'base_cost_usd': default_op.get('base_cost_usd', 0.50),
                'operator': default_op.get('operator_name', 'T-Mobile'),
                'operator_id': default_op.get('operator_id', 125),
                'catalog_product_id': default_op.get('catalog_product_id'),
                'cheapest_product_id': default_op.get('cheapest_product_id'),
                'operators': processed_ops,
                'available': sum(op.get('available', 0) for op in processed_ops)
            }
            services_list.append(item)

        # Append non-core services from usa_other_services.json
        other_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'usa_other_services.json')
        if os.path.exists(other_path):
            try:
                with open(other_path, 'r', encoding='utf-8') as f:
                    other_map = json.load(f)

                sorted_keys = sorted(other_map.keys(), key=lambda k: other_map[k].get('service_name', k).lower())
                for key in sorted_keys:
                    entry = other_map[key]
                    s_code = entry.get('service_code') or key
                    s_name = entry.get('service_name') or key.title()
                    raw_ops = entry.get('operators', [])

                    processed_ops = []
                    for op in raw_ops:
                        base_cost = float(op.get('base_price_usd', 0.20))
                        if s_code in overrides:
                            op_retail = overrides[s_code]
                        elif not apply_markup or (pct <= 0.0 and floor <= 0.0):
                            op_retail = round(base_cost, 2)
                        else:
                            op_retail = round(max(base_cost * mult, base_cost + floor), 2)

                        clean_op = dict(op)
                        clean_op['base_cost_usd'] = base_cost
                        clean_op['price_usd'] = op_retail
                        clean_op['price'] = op_retail
                        processed_ops.append(clean_op)

                    if not processed_ops:
                        continue

                    default_op = processed_ops[0]
                    services_list.append({
                        'id': f"{s_code}_basic",
                        'service_name': s_name,
                        'name': s_name,
                        'service_code': s_code,
                        'catalog_slug': key,
                        'quality': 'Economy Pool',
                        'is_core': False,
                        'price_usd': default_op.get('price_usd', 0.50),
                        'base_cost_usd': default_op.get('base_cost_usd', 0.20),
                        'operator': default_op.get('operator_name', 'Server Route 1 (Primary)'),
                        'operator_id': default_op.get('operator_id', 1),
                        'catalog_product_id': default_op.get('catalog_product_id'),
                        'cheapest_product_id': default_op.get('cheapest_product_id'),
                        'operators': processed_ops,
                        'available': sum(op.get('available', 0) for op in processed_ops)
                    })
            except Exception as e:
                print(f"[SIMProviderService] Error loading usa_other_services.json: {e}")

        if apply_markup:
            cls._cached_smscode_us_services_raw = services_list
        return services_list

    @classmethod
    def get_5sim_us_services(cls, apply_markup: bool = True) -> list:
        """Alias for get_smscode_us_services."""
        return cls.get_smscode_us_services(apply_markup=apply_markup)

    @classmethod
    def _load_raw_textverified_us_services(cls) -> list:
        if cls._cached_textverified_us_services_raw is not None:
            return cls._cached_textverified_us_services_raw

        import json
        import os
        data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'textverified_us_services.json')
        if os.path.exists(data_path):
            try:
                with open(data_path, 'r', encoding='utf-8') as f:
                    cls._cached_textverified_us_services_raw = json.load(f)
                    return cls._cached_textverified_us_services_raw
            except Exception as e:
                print(f"[SIMProviderService] Error loading textverified_us_services.json: {e}")

        return cls.TEXTVERIFIED_US_SERVICES

    @classmethod
    def get_textverified_us_services(cls, apply_markup: bool = True) -> list:
        """Loads full catalog of TextVerified USA services with dynamic admin markup and price overrides applied."""
        raw_list = cls._load_raw_textverified_us_services()
        if not apply_markup:
            return raw_list

        try:
            from app.services.settings_service import SettingsService
            pct, floor = SettingsService.get_textverified_markup()
            all_overrides = SettingsService.get_price_overrides()
            overrides = {
                o['service_code'].strip().lower(): float(o['override_price_usd'])
                for o in all_overrides
                if o.get('provider_type') in ('textverified', 'all') and o.get('is_active', True) and o.get('service_code')
            }
        except Exception:
            pct, floor = 25.0, 0.50
            overrides = {}

        mult = 1.0 + (pct / 100.0)
        marked = []
        for s in raw_list:
            item = dict(s)
            base = float(s.get('price_usd') or 0.50)
            item['base_cost_usd'] = base
            sc = str(s.get('service_code') or '').strip().lower()
            if sc in overrides:
                item['price_usd'] = overrides[sc]
                item['is_override'] = True
            else:
                item['price_usd'] = round(max(base * mult, base + floor), 2)
            marked.append(item)
        return marked

    @classmethod
    def get_us_canada_config(cls) -> dict:
        """Returns the packages and service offerings for the US page."""
        return {
            'packages': cls.US_CANADA_PACKAGES,
            'basic_services': cls.get_smscode_us_services(),
            'premium_services': cls.get_textverified_us_services(),
        }

    @classmethod
    def purchase_us_canada_number(
        cls,
        country_code: str = 'US',
        service_name: str = 'WhatsApp',
        package_id: str = 'basic_pool',
        provider_id: str = 'any',
        price: float = None,
        service_code: str = None,
        operator_id: int = None,
        catalog_product_id: int = None,
        product_id: int = None
    ) -> dict:
        """Purchases a US virtual number:
        - basic_pool: routes through SMSCode with selected operator route (T-Mobile, AT&T, Verizon, etc.)
        - reliable_non_voip: routes from dedicated cellular provider
        """
        import random
        import uuid

        cc_clean = 'US'
        country_name = 'United States'
        country_slug = 'usa'

        # Match package
        pkg = next((p for p in cls.US_CANADA_PACKAGES if p['id'] == package_id), cls.US_CANADA_PACKAGES[0])
        order_ref = f"TGS-USCA-{uuid.uuid4().hex[:6].upper()}"

        # Resolve service code
        if not service_code:
            svc_clean = service_name.strip()
            svc_lookup = svc_clean.lower().split('/')[0].strip()
            s_meta = cls.SERVICE_SLUGS.get(svc_lookup)
            service_code = s_meta['code'] if s_meta else svc_lookup.replace(' ', '').lower()
        else:
            svc_clean = service_name.strip()

        # 1. Reliable Non-VoIP / Dedicated Cellular line
        if package_id == 'reliable_non_voip':
            charge_price = float(price) if price else 2.50
            tv_client = cls.get_textverified_client()
            if tv_client:
                try:
                    from textverified import NewVerificationRequest, ReservationCapability
                    tv_svc = service_code
                    if service_code in ('google', 'gmail'): tv_svc = 'google'
                    elif service_code in ('whatsapp', 'whatsapp_business'): tv_svc = 'whatsapp'

                    req = NewVerificationRequest(service_name=tv_svc, capability=ReservationCapability.SMS)
                    ver = tv_client.verifications.create(req)
                    exp_iso = None
                    if hasattr(ver, 'ends_at') and ver.ends_at:
                        exp_iso = ver.ends_at.isoformat() if hasattr(ver.ends_at, 'isoformat') else str(ver.ends_at)
                    return {
                        'success': True,
                        'order_reference': order_ref,
                        'phone_number': ver.number,
                        'provider_order_id': f"TXTV-{ver.id}",
                        'country_code': cc_clean,
                        'country_name': country_name,
                        'service_name': f"{svc_clean} (Reliable)",
                        'package_id': 'reliable_non_voip',
                        'package_name': 'Reliable Package',
                        'provider_line': 'Dedicated Cellular',
                        'price': charge_price,
                        'status': 'pending',
                    }
                except Exception as e:
                    print(f"[SIMProviderService] Dedicated carrier line error: {e}")
                    return {'success': False, 'message': 'Dedicated cellular line temporarily busy. Please try again in a moment.'}
            else:
                # Sandbox / demo fallback if API keys are pending
                rand_num = f"+1 (800) {random.randint(200, 899)}-{random.randint(1000, 9999)}"
                return {
                    'success': True,
                    'order_reference': order_ref,
                    'phone_number': rand_num,
                    'provider_order_id': f"TXTV-DEMO-{uuid.uuid4().hex[:8].upper()}",
                    'country_code': cc_clean,
                    'country_name': country_name,
                    'service_name': f"{svc_clean} (Reliable)",
                    'package_id': 'reliable_non_voip',
                    'package_name': 'Reliable Package',
                    'provider_line': 'Dedicated Cellular',
                    'price': charge_price,
                    'status': 'pending',
                }

        # 2. Basic Pool (Routing SMSCode with selected operator route)
        client = cls.get_client()

        # Parse operator_id from provider_id if needed
        resolved_op_id = operator_id
        if resolved_op_id is None and provider_id and str(provider_id).isdigit():
            try:
                resolved_op_id = int(provider_id)
            except Exception:
                pass

        # Look up operator metadata from usa_core_services.json
        matched_op = None
        matched_catalog_pid = None
        matched_product_id = None
        op_display_name = 'T-Mobile'

        try:
            import json
            data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'usa_core_services.json')
            if os.path.exists(data_path):
                with open(data_path, 'r', encoding='utf-8') as f:
                    core_data = json.load(f)

                # Match service key
                s_key = service_code
                if s_key not in core_data:
                    for k in core_data:
                        if k.startswith(s_key) or s_key in k:
                            s_key = k
                            break

                svc_entry = core_data.get(s_key)
                if not svc_entry:
                    other_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'usa_other_services.json')
                    if os.path.exists(other_path):
                        with open(other_path, 'r', encoding='utf-8') as f:
                            other_data = json.load(f)
                        s_key = service_code
                        if s_key not in other_data:
                            for k in other_data:
                                if k.startswith(s_key) or s_key in k:
                                    s_key = k
                                    break
                        svc_entry = other_data.get(s_key)

                if svc_entry and svc_entry.get('operators'):
                    ops = svc_entry['operators']
                    if resolved_op_id is not None:
                        for op in ops:
                            if op.get('operator_id') == resolved_op_id:
                                matched_op = op
                                break
                    if not matched_op:
                        # Default to T-Mobile (125) or cheapest route
                        for op in ops:
                            if op.get('operator_id') == 125:
                                matched_op = op
                                break
                        if not matched_op and ops:
                            matched_op = ops[0]

                    if matched_op:
                        resolved_op_id = matched_op.get('operator_id')
                        matched_catalog_pid = matched_op.get('catalog_product_id')
                        matched_product_id = matched_op.get('cheapest_product_id')
                        op_display_name = matched_op.get('operator_name', 'Server Route 1 (Primary)')
        except Exception as e:
            print(f"[SIMProviderService] Error matching operator tier: {e}")

        if catalog_product_id:
            matched_catalog_pid = int(catalog_product_id)
        if product_id:
            matched_product_id = int(product_id)

        charge_price = float(price) if price else 1.25

        if client.is_configured:
            # 1. Try order creation with exact cheapest product tier
            buy_res = client.create_order(
                catalog_product_id=matched_catalog_pid,
                product_id=matched_product_id,
                operator_id=resolved_op_id,
                policy='cheapest'
            )
            # 2. If exact product is out of stock, fallback to general activation
            if not buy_res.get('success'):
                buy_res = client.buy_activation(
                    country_code=cc_clean,
                    service_code=service_code,
                    operator_id=resolved_op_id
                )

            if buy_res.get('success'):
                allocated_op = buy_res.get('operator') or op_display_name
                return {
                    'success': True,
                    'order_reference': order_ref,
                    'phone_number': buy_res.get('phone_number'),
                    'provider_order_id': buy_res.get('provider_order_id'),
                    'country_code': cc_clean,
                    'country_name': country_name,
                    'service_name': f"{svc_clean} (Basic)",
                    'package_id': 'basic_pool',
                    'package_name': 'Basic Package',
                    'provider_line': allocated_op,
                    'price': charge_price,
                    'status': 'pending',
                }
            else:
                return {'success': False, 'message': buy_res.get('message', 'No numbers currently available on this server route. Please choose another route.')}

        # Sandbox / demo mode fallback
        sim_phone = f"+1 555-{random.randint(100, 999)}-{random.randint(1000, 9999)}"
        return {
            'success': True,
            'order_reference': order_ref,
            'phone_number': sim_phone,
            'provider_order_id': f"SIM-{uuid.uuid4().hex[:8].upper()}",
            'country_code': cc_clean,
            'country_name': country_name,
            'service_name': f"{svc_clean} (Basic)",
            'package_id': 'basic_pool',
            'package_name': 'Basic Package',
            'provider_line': op_display_name,
            'price': charge_price,
            'status': 'pending',
        }

    @classmethod
    def reactivate_order(cls, order_id: str, user_id: str = None) -> dict:
        """Reactivates a previously completed/expired verification line so a new OTP can be received.
        Supported on TextVerified dedicated cellular lines.
        """
        # Find order in DB
        admin = get_supabase_admin()
        order = None
        if admin:
            try:
                import uuid
                is_valid_uuid = False
                try:
                    uuid.UUID(str(order_id))
                    is_valid_uuid = True
                except (ValueError, TypeError):
                    is_valid_uuid = False

                if is_valid_uuid:
                    q = admin.table('sim_orders').select('*').or_(f"id.eq.{order_id},order_reference.eq.{order_id}")
                else:
                    q = admin.table('sim_orders').select('*').eq('order_reference', order_id)

                if user_id and user_id != 'demo-user-id':
                    try:
                        uuid.UUID(str(user_id))
                        q = q.eq('user_id', user_id)
                    except (ValueError, TypeError):
                        pass
                res = q.limit(1).execute()
                if res.data and len(res.data) > 0:
                    order = res.data[0]
            except Exception as e:
                print(f"[SIMProviderService] DB lookup error during reactivate: {e}")

        if not order:
            for o in mock_db.sim_orders:
                if o.get('id') == order_id or o.get('order_reference') == order_id:
                    if not user_id or o.get('user_id') == user_id or user_id == 'demo-user-id':
                        order = o
                        break

        if not order:
            return {'success': False, 'message': 'Order not found.'}

        # Reactivation is only permitted if this number line previously received an OTP
        has_had_otp = bool(order.get('sms_code')) or order.get('status') in ('received', 'completed')
        if not has_had_otp and admin and order.get('id'):
            try:
                sms_chk = admin.table('sim_sms_messages').select('id').eq('order_id', str(order.get('id'))).limit(1).execute()
                if sms_chk.data and len(sms_chk.data) > 0:
                    has_had_otp = True
            except Exception:
                pass

        if not has_had_otp:
            return {
                'success': False,
                'message': 'Reactivation is only available after a number has received an initial verification OTP code.'
            }

        prov_order_id = str(order.get('provider_order_id') or '')

        # TextVerified order reactivation (Configurable in Admin Settings)
        if prov_order_id.startswith('TXTV-'):
            from app.services.db_service import DBService
            from app.services.settings_service import SettingsService
            tv_id = prov_order_id[5:]
            try:
                REACTIVATION_FEE = SettingsService.get_reactivation_fee()
                ngn_rate = SettingsService.get_usd_ngn_rate()
            except Exception:
                REACTIVATION_FEE = 1.00
                ngn_rate = 1600.00
            fee_deducted = False

            # Demo order reactivation
            if tv_id.startswith('DEMO-'):
                if user_id:
                    deduct_res = DBService.deduct_wallet_balance(
                        user_id=user_id,
                        amount=REACTIVATION_FEE,
                        reference=f"REACT-{uuid.uuid4().hex[:8].upper()}",
                        description=f"Number Reactivation ({order.get('service_name', 'SIM')})",
                        metadata={'order_reference': order.get('order_reference'), 'type': 'reactivation'},
                        order_id=order.get('id')
                    )
                    if not deduct_res.get('success'):
                        fee_ngn = REACTIVATION_FEE * ngn_rate
                        return {
                            'success': False,
                            'message': deduct_res.get('message') or f"Insufficient wallet balance. Reactivation costs ${REACTIVATION_FEE:.2f} (₦{fee_ngn:,.2f}). Please deposit funds to continue."
                        }
                import datetime
                demo_expires = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=20)).isoformat()
                cls._reset_order_for_new_otp(order.get('id') or order.get('order_reference') or order_id, admin, expires_at=demo_expires)
                return {
                    'success': True,
                    'message': f'Number reactivated successfully (${REACTIVATION_FEE:.2f})! Line is now open for your new OTP code.',
                    'order_reference': order.get('order_reference')
                }

            tv_client = cls.get_textverified_client()
            if not tv_client:
                return {'success': False, 'message': 'Verification service temporarily unavailable.'}

            # --- STEP 1: CHECK IF CARRIER LINE IS CURRENTLY ALREADY ACTIVE / WAITING FOR OTP ---
            expires_at_iso = None
            try:
                v_chk = tv_client.verifications.details(tv_id)
                chk_st = str(getattr(v_chk, 'state', '')).lower()
                if any(s in chk_st for s in ['pending', 'active', 'open', 'reactivated']):
                    if hasattr(v_chk, 'ends_at') and v_chk.ends_at:
                        expires_at_iso = v_chk.ends_at.isoformat() if hasattr(v_chk.ends_at, 'isoformat') else str(v_chk.ends_at)
                    cls._reset_order_for_new_otp(order.get('id') or order.get('order_reference') or order_id, admin, expires_at=expires_at_iso)
                    return {
                        'success': True,
                        'message': 'Number is reactivated and waiting for your new OTP code.',
                        'order_reference': order.get('order_reference')
                    }
            except Exception as ex_chk:
                print(f"[SIMProviderService] TextVerified details check note: {ex_chk}")

            # --- STEP 2: DEDUCT REACTIVATION FEE FROM USER WALLET ---
            if user_id:
                deduct_res = DBService.deduct_wallet_balance(
                    user_id=user_id,
                    amount=REACTIVATION_FEE,
                    reference=f"REACT-{uuid.uuid4().hex[:8].upper()}",
                    description=f"Number Reactivation ({order.get('service_name', 'SIM')})",
                    metadata={'order_reference': order.get('order_reference'), 'type': 'reactivation'},
                    order_id=order.get('id')
                )
                if not deduct_res.get('success'):
                    fee_ngn = REACTIVATION_FEE * ngn_rate
                    return {
                        'success': False,
                        'message': deduct_res.get('message') or f"Insufficient wallet balance. Reactivation costs ${REACTIVATION_FEE:.2f} (₦{fee_ngn:,.2f}). Please deposit funds to continue."
                    }
                fee_deducted = True

            # --- STEP 3: EXECUTE REACTIVATION ON TEXTVERIFIED ---
            try:
                success = tv_client.verifications.reactivate(tv_id)
                if success:
                    # Capture exact ends_at duration returned by TextVerified (e.g. 20m, 60m, 120m)
                    try:
                        v_details = tv_client.verifications.details(tv_id)
                        if hasattr(v_details, 'ends_at') and v_details.ends_at:
                            expires_at_iso = v_details.ends_at.isoformat() if hasattr(v_details.ends_at, 'isoformat') else str(v_details.ends_at)
                    except Exception as ed:
                        print(f"[SIMProviderService] Error querying reactivated ends_at: {ed}")

                    cls._reset_order_for_new_otp(order.get('id') or order.get('order_reference') or order_id, admin, expires_at=expires_at_iso)
                    return {
                        'success': True,
                        'message': f'Number reactivated successfully (${REACTIVATION_FEE:.2f})! Line is now open for your new OTP code.',
                        'order_reference': order.get('order_reference')
                    }
                else:
                    if fee_deducted and user_id:
                        DBService.credit_wallet_balance(
                            user_id=user_id,
                            amount=REACTIVATION_FEE,
                            trans_type='refund',
                            reference=f"REF-REACT-{uuid.uuid4().hex[:8].upper()}",
                            description="Refund: Reactivation unavailable",
                            order_id=order.get('id')
                        )
                    cls._mark_reactivation_expired(order.get('id') or order.get('order_reference') or order_id, admin)
                    return {
                        'success': False,
                        'message': 'This number is no longer available for reactivation from carrier. Your wallet has been refunded.',
                        'reactivation_expired': True
                    }
            except Exception as e:
                print(f"[SIMProviderService] TextVerified reactivate error: {e}")
                err_str = str(e).lower()

                # If carrier line is already active or reactivated, reset order to pending and allow user to receive OTP
                if 'already' in err_str and any(w in err_str for w in ['active', 'pending', 'open', 'reactivated']):
                    try:
                        v_details = tv_client.verifications.details(tv_id)
                        if hasattr(v_details, 'ends_at') and v_details.ends_at:
                            expires_at_iso = v_details.ends_at.isoformat() if hasattr(v_details.ends_at, 'isoformat') else str(v_details.ends_at)
                    except Exception:
                        pass
                    cls._reset_order_for_new_otp(order.get('id') or order.get('order_reference') or order_id, admin, expires_at=expires_at_iso)
                    return {
                        'success': True,
                        'message': 'Number is reactivated and waiting for your new OTP code.',
                        'order_reference': order.get('order_reference')
                    }

                # Refund the reactivation fee immediately on carrier failure
                if fee_deducted and user_id:
                    try:
                        DBService.credit_wallet_balance(
                            user_id=user_id,
                            amount=REACTIVATION_FEE,
                            trans_type='refund',
                            reference=f"REF-REACT-{uuid.uuid4().hex[:8].upper()}",
                            description="Refund: Reactivation unavailable",
                            order_id=order.get('id')
                        )
                    except Exception as ex:
                        print(f"[SIMProviderService] Error refunding reactivation fee: {ex}")

                if 'insufficient balance' in err_str or 'insufficientbalance' in err_str:
                    return {'success': False, 'message': 'Carrier service balance is currently low. Please contact support. (Your fee was refunded)'}

                # Carrier slot unavailable / expired / 404 / 400: mark expired so button goes blank
                cls._mark_reactivation_expired(order.get('id') or order.get('order_reference') or order_id, admin)
                return {
                    'success': False,
                    'message': 'This number cannot be reactivated with the carrier. The fee has been refunded to your wallet.',
                    'reactivation_expired': True
                }

        return {'success': False, 'message': 'Reactivation is only supported on Reliable Package numbers.'}

    @classmethod
    def _mark_reactivation_expired(cls, order_id: str, admin=None):
        """Flags an order so the reactivation button disappears permanently."""
        if not admin:
            from app.services.supabase_client import get_supabase_admin
            admin = get_supabase_admin()
        if admin:
            try:
                import uuid
                is_uuid = False
                try:
                    uuid.UUID(str(order_id))
                    is_uuid = True
                except (ValueError, TypeError):
                    is_uuid = False
                q = admin.table('sim_orders').update({'reactivation_expired': True})
                if is_uuid:
                    q = q.eq('id', order_id)
                else:
                    q = q.eq('order_reference', order_id)
                q.execute()
            except Exception as e:
                print(f"[SIMProviderService] _mark_reactivation_expired DB note: {e}")
        for o in mock_db.sim_orders:
            if o.get('id') == order_id or o.get('order_reference') == order_id:
                o['reactivation_expired'] = True
                break

    @classmethod
    def _reset_order_for_new_otp(cls, db_order_id: str, admin=None, expires_at: str = None):
        """Resets order status to pending for a fresh OTP while archiving previous code and tracking reactivation."""
        import datetime
        import uuid
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_iso = now_utc.isoformat()

        if not admin:
            admin = get_supabase_admin()

        if admin:
            try:
                is_valid_uuid = False
                try:
                    uuid.UUID(str(db_order_id))
                    is_valid_uuid = True
                except (ValueError, TypeError):
                    is_valid_uuid = False

                q = admin.table('sim_orders').select('*')
                if is_valid_uuid:
                    q = q.eq('id', db_order_id)
                else:
                    q = q.eq('order_reference', db_order_id)
                cur_res = q.limit(1).execute()
                if cur_res.data:
                    cur_ord = cur_res.data[0]
                    # Ensure previous SMS is safely recorded in sim_sms_messages
                    if cur_ord.get('sms_code'):
                        admin.table('sim_sms_messages').insert({
                            'order_id': cur_ord['id'],
                            'sender': cur_ord.get('service_name', 'Verification'),
                            'sms_code': cur_ord['sms_code'],
                            'full_text': cur_ord.get('full_sms_text', f"Code: {cur_ord['sms_code']}"),
                            'received_at': cur_ord.get('updated_at') or now_iso
                        }).execute()
            except Exception as ex:
                print(f"[SIMProviderService] archiving prev sms note: {ex}")

        # Note: sim_orders_order_type_check constraint permits 'activation'/'hosting'.
        # Reactivation is tracked via full_sms_text and status='pending'.
        cur_order_type = 'activation'
        if cur_res and cur_res.data:
            cur_order_type = cur_res.data[0].get('order_type') or 'activation'

        update_payload = {
            'status': 'pending',
            'order_type': cur_order_type,
            'sms_code': None,
            'full_sms_text': 'Line reactivated - waiting for new verification code...',
            'created_at': now_iso,
            'updated_at': now_iso
        }
        if expires_at:
            update_payload['expires_at'] = expires_at

        if admin:
            try:
                if is_valid_uuid:
                    admin.table('sim_orders').update(update_payload).eq('id', db_order_id).execute()
                else:
                    admin.table('sim_orders').update(update_payload).eq('order_reference', db_order_id).execute()
            except Exception as e:
                print(f"[SIMProviderService] Update order error during reactivate reset: {e}")

        for o in mock_db.sim_orders:
            if o.get('id') == db_order_id or o.get('order_reference') == db_order_id:
                o['status'] = 'pending'
                o['sms_code'] = None
                o['full_sms_text'] = 'Line reactivated - waiting for new verification code...'
                o['created_at'] = now_iso
                o['updated_at'] = now_iso
                if expires_at:
                    o['expires_at'] = expires_at
                break

    # =========================================================================
    # NUMBER RENTALS (DEDICATED LONG-TERM CARRIER RESERVATIONS)
    # =========================================================================
    RENTAL_SERVICES = [
        {
            'code': 'allservices',
            'name': 'Universal Number (All Services)',
            'icon': 'shield',
            'badge': 'Best Value',
            'badge_class': 'badge-brand',
            'description': 'One dedicated US number that receives OTPs from WhatsApp, Telegram, Google, Banks, PayPal, Apple, and all 2,000+ platforms simultaneously.',
            'base_pricing': {3: 6.00, 7: 7.00, 14: 8.00, 30: 10.00}
        },
        {
            'code': 'whatsapp',
            'name': 'WhatsApp / Business',
            'icon': 'whatsapp',
            'badge': 'Popular',
            'badge_class': 'badge-success',
            'description': 'Dedicated non-VoIP carrier SIM exclusively reserved for your WhatsApp or WhatsApp Business account for the entire duration.',
            'base_pricing': {3: 2.40, 7: 3.00, 14: 4.00, 30: 4.80}
        },
        {
            'code': 'telegram',
            'name': 'Telegram Messenger',
            'icon': 'telegram',
            'badge': 'High Demand',
            'badge_class': 'badge-info',
            'description': 'Reserved cellular line dedicated to Telegram account login, re-verifications, and multi-device auth.',
            'base_pricing': {3: 3.00, 7: 3.50, 14: 5.00, 30: 6.40}
        },
        {
            'code': 'google',
            'name': 'Google / Gmail / YouTube',
            'icon': 'google',
            'badge': 'Recommended',
            'badge_class': 'badge-warning',
            'description': 'Guaranteed cellular line for Google Account 2FA, workspace recovery, and long-term verification.',
            'base_pricing': {3: 2.20, 7: 2.40, 14: 3.00, 30: 3.60}
        },
        {
            'code': 'openai',
            'name': 'OpenAI / ChatGPT',
            'icon': 'bolt',
            'badge': 'AI Route',
            'badge_class': 'badge-neutral',
            'description': 'Real cellular number reserved for OpenAI, ChatGPT Plus, and API developer account validations.',
            'base_pricing': {3: 1.90, 7: 2.00, 14: 2.80, 30: 3.60}
        },
        {
            'code': 'paypal',
            'name': 'PayPal / Venmo',
            'icon': 'credit-card',
            'badge': 'Financial',
            'badge_class': 'badge-neutral',
            'description': 'Dedicated Non-VoIP carrier number matching strict security screening on financial platforms.',
            'base_pricing': {3: 2.40, 7: 2.90, 14: 3.80, 30: 4.60}
        },
        {
            'code': 'facebook',
            'name': 'Facebook / Instagram / Threads',
            'icon': 'globe',
            'badge': 'Social',
            'badge_class': 'badge-neutral',
            'description': 'Dedicated line for Meta platforms, Instagram business logins, and account verification.',
            'base_pricing': {3: 2.20, 7: 2.60, 14: 3.50, 30: 4.20}
        },
        {
            'code': 'apple',
            'name': 'Apple ID / iCloud',
            'icon': 'shield',
            'badge': 'Apple',
            'badge_class': 'badge-neutral',
            'description': 'Real AT&T/Verizon cellular route for Apple ID two-factor authentication and device setup.',
            'base_pricing': {3: 2.50, 7: 3.00, 14: 4.00, 30: 5.00}
        },
        {
            'code': 'twitter',
            'name': 'Twitter / X',
            'icon': 'twitter',
            'badge': 'Social',
            'badge_class': 'badge-neutral',
            'description': 'Dedicated verification line for Twitter / X account creation and premium subscriptions.',
            'base_pricing': {3: 2.00, 7: 2.50, 14: 3.20, 30: 4.00}
        },
        {
            'code': 'microsoft',
            'name': 'Microsoft / Outlook / Office',
            'icon': 'grid',
            'badge': 'Productivity',
            'badge_class': 'badge-neutral',
            'description': 'Reserved phone number for Microsoft Account security verification and Office 365 sign-ins.',
            'base_pricing': {3: 2.00, 7: 2.40, 14: 3.20, 30: 3.80}
        }
    ]

    @classmethod
    def get_rental_catalog(cls) -> list:
        """Returns the rental catalog with wholesale and retail prices calculated for 3, 7, 14, and 30 days,
        incorporating live wholesale database costs and admin custom selling price overrides.
        """
        from app.services.settings_service import SettingsService
        try:
            pct, floor = SettingsService.get_textverified_markup()
            ngn_rate = SettingsService.get_usd_ngn_rate()
        except Exception:
            pct, floor = 25.0, 0.50
            ngn_rate = 1600.00

        mult = 1.0 + (pct / 100.0)
        try:
            db_pricing = SettingsService.get_rental_pricing_map()
        except Exception as e:
            print(f"[SIMProviderService] rental pricing DB fetch error: {e}")
            db_pricing = {}

        catalog = []
        for svc in cls.RENTAL_SERVICES:
            item = dict(svc)
            code = svc['code'].strip().lower()
            pricing = {}
            for days, default_cost in svc['base_pricing'].items():
                db_item = db_pricing.get((code, days))
                if db_item and db_item.get('wholesale_price_usd'):
                    wholesale_cost = float(db_item['wholesale_price_usd'])
                else:
                    wholesale_cost = float(default_cost)

                custom_price = db_item.get('custom_price_usd') if db_item else None
                if custom_price is not None and float(custom_price) > 0:
                    retail_usd = round(float(custom_price), 2)
                    is_custom = True
                else:
                    retail_usd = round(max(wholesale_cost * mult, wholesale_cost + floor), 2)
                    is_custom = False

                retail_ngn = round(retail_usd * ngn_rate, 2)
                pricing[str(days)] = {
                    'days': days,
                    'base_cost_usd': wholesale_cost,
                    'retail_usd': retail_usd,
                    'retail_ngn': retail_ngn,
                    'is_custom': is_custom,
                    'custom_price_usd': custom_price,
                    'formatted_usd': f"${retail_usd:.2f}",
                    'formatted_ngn': f"₦{retail_ngn:,.2f}"
                }
            item['pricing'] = pricing
            catalog.append(item)
        return catalog

    @classmethod
    def purchase_rental(
        cls,
        user_id: str,
        service_code: str,
        duration_days: int = 3
    ) -> dict:
        """Purchases a dedicated long-term virtual number rental:
        - Locks carrier line for 3, 7, 14, or 30 days
        - Deducts wallet balance atomically
        - Stores in sim_rentals
        """
        import uuid
        import datetime
        from app.services.db_service import DBService
        from app.services.settings_service import SettingsService

        duration_map = {
            3: ('THREE_DAY', 3),
            7: ('SEVEN_DAY', 7),
            14: ('FOURTEEN_DAY', 14),
            30: ('THIRTY_DAY', 30)
        }
        tier_info = duration_map.get(int(duration_days))
        if not tier_info:
            return {'success': False, 'message': 'Invalid duration. Choose 3, 7, 14, or 30 days.'}

        tier_name, days = tier_info
        catalog = cls.get_rental_catalog()
        svc_clean = service_code.strip().lower()
        matched = next((s for s in catalog if s['code'].lower() == svc_clean), None)
        if not matched:
            matched = catalog[0]  # Fallback to universal allservices

        price_info = matched['pricing'].get(str(days))
        retail_usd = price_info['retail_usd']
        retail_ngn = price_info['retail_ngn']
        base_cost = price_info['base_cost_usd']
        rental_ref = f"TGS-RNT-{uuid.uuid4().hex[:6].upper()}"

        # 1. Check wallet balance
        wallet = DBService.get_wallet(user_id)
        cur_bal = float(wallet.get('balance', 0.00))
        if cur_bal < retail_usd:
            return {
                'success': False,
                'message': f"Insufficient wallet balance (${cur_bal:.2f}). This {days}-day rental costs ${retail_usd:.2f} (₦{retail_ngn:,.2f}). Please top up your wallet."
            }

        # 2. Allocate with TextVerified Reservations API
        tv_client = cls.get_textverified_client()
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        phone = None
        prov_res_id = None
        ends_at_iso = (now_utc + datetime.timedelta(days=days)).isoformat()

        if tv_client:
            try:
                from textverified import NewRentalRequest, RentalDuration, ReservationCapability, NumberType
                req = NewRentalRequest(
                    allow_back_order_reservations=False,
                    duration=RentalDuration[tier_name],
                    is_renewable=False,
                    number_type=NumberType.MOBILE,
                    service_name=matched['code'],
                    capability=ReservationCapability.SMS
                )
                sale = tv_client.reservations.create(req)
                if sale and sale.reservations:
                    res_obj = sale.reservations[0]
                    prov_res_id = res_obj.id
                    try:
                        details = tv_client.reservations.nonrenewable_details(res_obj.id)
                        phone = details.number
                        if hasattr(details, 'ends_at') and details.ends_at:
                            ends_at_iso = details.ends_at.isoformat() if hasattr(details.ends_at, 'isoformat') else str(details.ends_at)
                    except Exception as ed:
                        print(f"[SIMProviderService] rental details fetch note: {ed}")
            except Exception as e:
                print(f"[SIMProviderService] TextVerified rental create error: {e}")
                err_str = str(e).lower()
                if 'insufficient balance' in err_str:
                    return {'success': False, 'message': 'Carrier inventory is updating. Please try again shortly or contact support.'}
                return {'success': False, 'message': 'No dedicated carrier lines are currently available for this service tier. Please select another duration.'}

        # Sandbox / Demo fallback if credentials are pending
        if not phone:
            import random
            phone = f"+1 (202) {random.randint(200, 899)}-{random.randint(1000, 9999)}"
            prov_res_id = f"DEMO-RNT-{uuid.uuid4().hex[:8].upper()}"

        # 3. Deduct wallet balance
        deduct_res = DBService.deduct_wallet_balance(
            user_id=user_id,
            amount=retail_usd,
            reference=f"RNT-{uuid.uuid4().hex[:8].upper()}",
            description=f"Number Rental ({matched['name']} - {days} Days)",
            metadata={'rental_reference': rental_ref, 'service_code': matched['code'], 'days': days}
        )
        if not deduct_res.get('success'):
            return {'success': False, 'message': deduct_res.get('message', 'Failed to deduct wallet balance.')}

        # 4. Save to database
        rental_data = {
            'rental_reference': rental_ref,
            'provider': 'textverified',
            'provider_reservation_id': prov_res_id,
            'service_code': matched['code'],
            'service_name': matched['name'],
            'phone_number': phone,
            'country_code': 'US',
            'country_name': 'United States',
            'duration_days': days,
            'duration_tier': tier_name,
            'provider_cost': base_cost,
            'user_cost': retail_usd,
            'user_cost_ngn': retail_ngn,
            'profit_margin': round(retail_usd - base_cost, 2),
            'status': 'active',
            'starts_at': now_utc.isoformat(),
            'expires_at': ends_at_iso,
            'auto_renew': False
        }
        saved = DBService.create_rental(user_id, rental_data)

        # 5. Trigger user notification
        try:
            DBService.create_user_notification(
                user_id=user_id,
                title=f"{matched['name']} Dedicated Number Rented",
                message=f"Your dedicated line {phone} is active for {days} days. You can receive unlimited verification codes during this period.",
                type="purchase",
                link="/sims/rentals"
            )
        except Exception:
            pass

        return {
            'success': True,
            'rental_reference': rental_ref,
            'phone_number': phone,
            'service_name': matched['name'],
            'duration_days': days,
            'expires_at': ends_at_iso,
            'user_cost': retail_usd,
            'message': f"Dedicated number {phone} rented successfully for {days} days!"
        }

    @classmethod
    def check_rental_sms(cls, rental_id: str) -> dict:
        """Polls TextVerified for all SMS messages received on a rental line."""
        from app.services.db_service import DBService
        rental = DBService.get_rental_by_id(user_id=None, rental_id=rental_id)
        if not rental:
            return {'success': False, 'message': 'Rental not found.', 'messages': []}

        phone_number = rental.get('phone_number')
        prov_res_id = str(rental.get('provider_reservation_id') or '')
        tv_client = cls.get_textverified_client()
        new_count = 0

        if tv_client and prov_res_id and not prov_res_id.startswith('DEMO-') and phone_number:
            try:
                sms_list = list(tv_client.sms.list(to_number=phone_number))
                for s in sms_list:
                    code = getattr(s, 'parsed_code', None)
                    text = getattr(s, 'sms_content', None) or (f"Your verification code is: {code}" if code else "New SMS received")
                    sender = getattr(s, 'service_name', None) or rental.get('service_name', 'Verification')
                    DBService.record_rental_sms(rental.get('id') or rental_id, code, text, sender=sender)
                    new_count += 1
            except Exception as e:
                print(f"[SIMProviderService] check_rental_sms error: {e}")

        # Fetch all messages from DB
        messages = DBService.get_rental_messages(rental.get('id') or rental_id)
        return {
            'success': True,
            'messages': messages,
            'new_count': new_count,
            'phone_number': phone_number,
            'service_name': rental.get('service_name')
        }

