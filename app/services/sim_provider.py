"""Virtual SIM Provider Adapter for Tgsims.
Integrates 5sim API with transparent retail markups, slug mapping, error translation,
and complete white-labeling (no third-party provider names disclosed to end users).
"""

import os
import requests
import uuid
import datetime
from app.config import Config
from app.services.supabase_client import get_supabase_admin, mock_db


class FiveSimClient:
    """Low-level HTTP client for 5sim REST API."""

    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = (api_key or getattr(Config, 'FIVESIM_API_KEY', '') or os.getenv('FIVESIM_API_KEY', '')).strip()
        self.base_url = (base_url or getattr(Config, 'FIVESIM_BASE_URL', 'https://5sim.net/v1') or os.getenv('FIVESIM_BASE_URL', 'https://5sim.net/v1')).strip().rstrip('/')

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 20)

    def _headers(self) -> dict:
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Accept': 'application/json'
        }

    def get_profile(self) -> dict:
        """Fetch account balance, rating, and active orders."""
        if not self.is_configured:
            return {'success': False, 'balance': 0.0, 'message': 'API key not configured'}
        try:
            r = requests.get(f"{self.base_url}/user/profile", headers=self._headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                return {
                    'success': True,
                    'balance': float(data.get('balance', 0.0)),
                    'rating': data.get('rating', 0),
                    'active_orders': data.get('total_active_orders', 0)
                }
            return {'success': False, 'message': r.text, 'status_code': r.status_code}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def get_products(self, country_slug: str, operator: str = 'any') -> dict:
        """Fetch product list, inventory count, and cost for a country."""
        try:
            r = requests.get(f"{self.base_url}/guest/products/{country_slug}/{operator}", headers=self._headers(), timeout=12)
            if r.status_code == 200:
                return {'success': True, 'products': r.json()}
            return {'success': False, 'message': r.text, 'status_code': r.status_code}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def buy_activation(self, country_slug: str, service_code: str, operator: str = 'any') -> dict:
        """Buy a virtual number activation. Returns order details or error."""
        if not self.is_configured:
            return {'success': False, 'message': 'Provider client not configured'}
        try:
            url = f"{self.base_url}/user/buy/activation/{country_slug}/{operator}/{service_code}"
            r = requests.get(url, headers=self._headers(), timeout=15)
            
            if r.status_code == 200:
                data = r.json()
                return {
                    'success': True,
                    'provider_order_id': str(data.get('id', '')),
                    'phone_number': data.get('phone', ''),
                    'operator': data.get('operator', operator),
                    'provider_cost': float(data.get('price', 0.0)),
                    'expires_at': data.get('expires'),
                    'raw': data
                }
            
            # Error mapping
            err_text = r.text.lower()
            if 'no free phones' in err_text:
                msg = 'No numbers are currently available for this service. Please choose another country or try again shortly.'
            elif 'not enough' in err_text or 'balance' in err_text:
                msg = 'Service temporarily undergoing routine replenishment. Please try again in a moment.'
            else:
                msg = 'Unable to allocate a number at this moment. Please select another country or service.'

            return {'success': False, 'message': msg, 'raw_error': r.text}
        except Exception as e:
            return {'success': False, 'message': 'Network timeout while contacting verification server. Please try again.'}

    def check_order(self, provider_order_id: str) -> dict:
        """Check order status and incoming SMS messages."""
        if not self.is_configured or not provider_order_id:
            return {'success': False, 'has_sms': False}
        try:
            url = f"{self.base_url}/user/check/{provider_order_id}"
            r = requests.get(url, headers=self._headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                sms_list = data.get('sms', []) or []
                status = str(data.get('status', 'PENDING')).upper()
                
                latest_code = None
                latest_text = None
                latest_sms_id = None

                if sms_list and len(sms_list) > 0:
                    last_sms = sms_list[-1]
                    latest_code = last_sms.get('code')
                    latest_text = last_sms.get('text')
                    latest_sms_id = str(last_sms.get('id', ''))

                return {
                    'success': True,
                    'status': status,
                    'has_sms': bool(latest_code or (sms_list and len(sms_list) > 0)),
                    'sms_code': latest_code,
                    'full_sms': latest_text or (f"Your verification code is: {latest_code}" if latest_code else None),
                    'provider_sms_id': latest_sms_id,
                    'sms_list': sms_list,
                    'phone_number': data.get('phone')
                }
            return {'success': False, 'has_sms': False, 'message': r.text}
        except Exception as e:
            return {'success': False, 'has_sms': False, 'message': str(e)}

    def cancel_order(self, provider_order_id: str) -> dict:
        """Cancel an order before receiving SMS (refunds balance)."""
        if not self.is_configured or not provider_order_id:
            return {'success': False, 'message': 'Client not configured'}
        try:
            url = f"{self.base_url}/user/cancel/{provider_order_id}"
            r = requests.get(url, headers=self._headers(), timeout=10)
            if r.status_code == 200:
                return {'success': True, 'data': r.json()}
            return {'success': False, 'message': r.text}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def finish_order(self, provider_order_id: str) -> dict:
        """Mark an order as completed once SMS is received."""
        if not self.is_configured or not provider_order_id:
            return {'success': False, 'message': 'Client not configured'}
        try:
            url = f"{self.base_url}/user/finish/{provider_order_id}"
            r = requests.get(url, headers=self._headers(), timeout=10)
            if r.status_code == 200:
                return {'success': True, 'data': r.json()}
            return {'success': False, 'message': r.text}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def ban_order(self, provider_order_id: str) -> dict:
        """Report number as already registered or banned (refunds balance)."""
        if not self.is_configured or not provider_order_id:
            return {'success': False, 'message': 'Client not configured'}
        try:
            url = f"{self.base_url}/user/ban/{provider_order_id}"
            r = requests.get(url, headers=self._headers(), timeout=10)
            if r.status_code == 200:
                return {'success': True, 'data': r.json()}
            return {'success': False, 'message': r.text}
        except Exception as e:
            return {'success': False, 'message': str(e)}


class SIMProviderService:
    """High-level service interface for Tgsims virtual number purchasing and catalog."""

    # ISO Country Code -> 5sim slug mapping
    COUNTRY_SLUGS = {
        'US': {'slug': 'usa', 'name': 'United States', 'flag': '🇺🇸', 'dial': '+1'},
        'GB': {'slug': 'england', 'name': 'United Kingdom', 'flag': '🇬🇧', 'dial': '+44'},
        'NG': {'slug': 'nigeria', 'name': 'Nigeria', 'flag': '🇳🇬', 'dial': '+234'},
        'CA': {'slug': 'canada', 'name': 'Canada', 'flag': '🇨🇦', 'dial': '+1'},
        'DE': {'slug': 'germany', 'name': 'Germany', 'flag': '🇩🇪', 'dial': '+49'},
        'FR': {'slug': 'france', 'name': 'France', 'flag': '🇫🇷', 'dial': '+33'},
        'NL': {'slug': 'netherlands', 'name': 'Netherlands', 'flag': '🇳🇱', 'dial': '+31'},
        'ES': {'slug': 'spain', 'name': 'Spain', 'flag': '🇪🇸', 'dial': '+34'},
        'IN': {'slug': 'india', 'name': 'India', 'flag': '🇮🇳', 'dial': '+91'},
        'BR': {'slug': 'brazil', 'name': 'Brazil', 'flag': '🇧🇷', 'dial': '+55'},
        'ZA': {'slug': 'southafrica', 'name': 'South Africa', 'flag': '🇿🇦', 'dial': '+27'},
        'GH': {'slug': 'ghana', 'name': 'Ghana', 'flag': '🇬🇭', 'dial': '+233'},
        'KE': {'slug': 'kenya', 'name': 'Kenya', 'flag': '🇰🇪', 'dial': '+254'},
        'RU': {'slug': 'russia', 'name': 'Russia', 'flag': '🇷🇺', 'dial': '+7'}
    }

    # Common service display name -> 5sim service code mapping
    SERVICE_SLUGS = {
        'whatsapp': {'code': 'whatsapp', 'name': 'WhatsApp'},
        'telegram': {'code': 'telegram', 'name': 'Telegram'},
        'google': {'code': 'google', 'name': 'Google / Gmail'},
        'openai': {'code': 'openai', 'name': 'OpenAI / ChatGPT'},
        'chatgpt': {'code': 'openai', 'name': 'OpenAI / ChatGPT'},
        'instagram': {'code': 'instagram', 'name': 'Instagram'},
        'tiktok': {'code': 'tiktok', 'name': 'TikTok'},
        'facebook': {'code': 'facebook', 'name': 'Facebook'},
        'twitter': {'code': 'twitter', 'name': 'Twitter / X'},
        'tinder': {'code': 'tinder', 'name': 'Tinder'},
        'discord': {'code': 'discord', 'name': 'Discord'},
        'snapchat': {'code': 'snapchat', 'name': 'Snapchat'},
        'netflix': {'code': 'netflix', 'name': 'Netflix'},
        'uber': {'code': 'uber', 'name': 'Uber'},
        'apple': {'code': 'apple', 'name': 'Apple'},
        'microsoft': {'code': 'microsoft', 'name': 'Microsoft'},
        'amazon': {'code': 'amazon', 'name': 'Amazon'},
        'bank verification': {'code': 'other', 'name': 'Bank Verification'}
    }

    _client = None

    @classmethod
    def get_textverified_client(cls):
        import os
        try:
            from textverified import TextVerified
        except ImportError:
            return None
        
        api_key = os.getenv('TEXTVERIFIED_API_KEY')
        api_username = os.getenv('TEXTVERIFIED_USERNAME')
        if not api_key or not api_username:
            return None
        try:
            return TextVerified(api_key=api_key, api_username=api_username)
        except Exception as e:
            print(f"[SIMProviderService] Error initializing TextVerified: {e}")
            return None

    @classmethod
    def get_client(cls) -> FiveSimClient:
        if cls._client is None:
            cls._client = FiveSimClient()
        return cls._client

    @classmethod
    def calculate_retail_price(cls, base_cost: float) -> tuple[float, float]:
        """Calculates retail price and profit margin in USD.
        Rule: 35% margin with a minimum profit floor of $0.30 per number.
        """
        if base_cost <= 0:
            return 1.50, 1.50

        # Margin: max(cost * 1.35, cost + 0.30) rounded to 2 decimals
        markup = max(base_cost * 1.35, base_cost + 0.30)
        retail_price = round(markup, 2)
        profit_margin = round(retail_price - base_cost, 4)
        return retail_price, profit_margin

    _cached_catalog = None

    @classmethod
    def get_catalog(cls) -> list:
        """Returns country and service catalog loaded from app/data/catalog.json.
        Covers all 153 countries from 5sim with all platforms and dynamic markups.
        """
        if cls._cached_catalog is not None:
            return cls._cached_catalog

        import json
        json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'catalog.json')
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data and isinstance(data, list) and len(data) > 0:
                        # Filter out US from the other countries catalog
                        filtered_data = [c for c in data if c.get('country_code', '').upper() != 'US']
                        cls._cached_catalog = filtered_data
                        return filtered_data
            except Exception as e:
                print(f"[SIMProviderService] Error reading catalog.json: {e}")

        # Curated fallback countries & services
        return [
            {
                'country_code': 'US',
                'country_name': 'United States',
                'country_slug': 'usa',
                'flag': '🇺🇸',
                'dial': '+1',
                'services': [
                    {'name': 'WhatsApp', 'price': 1.25, 'available': 46790, 'category': 'SMS Verification'},
                    {'name': 'Telegram', 'price': 1.10, 'available': 12500, 'category': 'SMS Verification'},
                    {'name': 'OpenAI / ChatGPT', 'price': 1.40, 'available': 8200, 'category': 'SMS Verification'},
                    {'name': 'Google / Gmail', 'price': 0.95, 'available': 35400, 'category': 'SMS Verification'},
                    {'name': 'Instagram', 'price': 0.85, 'available': 24100, 'category': 'SMS Verification'},
                    {'name': 'Tinder', 'price': 1.20, 'available': 6100, 'category': 'SMS Verification'}
                ]
            }
        ]

    @classmethod
    def purchase_number(cls, country_code: str, service_name: str, operator: str = 'any') -> dict:
        """Allocates a virtual number from 5sim.
        Falls back to local preview mode if API key is not yet configured.
        """
        client = cls.get_client()
        cc_clean = (country_code or 'US').upper().strip()
        svc_clean = (service_name or 'WhatsApp').strip()

        # Map country to 5sim slug
        c_meta = cls.COUNTRY_SLUGS.get(cc_clean)
        if c_meta:
            country_slug = c_meta['slug']
            country_name = c_meta['name']
        else:
            cat = cls.get_catalog()
            matched = next((c for c in cat if c.get('country_code', '').upper() == cc_clean or c.get('country_slug', '').lower() == cc_clean.lower()), None)
            if matched:
                country_slug = matched.get('country_slug', cc_clean.lower())
                country_name = matched.get('country_name', cc_clean)
            else:
                country_slug = cc_clean.lower()
                country_name = cc_clean

        # Map service to 5sim code
        svc_lookup = svc_clean.lower().split('/')[0].strip()
        s_meta = cls.SERVICE_SLUGS.get(svc_lookup)
        if s_meta:
            service_code = s_meta['code']
        else:
            service_code = svc_lookup.replace(' ', '').replace('-', '').lower()

        order_ref = f"TGS-SIM-{uuid.uuid4().hex[:6].upper()}"

        # If 5sim is configured, make real API purchase
        if client.is_configured:
            buy_res = client.buy_activation(country_slug=country_slug, service_code=service_code, operator=operator)
            if not buy_res.get('success'):
                return buy_res

            prov_id = buy_res.get('provider_order_id')
            phone = buy_res.get('phone_number')
            prov_cost = buy_res.get('provider_cost', 0.0)
            retail_price, margin = cls.calculate_retail_price(prov_cost)

            return {
                'success': True,
                'order_reference': order_ref,
                'phone_number': phone,
                'provider_order_id': prov_id,
                'country_code': cc_clean,
                'country_name': country_name,
                'country_slug': country_slug,
                'service_name': svc_clean,
                'service_code': service_code,
                'operator': buy_res.get('operator', operator),
                'provider_cost': prov_cost,
                'retail_price': retail_price,
                'profit_margin': margin,
                'expires_at': buy_res.get('expires_at'),
                'is_esim': False,
                'status': 'pending'
            }

        # Fallback simulation for sandbox / preview before live funding
        prefix = c_meta.get('dial', '+1')
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
            'country_name': c_meta['name'],
            'country_slug': country_slug,
            'service_name': svc_clean,
            'service_code': service_code,
            'operator': operator,
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

        # Find order in DB to get provider_order_id
        admin = get_supabase_admin()
        prov_order_id = None
        if admin:
            try:
                res = admin.table('sim_orders').select('provider_order_id').or_(f"id.eq.{order_id},order_reference.eq.{order_id}").limit(1).execute()
                if res.data and len(res.data) > 0:
                    prov_order_id = res.data[0].get('provider_order_id')
            except Exception:
                pass

        if not prov_order_id:
            for o in mock_db.sim_orders:
                if o.get('id') == order_id or o.get('order_reference') == order_id:
                    prov_order_id = o.get('provider_order_id')
                    break

        if prov_order_id and prov_order_id.startswith('TXTV-'):
            tv_id = prov_order_id[5:]
            tv_client = cls.get_textverified_client()
            if tv_client:
                try:
                    verification = tv_client.verifications.details(tv_id)
                    sms_list = tv_client.sms.list(data=verification)
                    items = list(sms_list)
                    if items:
                        sms = items[0]
                        return {
                            'has_sms': True,
                            'sms_code': sms.parsed_code,
                            'full_sms': sms.sms_content,
                            'provider_sms_id': sms.id
                        }
                    else:
                        return {
                            'has_sms': False,
                            'sms_code': None,
                            'full_sms': None,
                            'status': verification.state.value if hasattr(verification.state, 'value') else str(verification.state)
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
                'Multiple server carrier routes with varying price options',
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
            'description': 'Screened 100% Non-VoIP real cellular lines (AT&T, Verizon, T-Mobile). Dedicated high-reputation lines for WhatsApp, Banking, and OpenAI.',
            'features': [
                '100% Non-VoIP real cellular carrier numbers',
                'Screened unbanned guarantee for WhatsApp & Banking',
                'Dedicated 1-to-1 reliable carrier routing',
                'Instant auto-refund to wallet if no SMS received'
            ],
            'price_range_label': '₦4,000 – ₦6,000',
            'price_range_usd': '$2.50 – $3.75',
        },
    ]

    FIVESIM_US_SERVICES_WITH_ROUTES = [
        # WhatsApp variants (different server routes / price tags)
        {'id': 'whatsapp_v8', 'service_name': 'WhatsApp', 'service_code': 'whatsapp', 'operator': 'virtual8', 'name': 'WhatsApp (Standard Route)', 'quality': 'Economy Pool', 'price_usd': 0.55},
        {'id': 'whatsapp_v63', 'service_name': 'WhatsApp', 'service_code': 'whatsapp', 'operator': 'virtual63', 'name': 'WhatsApp (Enhanced Route)', 'quality': 'Enhanced Route', 'price_usd': 0.95},
        {'id': 'whatsapp_v28', 'service_name': 'WhatsApp', 'service_code': 'whatsapp', 'operator': 'virtual28', 'name': 'WhatsApp (Ultra Clean Route)', 'quality': 'Ultra Route', 'price_usd': 1.85},
        {'id': 'whatsapp_any', 'service_name': 'WhatsApp', 'service_code': 'whatsapp', 'operator': 'any', 'name': 'WhatsApp (Auto-Dynamic Route)', 'quality': 'Dynamic Route', 'price_usd': 1.20},

        # WhatsApp Business variants
        {'id': 'wabiz_v8', 'service_name': 'WhatsApp Business', 'service_code': 'whatsapp', 'operator': 'virtual8', 'name': 'WhatsApp Business (Standard Route)', 'quality': 'Economy Pool', 'price_usd': 0.70},
        {'id': 'wabiz_v63', 'service_name': 'WhatsApp Business', 'service_code': 'whatsapp', 'operator': 'virtual63', 'name': 'WhatsApp Business (Enhanced Route)', 'quality': 'Enhanced Route', 'price_usd': 1.15},
        {'id': 'wabiz_v28', 'service_name': 'WhatsApp Business', 'service_code': 'whatsapp', 'operator': 'virtual28', 'name': 'WhatsApp Business (Ultra Route)', 'quality': 'Ultra Route', 'price_usd': 1.95},

        # Telegram variants
        {'id': 'tg_v8', 'service_name': 'Telegram', 'service_code': 'telegram', 'operator': 'virtual8', 'name': 'Telegram (Standard Route)', 'quality': 'Economy Pool', 'price_usd': 0.60},
        {'id': 'tg_v63', 'service_name': 'Telegram', 'service_code': 'telegram', 'operator': 'virtual63', 'name': 'Telegram (Enhanced Route)', 'quality': 'Enhanced Route', 'price_usd': 1.10},
        {'id': 'tg_v28', 'service_name': 'Telegram', 'service_code': 'telegram', 'operator': 'virtual28', 'name': 'Telegram (Ultra Route)', 'quality': 'Ultra Route', 'price_usd': 1.75},

        # Google / Gmail variants
        {'id': 'google_v8', 'service_name': 'Google / Gmail', 'service_code': 'google', 'operator': 'virtual8', 'name': 'Google / Gmail (Standard Route)', 'quality': 'Economy Pool', 'price_usd': 0.60},
        {'id': 'google_v63', 'service_name': 'Google / Gmail', 'service_code': 'google', 'operator': 'virtual63', 'name': 'Google / Gmail (Enhanced Route)', 'quality': 'Enhanced Route', 'price_usd': 1.15},
        {'id': 'google_v28', 'service_name': 'Google / Gmail', 'service_code': 'google', 'operator': 'virtual28', 'name': 'Google / Gmail (Ultra Route)', 'quality': 'Ultra Route', 'price_usd': 1.65},

        # OpenAI / ChatGPT variants
        {'id': 'openai_v8', 'service_name': 'OpenAI / ChatGPT', 'service_code': 'openai', 'operator': 'virtual8', 'name': 'OpenAI / ChatGPT (Standard Route)', 'quality': 'Economy Pool', 'price_usd': 0.75},
        {'id': 'openai_v63', 'service_name': 'OpenAI / ChatGPT', 'service_code': 'openai', 'operator': 'virtual63', 'name': 'OpenAI / ChatGPT (Enhanced Route)', 'quality': 'Enhanced Route', 'price_usd': 1.40},
        {'id': 'openai_v28', 'service_name': 'OpenAI / ChatGPT', 'service_code': 'openai', 'operator': 'virtual28', 'name': 'OpenAI / ChatGPT (Ultra Route)', 'quality': 'Ultra Route', 'price_usd': 1.85},

        # Claude AI
        {'id': 'claude_any', 'service_name': 'Claude AI', 'service_code': 'claude', 'operator': 'any', 'name': 'Claude AI (Enhanced Route)', 'quality': 'Enhanced Route', 'price_usd': 1.50},

        # Instagram variants
        {'id': 'ig_v8', 'service_name': 'Instagram', 'service_code': 'instagram', 'operator': 'virtual8', 'name': 'Instagram (Standard Route)', 'quality': 'Economy Pool', 'price_usd': 0.55},
        {'id': 'ig_v63', 'service_name': 'Instagram', 'service_code': 'instagram', 'operator': 'virtual63', 'name': 'Instagram (Enhanced Route)', 'quality': 'Enhanced Route', 'price_usd': 0.95},

        # Twitter / X variants
        {'id': 'twitter_v8', 'service_name': 'Twitter / X', 'service_code': 'twitter', 'operator': 'virtual8', 'name': 'Twitter / X (Standard Route)', 'quality': 'Economy Pool', 'price_usd': 0.55},
        {'id': 'twitter_v63', 'service_name': 'Twitter / X', 'service_code': 'twitter', 'operator': 'virtual63', 'name': 'Twitter / X (Enhanced Route)', 'quality': 'Enhanced Route', 'price_usd': 0.95},

        # TikTok variants
        {'id': 'tiktok_v8', 'service_name': 'TikTok', 'service_code': 'tiktok', 'operator': 'virtual8', 'name': 'TikTok (Standard Route)', 'quality': 'Economy Pool', 'price_usd': 0.60},
        {'id': 'tiktok_v63', 'service_name': 'TikTok', 'service_code': 'tiktok', 'operator': 'virtual63', 'name': 'TikTok (Enhanced Route)', 'quality': 'Enhanced Route', 'price_usd': 1.00},

        # Facebook variants
        {'id': 'fb_v8', 'service_name': 'Facebook', 'service_code': 'facebook', 'operator': 'virtual8', 'name': 'Facebook (Standard Route)', 'quality': 'Economy Pool', 'price_usd': 0.55},
        {'id': 'fb_v63', 'service_name': 'Facebook', 'service_code': 'facebook', 'operator': 'virtual63', 'name': 'Facebook (Enhanced Route)', 'quality': 'Enhanced Route', 'price_usd': 0.95},

        # Tinder variants
        {'id': 'tinder_v8', 'service_name': 'Tinder', 'service_code': 'tinder', 'operator': 'virtual8', 'name': 'Tinder (Standard Route)', 'quality': 'Economy Pool', 'price_usd': 0.80},
        {'id': 'tinder_v63', 'service_name': 'Tinder', 'service_code': 'tinder', 'operator': 'virtual63', 'name': 'Tinder (Enhanced Route)', 'quality': 'Enhanced Route', 'price_usd': 1.45},

        # Apple ID / iCloud
        {'id': 'apple_v8', 'service_name': 'Apple ID / iCloud', 'service_code': 'apple', 'operator': 'virtual8', 'name': 'Apple ID / iCloud (Standard Route)', 'quality': 'Economy Pool', 'price_usd': 0.90},
        {'id': 'apple_v63', 'service_name': 'Apple ID / iCloud', 'service_code': 'apple', 'operator': 'virtual63', 'name': 'Apple ID / iCloud (Enhanced Route)', 'quality': 'Enhanced Route', 'price_usd': 1.60},

        # PayPal
        {'id': 'paypal_v8', 'service_name': 'PayPal', 'service_code': 'paypal', 'operator': 'virtual8', 'name': 'PayPal (Standard Route)', 'quality': 'Economy Pool', 'price_usd': 1.10},
        {'id': 'paypal_v63', 'service_name': 'PayPal', 'service_code': 'paypal', 'operator': 'virtual63', 'name': 'PayPal (Enhanced Route)', 'quality': 'Enhanced Route', 'price_usd': 1.85},

        # Amazon
        {'id': 'amazon_v8', 'service_name': 'Amazon', 'service_code': 'amazon', 'operator': 'virtual8', 'name': 'Amazon (Standard Route)', 'quality': 'Economy Pool', 'price_usd': 0.65},
        {'id': 'amazon_v63', 'service_name': 'Amazon', 'service_code': 'amazon', 'operator': 'virtual63', 'name': 'Amazon (Enhanced Route)', 'quality': 'Enhanced Route', 'price_usd': 1.15},

        # Uber / Lyft
        {'id': 'uber_v8', 'service_name': 'Uber / Lyft', 'service_code': 'uber', 'operator': 'virtual8', 'name': 'Uber / Lyft (Standard Route)', 'quality': 'Economy Pool', 'price_usd': 0.70},
        {'id': 'uber_v63', 'service_name': 'Uber / Lyft', 'service_code': 'uber', 'operator': 'virtual63', 'name': 'Uber / Lyft (Enhanced Route)', 'quality': 'Enhanced Route', 'price_usd': 1.25},

        # Discord
        {'id': 'discord_v8', 'service_name': 'Discord', 'service_code': 'discord', 'operator': 'virtual8', 'name': 'Discord (Standard Route)', 'quality': 'Economy Pool', 'price_usd': 0.60},
        {'id': 'discord_v63', 'service_name': 'Discord', 'service_code': 'discord', 'operator': 'virtual63', 'name': 'Discord (Enhanced Route)', 'quality': 'Enhanced Route', 'price_usd': 1.05},

        # Other Platforms
        {'id': 'other_v8', 'service_name': 'Other Platforms', 'service_code': 'other', 'operator': 'virtual8', 'name': 'Other Platforms (Standard Route)', 'quality': 'Economy Pool', 'price_usd': 0.65},
        {'id': 'other_v63', 'service_name': 'Other Platforms', 'service_code': 'other', 'operator': 'virtual63', 'name': 'Other Platforms (Enhanced Route)', 'quality': 'Enhanced Route', 'price_usd': 1.20},
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

    @classmethod
    def get_us_canada_config(cls) -> dict:
        """Returns the packages and service offerings for the US page."""
        return {
            'packages': cls.US_CANADA_PACKAGES,
            'basic_services': cls.FIVESIM_US_SERVICES_WITH_ROUTES,
            'premium_services': cls.TEXTVERIFIED_US_SERVICES,
        }

    @classmethod
    def purchase_us_canada_number(
        cls,
        country_code: str = 'US',
        service_name: str = 'WhatsApp',
        package_id: str = 'basic_pool',
        provider_id: str = 'any',
        price: float = None,
        service_code: str = None
    ) -> dict:
        """Purchases a US virtual number:
        - basic_pool: routes from 5sim with specified operator quality route
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

        # 2. Basic Pool (Routing 5sim with specified operator route)
        client = cls.get_client()
        operator = provider_id or 'any'
        charge_price = float(price) if price else 0.85

        if client.is_configured:
            buy_res = client.buy_activation(country_slug=country_slug, service_code=service_code, operator=operator)
            if buy_res.get('success'):
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
                    'provider_line': operator,
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
            'provider_line': operator,
            'price': charge_price,
            'status': 'pending',
        }
