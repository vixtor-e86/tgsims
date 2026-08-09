import os
from app.config import Config

_supabase_client = None

def get_supabase():
    global _supabase_client
    if _supabase_client is None:
        url = Config.SUPABASE_URL
        key = Config.SUPABASE_ANON_KEY
        if url and key and url != 'https://your-supabase-project.supabase.co':
            try:
                from supabase import create_client
                _supabase_client = create_client(url, key)
            except Exception as e:
                print(f"[Supabase] Warning: Failed to connect to Supabase: {e}")
                _supabase_client = None
    return _supabase_client

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
