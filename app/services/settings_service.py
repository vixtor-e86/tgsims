"""Platform Settings Service for Tgsims.
Manages FX conversion rates (USD/NGN), provider markup percentages (5sim & TextVerified),
reactivation fees, price overrides, and payment channel configurations.
Uses an in-memory cache with immediate invalidation on admin updates.
"""
import time
from typing import Dict, Any, List, Optional
from app.services.supabase_client import get_supabase_admin

# Default fallbacks
DEFAULT_SETTINGS = {
    'ngn_per_usd_rate': 1600.00,
    'fivesim_markup_percent': 30.00,
    'fivesim_min_profit_usd': 0.30,
    'textverified_markup_percent': 25.00,
    'reactivation_fee_usd': 1.00,
    'crypto_deposit_address': '',
    'squad_enabled': True,
    'crypto_enabled': True,
    'manual_bank_details': 'Bank: GTBank\nAccount Name: Tgsims Tech\nAccount Number: 0123456789'
}


class SettingsService:
    """Manages platform pricing rules, exchange rates, and payment configurations."""

    _cache: Optional[Dict[str, Any]] = None
    _cache_time: float = 0
    _CACHE_TTL: float = 60.0  # Cache for 60 seconds

    @classmethod
    def get_settings(cls, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch platform settings with in-memory caching."""
        now = time.time()
        if not force_refresh and cls._cache is not None and (now - cls._cache_time) < cls._CACHE_TTL:
            return dict(cls._cache)

        admin = get_supabase_admin()
        base = dict(cls._cache) if cls._cache else dict(DEFAULT_SETTINGS)

        if not admin:
            cls._cache = base
            cls._cache_time = now
            return dict(base)

        try:
            res = admin.table('platform_settings').select('*').limit(1).execute()
            if res.data and len(res.data) > 0:
                row = res.data[0]
                # Merge DB fields dynamically
                if 'ngn_per_usd_rate' in row and row['ngn_per_usd_rate'] is not None:
                    base['ngn_per_usd_rate'] = float(row['ngn_per_usd_rate'])
                if 'fivesim_markup_percent' in row and row['fivesim_markup_percent'] is not None:
                    base['fivesim_markup_percent'] = float(row['fivesim_markup_percent'])
                elif 'default_markup_percent' in row and row['default_markup_percent'] is not None:
                    base['fivesim_markup_percent'] = float(row['default_markup_percent'])

                if 'fivesim_min_profit_usd' in row and row['fivesim_min_profit_usd'] is not None:
                    base['fivesim_min_profit_usd'] = float(row['fivesim_min_profit_usd'])
                elif 'min_profit_usd' in row and row['min_profit_usd'] is not None:
                    base['fivesim_min_profit_usd'] = float(row['min_profit_usd'])

                if 'textverified_markup_percent' in row and row['textverified_markup_percent'] is not None:
                    base['textverified_markup_percent'] = float(row['textverified_markup_percent'])
                if 'reactivation_fee_usd' in row and row['reactivation_fee_usd'] is not None:
                    base['reactivation_fee_usd'] = float(row['reactivation_fee_usd'])
                if 'crypto_deposit_address' in row and row['crypto_deposit_address'] is not None:
                    base['crypto_deposit_address'] = row['crypto_deposit_address']
                if 'squad_enabled' in row and row['squad_enabled'] is not None:
                    base['squad_enabled'] = bool(row['squad_enabled'])
                if 'crypto_enabled' in row and row['crypto_enabled'] is not None:
                    base['crypto_enabled'] = bool(row['crypto_enabled'])
                if 'manual_bank_details' in row and row['manual_bank_details'] is not None:
                    base['manual_bank_details'] = row['manual_bank_details']

                base['id'] = row.get('id')
                base['updated_at'] = row.get('updated_at', base.get('updated_at'))
                cls._cache = base
                cls._cache_time = now
                return dict(base)
        except Exception as e:
            print(f"[SettingsService] Error loading platform settings: {e}")

        cls._cache = base
        cls._cache_time = now
        return dict(base)

    @classmethod
    def get_usd_ngn_rate(cls) -> float:
        """Returns the current USD to NGN rate."""
        settings = cls.get_settings()
        return float(settings.get('ngn_per_usd_rate', 1600.00))

    @classmethod
    def get_fivesim_markup(cls) -> tuple[float, float]:
        """Returns (fivesim_markup_percent, fivesim_min_profit_usd)."""
        settings = cls.get_settings()
        pct = float(settings.get('fivesim_markup_percent', 30.00))
        floor = float(settings.get('fivesim_min_profit_usd', 0.30))
        return pct, floor

    @classmethod
    def get_textverified_markup(cls) -> float:
        """Returns textverified_markup_percent."""
        settings = cls.get_settings()
        return float(settings.get('textverified_markup_percent', 25.00))

    @classmethod
    def get_reactivation_fee(cls) -> float:
        """Returns reactivation fee in USD."""
        settings = cls.get_settings()
        return float(settings.get('reactivation_fee_usd', 1.00))

    @classmethod
    def update_settings(cls, updates: Dict[str, Any]) -> bool:
        """Persists updated settings and updates cache."""
        admin = get_supabase_admin()
        now_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

        clean_data = {}
        if 'ngn_per_usd_rate' in updates:
            clean_data['ngn_per_usd_rate'] = float(updates['ngn_per_usd_rate'])
        if 'fivesim_markup_percent' in updates:
            clean_data['fivesim_markup_percent'] = float(updates['fivesim_markup_percent'])
        if 'fivesim_min_profit_usd' in updates:
            clean_data['fivesim_min_profit_usd'] = float(updates['fivesim_min_profit_usd'])
        if 'textverified_markup_percent' in updates:
            clean_data['textverified_markup_percent'] = float(updates['textverified_markup_percent'])
        if 'reactivation_fee_usd' in updates:
            clean_data['reactivation_fee_usd'] = float(updates['reactivation_fee_usd'])
        if 'crypto_deposit_address' in updates:
            clean_data['crypto_deposit_address'] = str(updates['crypto_deposit_address']).strip()
        if 'squad_enabled' in updates:
            clean_data['squad_enabled'] = bool(updates['squad_enabled'])
        if 'crypto_enabled' in updates:
            clean_data['crypto_enabled'] = bool(updates['crypto_enabled'])
        if 'manual_bank_details' in updates:
            clean_data['manual_bank_details'] = str(updates['manual_bank_details']).strip()

        clean_data['updated_at'] = now_iso

        # Update cache immediately
        if cls._cache is None:
            cls._cache = dict(DEFAULT_SETTINGS)
        cls._cache.update(clean_data)
        cls._cache_time = time.time()

        if not admin:
            return True

        try:
            res = admin.table('platform_settings').select('*').limit(1).execute()
            if res.data and len(res.data) > 0:
                row = res.data[0]
                row_id = row['id']
                existing_cols = set(row.keys())

                # Build payload matching only existing columns
                payload = {}
                for k, v in clean_data.items():
                    if k in existing_cols:
                        payload[k] = v

                # Handle legacy column names if present
                if 'default_markup_percent' in existing_cols and 'fivesim_markup_percent' in clean_data:
                    payload['default_markup_percent'] = clean_data['fivesim_markup_percent']
                if 'min_profit_usd' in existing_cols and 'fivesim_min_profit_usd' in clean_data:
                    payload['min_profit_usd'] = clean_data['fivesim_min_profit_usd']

                if payload:
                    admin.table('platform_settings').update(payload).eq('id', row_id).execute()
            return True
        except Exception as e:
            print(f"[SettingsService] Error persisting settings to DB: {e}")
            return True

    @classmethod
    def get_price_overrides(cls) -> List[Dict[str, Any]]:
        """Fetch all manual service price overrides."""
        admin = get_supabase_admin()
        if not admin:
            return []
        try:
            res = admin.table('service_price_overrides')\
                .select('*')\
                .order('service_name', desc=False)\
                .execute()
            return res.data or []
        except Exception as e:
            print(f"[SettingsService] Error loading price overrides: {e}")
            return []

    @classmethod
    def set_price_override(cls, service_code: str, service_name: str, provider_type: str, override_price_usd: float, notes: str = '') -> bool:
        """Upsert a manual service price override."""
        admin = get_supabase_admin()
        if not admin:
            return True
        try:
            row = {
                'service_code': service_code.strip().lower(),
                'service_name': service_name.strip(),
                'provider_type': provider_type.strip().lower(),
                'override_price_usd': float(override_price_usd),
                'notes': notes.strip(),
                'is_active': True,
                'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            }
            res = admin.table('service_price_overrides')\
                .upsert(row, on_conflict='service_code,provider_type')\
                .execute()
            return True
        except Exception as e:
            print(f"[SettingsService] Error saving price override: {e}")
            return False

    @classmethod
    def delete_price_override(cls, override_id: str) -> bool:
        """Remove a service price override."""
        admin = get_supabase_admin()
        if not admin:
            return True
        try:
            admin.table('service_price_overrides').delete().eq('id', override_id).execute()
            return True
        except Exception as e:
            print(f"[SettingsService] Error deleting price override: {e}")
            return False
