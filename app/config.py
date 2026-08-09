import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'tgsims-dev-secret-key-2026')
    SUPABASE_URL = os.getenv('SUPABASE_URL', '')
    SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY', '')
    SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
    SIM_PROVIDER_API_KEY = os.getenv('SIM_PROVIDER_API_KEY', '')
    SIM_PROVIDER_BASE_URL = os.getenv('SIM_PROVIDER_BASE_URL', '')
    PAYMENT_SECRET_KEY = os.getenv('PAYMENT_SECRET_KEY', '')
    PAYMENT_PUBLIC_KEY = os.getenv('PAYMENT_PUBLIC_KEY', '')
