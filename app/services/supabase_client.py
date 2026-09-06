import os
from app.config import Config

_supabase_client = None
_supabase_admin = None


def is_supabase_configured():
    """Check if valid Supabase credentials have been configured."""
    url = Config.SUPABASE_URL.strip()
    key = Config.SUPABASE_ANON_KEY.strip()
    return bool(url and key and url != 'https://your-supabase-project.supabase.co' and key != 'your-supabase-anon-key')


def get_supabase():
    """Cached client for shared read queries."""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_supabase_client()
    return _supabase_client


def create_supabase_client():
    """Create a fresh Supabase client instance using the Anon Public Key.
    Recommended for per-request Auth actions (sign_up, sign_in, sign_out) to prevent session leaks.
    """
    if not is_supabase_configured():
        return None
    try:
        from supabase import create_client
        return create_client(Config.SUPABASE_URL.strip(), Config.SUPABASE_ANON_KEY.strip())
    except Exception as e:
        print(f"[Supabase] Error initializing client: {e}")
        return None


def get_supabase_admin():
    """Admin client with Service Role Key for server-level operations (bypasses RLS, admin auth)."""
    global _supabase_admin
    url = Config.SUPABASE_URL.strip()
    key = Config.SUPABASE_SERVICE_ROLE_KEY.strip()
    if not (url and key and key != 'your-supabase-service-role-key' and url != 'https://your-supabase-project.supabase.co'):
        return None

    if _supabase_admin is None:
        try:
            from supabase import create_client
            _supabase_admin = create_client(url, key)
        except Exception as e:
            print(f"[Supabase Admin] Error initializing admin client: {e}")
            _supabase_admin = None
    return _supabase_admin

class MockDatabase:
    """Fallback in-memory database for local demonstration before live Supabase keys are inserted."""
    def __init__(self):
        self.wallets = {
            'demo-user-id': {'balance': 45.50, 'currency': 'USD'}
        }
        self.sim_orders = [
            {
                'id': 'sim-101',
                'user_id': 'demo-user-id',
                'order_reference': 'TGS-SIM-98214',
                'service_name': 'WhatsApp',
                'country_name': 'United States',
                'country_code': 'US',
                'phone_number': '+1 (555) 234-8921',
                'price': 2.50,
                'status': 'active',
                'sms_code': '482-910',
                'full_sms_text': 'Your WhatsApp code is: 482-910. Do not share it with anyone.',
                'created_at': '2026-08-07 18:30:00'
            },
            {
                'id': 'sim-102',
                'user_id': 'demo-user-id',
                'order_reference': 'TGS-SIM-98215',
                'service_name': 'Telegram',
                'country_name': 'United Kingdom',
                'country_code': 'GB',
                'phone_number': '+44 7700 900123',
                'price': 1.80,
                'status': 'completed',
                'sms_code': '994-123',
                'full_sms_text': 'Telegram code: 994123',
                'created_at': '2026-08-06 14:15:00'
            }
        ]
        self.transactions = [
            {
                'id': 'tx-1',
                'user_id': 'demo-user-id',
                'amount': 50.00,
                'type': 'deposit',
                'status': 'completed',
                'reference': 'DEP-908123',
                'description': 'Wallet Top-up via Paystack',
                'created_at': '2026-08-05 10:00:00'
            },
            {
                'id': 'tx-2',
                'user_id': 'demo-user-id',
                'amount': -2.50,
                'type': 'purchase',
                'status': 'completed',
                'reference': 'TGS-SIM-98214',
                'description': 'WhatsApp Virtual SIM (US)',
                'created_at': '2026-08-07 18:30:00'
            }
        ]

mock_db = MockDatabase()
