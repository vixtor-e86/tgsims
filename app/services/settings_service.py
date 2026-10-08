import time
from typing import Dict, Any, List, Optional
from app.services.supabase_client import get_supabase_admin, reset_supabase_admin

# Default fallbacks if database table is completely unpopulated
DEFAULT_SETTINGS = {
    'ngn_per_usd_rate': 1600.00,
    'smscode_markup_percent': 30.00,
    'smscode_min_profit_usd': 0.30,
    'virtualsms_markup_percent': 30.00,
    'virtualsms_min_profit_usd': 0.30,
    'fivesim_markup_percent': 30.00,
    'fivesim_min_profit_usd': 0.30,
    'textverified_markup_percent': 25.00,
    'textverified_min_profit_usd': 0.50,
    'reactivation_fee_usd': 1.00,
    'crypto_deposit_address': '',
    'squad_enabled': True,
    'crypto_enabled': True,
    'manual_bank_details': 'Bank: GTBank\nAccount Name: Tgsims Tech\nAccount Number: 0123456789'
}


class SettingsService:
    """Manages platform pricing rules, exchange rates, and payment configurations directly in the database."""

    _cache: Optional[Dict[str, Any]] = None
    _cache_time: float = 0
    _CACHE_TTL: float = 2.0  # Ultra-short 2-second cache for lightning-fast real-time database reactivity

    @classmethod
    def get_settings(cls, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch platform settings directly from Supabase database in real-time."""
        now = time.time()
        if not force_refresh and cls._cache is not None and (now - cls._cache_time) < cls._CACHE_TTL:
            return dict(cls._cache)

        base = dict(DEFAULT_SETTINGS)
        admin = get_supabase_admin()
        if not admin:
            cls._cache = base
            cls._cache_time = now
            return dict(base)

        for attempt in range(2):
            try:
                res = admin.table('platform_settings').select('*').limit(1).execute()
                if res.data and len(res.data) > 0:
                    row = res.data[0]
                    # Map database fields directly
                    for k in DEFAULT_SETTINGS.keys():
                        if k in row and row[k] is not None:
                            val = row[k]
                            if isinstance(DEFAULT_SETTINGS[k], float):
                                base[k] = float(val)
                            elif isinstance(DEFAULT_SETTINGS[k], bool):
                                base[k] = bool(val)
                            else:
                                base[k] = val
                        elif cls._cache and k in cls._cache and cls._cache[k] is not None:
                            base[k] = cls._cache[k]

                    # Handle legacy column names if present
                    if 'default_markup_percent' in row and row['default_markup_percent'] is not None and 'fivesim_markup_percent' not in row:
                        base['fivesim_markup_percent'] = float(row['default_markup_percent'])
                    if 'min_profit_usd' in row and row['min_profit_usd'] is not None and 'fivesim_min_profit_usd' not in row:
                        base['fivesim_min_profit_usd'] = float(row['min_profit_usd'])

                    base['id'] = row.get('id')
                    base['updated_at'] = row.get('updated_at')

                    cls._cache = base
                    cls._cache_time = now
                    return dict(base)
                break
            except Exception as e:
                err_str = str(e).lower()
                if ('10054' in err_str or 'connection' in err_str or 'closed' in err_str) and attempt == 0:
                    reset_supabase_admin()
                    admin = get_supabase_admin(fresh=True)
                    continue
                print(f"[SettingsService] Error loading platform settings from DB: {e}")
                break

        cls._cache = base
        cls._cache_time = now
        return dict(base)

    @classmethod
    def get_usd_ngn_rate(cls) -> float:
        """Returns the current USD to NGN rate."""
        settings = cls.get_settings()
        return float(settings.get('ngn_per_usd_rate', 1600.00))

    @classmethod
    def get_smscode_markup(cls) -> tuple[float, float]:
        """Returns (smscode_markup_percent, smscode_min_profit_usd)."""
        settings = cls.get_settings()
        raw_pct = (
            settings.get('smscode_markup_percent')
            if settings.get('smscode_markup_percent') is not None
            else (settings.get('virtualsms_markup_percent') if settings.get('virtualsms_markup_percent') is not None else settings.get('fivesim_markup_percent'))
        )
        raw_floor = (
            settings.get('smscode_min_profit_usd')
            if settings.get('smscode_min_profit_usd') is not None
            else (settings.get('virtualsms_min_profit_usd') if settings.get('virtualsms_min_profit_usd') is not None else settings.get('fivesim_min_profit_usd'))
        )
        pct = float(raw_pct if raw_pct is not None else 30.0)
        floor = float(raw_floor if raw_floor is not None else 0.30)
        return pct, floor

    @classmethod
    def get_fivesim_markup(cls) -> tuple[float, float]:
        """Returns (smscode_markup_percent, smscode_min_profit_usd). Legacy alias."""
        return cls.get_smscode_markup()

    @classmethod
    def get_virtualsms_markup(cls) -> tuple[float, float]:
        """Returns (smscode_markup_percent, smscode_min_profit_usd). Legacy alias."""
        return cls.get_smscode_markup()

    @classmethod
    def get_textverified_markup(cls) -> tuple[float, float]:
        """Returns (textverified_markup_percent, textverified_min_profit_usd)."""
        settings = cls.get_settings()
        pct = float(settings.get('textverified_markup_percent', 25.00))
        floor = float(settings.get('textverified_min_profit_usd', 0.50))
        return pct, floor

    @classmethod
    def get_reactivation_fee(cls) -> float:
        """Returns reactivation fee in USD."""
        settings = cls.get_settings()
        return float(settings.get('reactivation_fee_usd', 1.00))

    @classmethod
    def update_settings(cls, updates: Dict[str, Any]) -> bool:
        """Persists updated settings directly to Supabase immediately in real-time."""
        now_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

        clean_data = {}
        if 'ngn_per_usd_rate' in updates:
            clean_data['ngn_per_usd_rate'] = float(updates['ngn_per_usd_rate'])

        # Support smscode, virtualsms, and fivesim keys interchangeably
        sc_pct = updates.get('smscode_markup_percent') or updates.get('virtualsms_markup_percent') or updates.get('fivesim_markup_percent')
        if sc_pct is not None:
            clean_data['smscode_markup_percent'] = float(sc_pct)
            clean_data['virtualsms_markup_percent'] = float(sc_pct)
            clean_data['fivesim_markup_percent'] = float(sc_pct)

        sc_floor = updates.get('smscode_min_profit_usd') or updates.get('virtualsms_min_profit_usd') or updates.get('fivesim_min_profit_usd')
        if sc_floor is not None:
            clean_data['smscode_min_profit_usd'] = float(sc_floor)
            clean_data['virtualsms_min_profit_usd'] = float(sc_floor)
            clean_data['fivesim_min_profit_usd'] = float(sc_floor)
        if 'textverified_markup_percent' in updates:
            clean_data['textverified_markup_percent'] = float(updates['textverified_markup_percent'])
        if 'textverified_min_profit_usd' in updates:
            clean_data['textverified_min_profit_usd'] = float(updates['textverified_min_profit_usd'])
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

        # 1. Update in-memory cache instantly
        if cls._cache is None:
            cls._cache = dict(DEFAULT_SETTINGS)
        cls._cache.update(clean_data)
        cls._cache_time = time.time()

        admin = get_supabase_admin()
        if not admin:
            return True

        # 2. Persist to Supabase in real-time
        for attempt in range(2):
            try:
                res = admin.table('platform_settings').select('*').limit(1).execute()
                if res.data and len(res.data) > 0:
                    row = res.data[0]
                    row_id = row['id']
                    existing_cols = set(row.keys())

                    payload = {}
                    for k, v in clean_data.items():
                        if k in existing_cols:
                            payload[k] = v

                    if 'default_markup_percent' in existing_cols and 'fivesim_markup_percent' in clean_data:
                        payload['default_markup_percent'] = clean_data['fivesim_markup_percent']
                    if 'min_profit_usd' in existing_cols and 'fivesim_min_profit_usd' in clean_data:
                        payload['min_profit_usd'] = clean_data['fivesim_min_profit_usd']

                    if payload:
                        admin.table('platform_settings').update(payload).eq('id', row_id).execute()
                else:
                    # Insert initial row into platform_settings
                    admin.table('platform_settings').insert(clean_data).execute()

                # Refresh in-memory cache from freshly updated DB
                cls.get_settings(force_refresh=True)
                return True
            except Exception as e:
                err_str = str(e).lower()
                if ('10054' in err_str or 'connection' in err_str or 'closed' in err_str) and attempt == 0:
                    reset_supabase_admin()
                    admin = get_supabase_admin(fresh=True)
                    continue
                print(f"[SettingsService] Error persisting settings to DB: {e}")
                return True
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

    # =========================================================================
    # DEDICATED RENTAL PRICING (DATABASE-DRIVEN)
    # =========================================================================

    @classmethod
    def get_rental_pricing_records(cls) -> List[Dict[str, Any]]:
        """Fetch all rental pricing records from public.rental_service_pricing in Supabase."""
        admin = get_supabase_admin()
        if not admin:
            return []
        try:
            res = admin.table('rental_service_pricing').select('*').order('service_name').order('duration_days').execute()
            return res.data or []
        except Exception as e:
            print(f"[SettingsService] rental_service_pricing load notice: {e}")
            return []

    @classmethod
    def get_rental_pricing_map(cls) -> Dict[tuple, Dict[str, Any]]:
        """Returns map of (service_code, duration_days) -> row from rental_service_pricing."""
        records = cls.get_rental_pricing_records()
        pmap = {}
        for r in records:
            sc = str(r.get('service_code', '')).lower().strip()
            days = int(r.get('duration_days', 3))
            pmap[(sc, days)] = {
                'id': r.get('id'),
                'service_code': sc,
                'service_name': r.get('service_name', sc.capitalize()),
                'duration_days': days,
                'wholesale_price_usd': float(r.get('wholesale_price_usd') or 0.00),
                'custom_price_usd': float(r.get('custom_price_usd')) if r.get('custom_price_usd') is not None else None,
                'is_active': bool(r.get('is_active', True)),
                'updated_at': r.get('updated_at')
            }
        return pmap

    @classmethod
    def update_rental_price(
        cls,
        service_code: str,
        duration_days: int,
        custom_price_usd: Optional[float],
        service_name: str = ''
    ) -> bool:
        """Sets or updates a custom price override for a rental service & duration."""
        admin = get_supabase_admin()
        if not admin:
            return False
        sc = service_code.strip().lower()
        days = int(duration_days)
        now_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        try:
            row = {
                'service_code': sc,
                'service_name': service_name or sc.capitalize(),
                'duration_days': days,
                'custom_price_usd': float(custom_price_usd) if custom_price_usd is not None and custom_price_usd > 0 else None,
                'updated_at': now_iso
            }
            admin.table('rental_service_pricing').upsert(row, on_conflict='service_code,duration_days').execute()
            return True
        except Exception as e:
            print(f"[SettingsService] Error updating rental price: {e}")
            return False

    @classmethod
    def reset_rental_price(cls, service_code: str, duration_days: int) -> bool:
        """Resets custom price override to NULL (so it falls back to dynamic markup)."""
        admin = get_supabase_admin()
        if not admin:
            return False
        sc = service_code.strip().lower()
        days = int(duration_days)
        now_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        try:
            admin.table('rental_service_pricing')\
                .update({'custom_price_usd': None, 'updated_at': now_iso})\
                .eq('service_code', sc)\
                .eq('duration_days', days)\
                .execute()
            return True
        except Exception as e:
            print(f"[SettingsService] Error resetting rental price: {e}")
            return False

    @classmethod
    def sync_rental_wholesale_prices(cls) -> tuple[bool, str, int]:
        """Fetches live wholesale rental prices from TextVerified API for all 10 core services
        across durations (3, 7, 14, 30 days) and persists them directly into the database.
        """
        from app.services.sim_provider import SIMProviderService
        try:
            from textverified import RentalDuration, NumberType, ReservationCapability
        except ImportError:
            return False, "TextVerified SDK is not installed or unavailable.", 0

        tv = SIMProviderService.get_textverified_client()
        if not tv:
            return False, "TextVerified API credentials are not configured.", 0

        admin = get_supabase_admin()
        if not admin:
            return False, "Database connection is not available.", 0

        durations = {
            3: RentalDuration.THREE_DAY,
            7: RentalDuration.SEVEN_DAY,
            14: RentalDuration.FOURTEEN_DAY,
            30: RentalDuration.THIRTY_DAY
        }

        services = SIMProviderService.RENTAL_SERVICES
        updated_count = 0
        now_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

        for svc in services:
            sc = svc['code'].strip().lower()
            sname = svc.get('name', sc.capitalize())
            for days, rd in durations.items():
                try:
                    p = tv.reservations.pricing(
                        service_name=sc,
                        duration=rd,
                        number_type=NumberType.MOBILE,
                        capability=ReservationCapability.SMS,
                        area_code=False,
                        always_on=False,
                        is_renewable=False
                    )
                    cost = float(getattr(p, 'price', 0.0) or 0.0)
                    if cost > 0:
                        admin.table('rental_service_pricing').upsert({
                            'service_code': sc,
                            'service_name': sname,
                            'duration_days': days,
                            'wholesale_price_usd': cost,
                            'updated_at': now_iso
                        }, on_conflict='service_code,duration_days').execute()
                        updated_count += 1
                except Exception as ep:
                    print(f"[SettingsService] rental pricing sync note ({sc}, {days}d): {ep}")

        if updated_count > 0:
            return True, f"Successfully refreshed wholesale prices for {updated_count} rental options directly from TextVerified!", updated_count
        else:
            return False, "No prices could be updated. Please ensure migration 012 has been run in Supabase SQL editor.", 0

