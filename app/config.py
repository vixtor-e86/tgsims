import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'tgsims-dev-secret-key-2026')
    SUPABASE_URL = os.getenv('SUPABASE_URL', '')
    SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY', '')
    SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
    RESEND_API_KEY = os.getenv('RESEND_API_KEY', '')
    SMSCODE_API_KEY = (os.getenv('SMSCODE_API_KEY') or os.getenv('SIM_PROVIDER_API_KEY', '')).strip()
    SMSCODE_BASE_URL = (os.getenv('SMSCODE_BASE_URL') or os.getenv('SIM_PROVIDER_BASE_URL', 'https://api.smscode.gg/v2')).strip().rstrip('/')
    SIM_PROVIDER_API_KEY = SMSCODE_API_KEY
    SIM_PROVIDER_BASE_URL = SMSCODE_BASE_URL
    # Legacy alias
    VIRTUALSMS_API_KEY = SMSCODE_API_KEY
    VIRTUALSMS_BASE_URL = SMSCODE_BASE_URL
    FIVESIM_API_KEY = SMSCODE_API_KEY
    FIVESIM_BASE_URL = SMSCODE_BASE_URL
    PAYMENT_SECRET_KEY = os.getenv('PAYMENT_SECRET_KEY', '')
    PAYMENT_PUBLIC_KEY = os.getenv('PAYMENT_PUBLIC_KEY', '')
    DEV_PASSWORD = os.getenv('DEV_PASSWORD', 'Icui4cu')
    TEXTVERIFIED_API_KEY = (os.getenv('TEXTVERIFIED_API_KEY') or '').strip()
    TEXTVERIFIED_USERNAME = (os.getenv('TEXTVERIFIED_USERNAME') or '').strip()

    # Legacy NowPayments (kept for backward compat, no longer primary)
    NOWPAYMENTS_API_KEY = (os.getenv('NOWPAYMENTS_API_KEY') or '').strip()
    NOWPAYMENTS_IPN_SECRET = (os.getenv('NOWPAYMENTS_IPN_SECRET') or '').strip()
    NOWPAYMENTS_BASE_URL = (os.getenv('NOWPAYMENTS_BASE_URL') or 'https://api.nowpayments.io/v1').strip().rstrip('/')

    # OXAPay (primary crypto gateway — supports Nigeria, $1 minimum)
    OXAPAY_API_KEY = (os.getenv('OXAPAY_API_KEY') or '').strip()

    # Squad (NGN payment gateway - virtual accounts, card, bank transfer)
    SQUAD_SECRET_KEY = (os.getenv('SQUAD_SECRET_KEY') or '').strip()
    SQUAD_PUBLIC_KEY = (os.getenv('SQUAD_PUBLIC_KEY') or '').strip()

    # Korapay (Dedicated Virtual Accounts)
    KORAPAY_SECRET_KEY = (os.getenv('KORAPAY_SECRET_KEY') or '').strip()
    KORAPAY_PUBLIC_KEY = (os.getenv('KORAPAY_PUBLIC_KEY') or '').strip()
    KORAPAY_ENCRYPTION_KEY = (os.getenv('KORAPAY_ENCRYPTION_KEY') or '').strip()

    SITE_LOCK_ENABLED = os.getenv('SITE_LOCK_ENABLED', 'false').lower() in ('true', '1', 'yes')
