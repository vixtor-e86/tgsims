import time
from typing import Dict, Any, List, Optional
from app.services.supabase_client import get_supabase_admin, reset_supabase_admin

# Default fallbacks if database table is completely unpopulated
DEFAULT_SETTINGS = {
    'ngn_per_usd_rate': 1600.00,
    'smscode_markup_percent': 25.00,
    'smscode_min_profit_usd': 0.25,
    'virtualsms_markup_percent': 25.00,
    'virtualsms_min_profit_usd': 0.25,
    'fivesim_markup_percent': 25.00,
    'fivesim_min_profit_usd': 0.25,
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

                    # Synchronize SMSCode / 5sim markup percentage and floor consistently from DB columns
                    active_smscode_pct = None
                    for col in ('smscode_markup_percent', 'virtualsms_markup_percent', 'fivesim_markup_percent', 'default_markup_percent'):
                        if col in row and row[col] is not None:
                            try:
                                active_smscode_pct = float(row[col])
                                break
                            except (ValueError, TypeError):
                                pass
                    if active_smscode_pct is not None:
                        base['smscode_markup_percent'] = active_smscode_pct
                        base['virtualsms_markup_percent'] = active_smscode_pct
                        base['fivesim_markup_percent'] = active_smscode_pct

                    active_smscode_floor = None
                    for col in ('smscode_min_profit_usd', 'virtualsms_min_profit_usd', 'fivesim_min_profit_usd', 'min_profit_usd'):
                        if col in row and row[col] is not None:
                            try:
                                active_smscode_floor = float(row[col])
                                break
                            except (ValueError, TypeError):
                                pass
                    if active_smscode_floor is not None:
                        base['smscode_min_profit_usd'] = active_smscode_floor
                        base['virtualsms_min_profit_usd'] = active_smscode_floor
                        base['fivesim_min_profit_usd'] = active_smscode_floor

                    if 'textverified_markup_percent' in row and row['textverified_markup_percent'] is not None:
                        base['textverified_markup_percent'] = float(row['textverified_markup_percent'])
                    if 'textverified_min_profit_usd' in row and row['textverified_min_profit_usd'] is not None:
                        base['textverified_min_profit_usd'] = float(row['textverified_min_profit_usd'])

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
        pct = float(
            settings.get('smscode_markup_percent')
            if settings.get('smscode_markup_percent') is not None
            else settings.get('fivesim_markup_percent', 25.0)
        )
        floor = float(
            settings.get('smscode_min_profit_usd')
            if settings.get('smscode_min_profit_usd') is not None
            else settings.get('fivesim_min_profit_usd', 0.25)
        )
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

        # Support smscode, virtualsms, and fivesim keys interchangeably with proper zero handling
        sc_pct = None
        for k in ('smscode_markup_percent', 'virtualsms_markup_percent', 'fivesim_markup_percent'):
            if updates.get(k) is not None:
                sc_pct = updates[k]
                break
        if sc_pct is not None:
            clean_data['smscode_markup_percent'] = float(sc_pct)
            clean_data['virtualsms_markup_percent'] = float(sc_pct)
            clean_data['fivesim_markup_percent'] = float(sc_pct)

        sc_floor = None
        for k in ('smscode_min_profit_usd', 'virtualsms_min_profit_usd', 'fivesim_min_profit_usd'):
            if updates.get(k) is not None:
                sc_floor = updates[k]
                break
        if sc_floor is not None:
            clean_data['smscode_min_profit_usd'] = float(sc_floor)
            clean_data['virtualsms_min_profit_usd'] = float(sc_floor)
            clean_data['fivesim_min_profit_usd'] = float(sc_floor)
        if 'textverified_markup_percent' in updates and updates['textverified_markup_percent'] is not None:
            clean_data['textverified_markup_percent'] = float(updates['textverified_markup_percent'])
        if 'textverified_min_profit_usd' in updates and updates['textverified_min_profit_usd'] is not None:
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
                cls._overrides_cache = None
                cls._overrides_cache_time = 0
                try:
                    from app.services.sim_provider import SIMProviderService
                    SIMProviderService.clear_all_caches()
                except Exception:
                    pass
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

    _overrides_cache = None
    _overrides_cache_time = 0

    @classmethod
    def get_price_overrides(cls, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch all manual service price overrides."""
        now = time.time()
        if not force_refresh and cls._overrides_cache is not None and (now - cls._overrides_cache_time) < 60:
            return cls._overrides_cache

        admin = get_supabase_admin()
        if not admin:
            return []
        try:
            res = admin.table('service_price_overrides')\
                .select('*')\
                .order('service_name', desc=False)\
                .execute()
            cls._overrides_cache = res.data or []
            cls._overrides_cache_time = now
            return cls._overrides_cache
        except Exception as e:
            print(f"[SettingsService] Error loading price overrides: {e}")
            return cls._overrides_cache or []

    @classmethod
    def set_price_override(cls, service_code: str, service_name: str, provider_type: str, override_price_usd: float, notes: str = '', override_price_ngn: float = None) -> bool:
        """Upsert a manual service price override."""
        cls._overrides_cache = None
        cls._overrides_cache_time = 0
        try:
            from app.services.sim_provider import SIMProviderService
            SIMProviderService.clear_all_caches()
        except Exception:
            pass

        admin = get_supabase_admin()
        if not admin:
            return True
        try:
            # Map provider types: 'textverified' -> 'textverified', all others ('smscode', '5sim', 'virtualsms') -> '5sim'
            # to strictly satisfy PostgreSQL table check constraint: CHECK (provider_type IN ('5sim', 'textverified'))
            prov_clean = str(provider_type).strip().lower()
            norm_provider = 'textverified' if prov_clean == 'textverified' else '5sim'

            rate = cls.get_usd_ngn_rate()
            if override_price_ngn is None:
                override_price_ngn = round(float(override_price_usd) * rate, 2)

            row = {
                'service_code': service_code.strip().lower(),
                'service_name': service_name.strip(),
                'provider_type': norm_provider,
                'override_price_usd': float(override_price_usd),
                'override_price_ngn': float(override_price_ngn),
                'notes': notes.strip(),
                'is_active': True,
                'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            }
            try:
                res = admin.table('service_price_overrides')\
                    .upsert(row, on_conflict='service_code,provider_type')\
                    .execute()
                return True
            except Exception as e_col:
                # If override_price_ngn column doesn't exist yet in Supabase table, retry without it
                if 'override_price_ngn' in str(e_col) and 'override_price_ngn' in row:
                    row.pop('override_price_ngn', None)
                    res = admin.table('service_price_overrides')\
                        .upsert(row, on_conflict='service_code,provider_type')\
                        .execute()
                    return True
                raise e_col
        except Exception as e:
            print(f"[SettingsService] Error saving price override: {e}")
            return False

    @classmethod
    def delete_price_override(cls, override_id: str) -> bool:
        """Remove a service price override."""
        cls._overrides_cache = None
        cls._overrides_cache_time = 0
        try:
            from app.services.sim_provider import SIMProviderService
            SIMProviderService.clear_all_caches()
        except Exception:
            pass

        admin = get_supabase_admin()
        if not admin:
            return True
        try:
            admin.table('service_price_overrides').delete().eq('id', override_id).execute()
            return True
        except Exception as e:
            print(f"[SettingsService] Error deleting price override: {e}")
            return False

    @classmethod
    def delete_price_override_by_code(cls, service_code: str, provider_type: str = '5sim') -> bool:
        """Remove a service price override by its service_code and provider_type."""
        cls._overrides_cache = None
        cls._overrides_cache_time = 0
        try:
            from app.services.sim_provider import SIMProviderService
            SIMProviderService.clear_all_caches()
        except Exception:
            pass

        admin = get_supabase_admin()
        if not admin:
            return True
        try:
            admin.table('service_price_overrides').delete().eq('service_code', service_code.strip().lower()).eq('provider_type', provider_type).execute()
            return True
        except Exception as e:
            print(f"[SettingsService] Error deleting price override by code: {e}")
            return False

    @classmethod
    def get_us_whatsapp_operators_pricing(cls) -> List[Dict[str, Any]]:
        """Fetch US WhatsApp operator list with wholesale costs and current retail prices."""
        import json
        import os

        rate = cls.get_usd_ngn_rate()
        pct, floor = cls.get_smscode_markup()

        all_overrides = cls.get_price_overrides()
        overrides_map = {
            o['service_code'].strip().lower(): o
            for o in all_overrides
            if o.get('is_active', True) and o.get('service_code')
        }

        data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'usa_core_services.json')
        wa_ops = []
        if os.path.exists(data_path):
            try:
                with open(data_path, 'r', encoding='utf-8') as f:
                    core_data = json.load(f)
                    wa_ops = core_data.get('whatsapp', {}).get('operators', [])
            except Exception as e:
                print(f"[SettingsService] Error loading whatsapp operators: {e}")

        if not wa_ops:
            wa_ops = [
                {'operator_id': 0, 'operator_code': 'any', 'operator_name': 'Basic Operator', 'base_price_usd': 0.963},
                {'operator_id': 125, 'operator_code': 'tmobile', 'operator_name': 'T-Mobile (EE)', 'base_price_usd': 1.9423},
                {'operator_id': 111, 'operator_code': 'at_t', 'operator_name': 'AT&T', 'base_price_usd': 1.6719},
                {'operator_id': 119, 'operator_code': 'mint_mobile', 'operator_name': 'Mint Mobile', 'base_price_usd': 1.9423},
                {'operator_id': 128, 'operator_code': 'verizon', 'operator_name': 'Verizon', 'base_price_usd': 2.14},
                {'operator_id': 127, 'operator_code': 'us_mobile', 'operator_name': 'US_MOBILE', 'base_price_usd': 3.7765},
            ]

        res = []
        for op in wa_ops:
            op_code = (op.get('operator_code') or '').strip().lower()
            op_id = op.get('operator_id')
            op_id_str = str(op_id) if op_id is not None else ''
            raw_name = op.get('operator_name', op_code.title())
            base_cost = float(op.get('base_price_usd', 0.963))

            # Normalize display name
            if op_code in ('any', 'basic') or 'basic' in raw_name.lower():
                display_name = 'Basic Operator'
            elif 'tmobile' in op_code or 't-mobile' in raw_name.lower():
                display_name = 'T-Mobile'
            elif 'at_t' in op_code or 'at&t' in raw_name.lower():
                display_name = 'AT&T'
            elif 'verizon' in op_code or 'verizon' in raw_name.lower():
                display_name = 'Verizon'
            elif 'mint' in op_code or 'mint' in raw_name.lower():
                display_name = 'Mint Mobile'
            elif 'us_mobile' in op_code or 'us mobile' in raw_name.lower():
                display_name = 'US Mobile'
            else:
                display_name = raw_name

            # Check for operator-specific override
            ov_key = f"whatsapp:{op_code}"
            ov_obj = overrides_map.get(ov_key)
            if not ov_obj and op_id_str:
                ov_obj = overrides_map.get(f"whatsapp:{op_id_str}")

            is_custom = False
            custom_price_usd = None
            custom_price_ngn = None
            override_id = None

            if ov_obj:
                is_custom = True
                custom_price_usd = float(ov_obj['override_price_usd'])
                override_id = ov_obj.get('id')
                retail_usd = round(custom_price_usd, 2)
                if ov_obj.get('override_price_ngn') is not None and float(ov_obj['override_price_ngn']) > 0:
                    custom_price_ngn = round(float(ov_obj['override_price_ngn']), 2)
                else:
                    custom_price_ngn = round(custom_price_usd * rate, 2)
                retail_ngn = custom_price_ngn
            else:
                # Calculate auto-markup
                if pct <= 0.0 and floor <= 0.0:
                    retail_usd = round(base_cost, 2)
                else:
                    profit = max(base_cost * (pct / 100.0), floor)
                    retail_usd = round(base_cost + profit, 2)
                retail_ngn = round(retail_usd * rate, 2)

            res.append({
                'operator_id': op_id,
                'operator_code': op_code,
                'operator_name': display_name,
                'base_cost_usd': round(base_cost, 4),
                'base_cost_display': f"${base_cost:.2f}",
                'base_cost_ngn_display': f"₦{round(base_cost * rate, 2):,.2f}",
                'cheapest_product_id': op.get('cheapest_product_id'),
                'catalog_product_id': op.get('catalog_product_id'),
                'available': op.get('available', 100),
                'override_id': override_id,
                'custom_price_usd': custom_price_usd,
                'custom_price_ngn': custom_price_ngn,
                'retail_usd': retail_usd,
                'retail_ngn': retail_ngn,
                'formatted_usd': f"${retail_usd:.2f}",
                'formatted_ngn': f"₦{retail_ngn:,.2f}",
                'is_custom': is_custom,
            })

        # Ensure Basic Operator is first, then T-Mobile, then remaining by wholesale cost
        res.sort(key=lambda x: (0 if x['operator_code'] == 'any' else (1 if 'tmobile' in x['operator_code'] else 2), x['base_cost_usd']))
        return res

    @classmethod
    def set_us_whatsapp_operator_price(cls, operator_code: str, custom_price_usd: float = None, custom_price_ngn: float = None, operator_name: str = '') -> bool:
        """Sets or resets the retail price override for a specific US WhatsApp operator using USD or NGN."""
        op_code = operator_code.strip().lower()
        rate = cls.get_usd_ngn_rate()

        if custom_price_usd is None and custom_price_ngn is not None and float(custom_price_ngn) > 0:
            custom_price_usd = round(float(custom_price_ngn) / rate, 4)
        elif custom_price_ngn is None and custom_price_usd is not None and float(custom_price_usd) > 0:
            custom_price_ngn = round(float(custom_price_usd) * rate, 2)

        if custom_price_usd is not None and float(custom_price_usd) > 0:
            svc_code = f"whatsapp:{op_code}"
            name = f"WhatsApp ({operator_name or op_code.title()})"
            return cls.set_price_override(
                service_code=svc_code,
                service_name=name,
                provider_type='5sim',
                override_price_usd=float(custom_price_usd),
                override_price_ngn=float(custom_price_ngn) if custom_price_ngn else None,
                notes='US WhatsApp operator pricing override'
            )
        else:
            return cls.delete_price_override_by_code(f"whatsapp:{op_code}", provider_type='5sim')

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
        row = {
            'service_code': sc,
            'service_name': service_name or sc.capitalize(),
            'duration_days': days,
            'custom_price_usd': float(custom_price_usd) if custom_price_usd is not None and custom_price_usd > 0 else None,
            'updated_at': now_iso
        }
        for attempt in range(2):
            try:
                admin.table('rental_service_pricing').upsert(row, on_conflict='service_code,duration_days').execute()
                return True
            except Exception as e:
                err_str = str(e).lower()
                if ('10054' in err_str or 'connection' in err_str or 'closed' in err_str) and attempt == 0:
                    reset_supabase_admin()
                    admin = get_supabase_admin(fresh=True)
                    continue
                print(f"[SettingsService] Error updating rental price: {e}")
                return False
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
        for attempt in range(2):
            try:
                admin.table('rental_service_pricing')\
                    .update({'custom_price_usd': None, 'updated_at': now_iso})\
                    .eq('service_code', sc)\
                    .eq('duration_days', days)\
                    .execute()
                return True
            except Exception as e:
                err_str = str(e).lower()
                if ('10054' in err_str or 'connection' in err_str or 'closed' in err_str) and attempt == 0:
                    reset_supabase_admin()
                    admin = get_supabase_admin(fresh=True)
                    continue
                print(f"[SettingsService] Error resetting rental price: {e}")
                return False
        return False

    @classmethod
    def sync_rental_wholesale_prices(cls) -> tuple[bool, str, int]:
        """Fetches live wholesale rental prices from TextVerified API for all 10 core services
        across durations (1, 3, 7, 14, 30, 90, 365 days) and persists them directly into the database.
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
            1: RentalDuration.ONE_DAY,
            3: RentalDuration.THREE_DAY,
            7: RentalDuration.SEVEN_DAY,
            14: RentalDuration.FOURTEEN_DAY,
            30: RentalDuration.THIRTY_DAY,
            90: RentalDuration.NINETY_DAY,
            365: RentalDuration.ONE_YEAR
        }

        services = SIMProviderService.RENTAL_SERVICES
        updated_count = 0
        now_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

        for svc in services:
            sc = svc['code'].strip().lower()
            sname = svc.get('name', sc.capitalize())
            for days, rd in durations.items():
                try:
                    if sc == 'allservices' and days == 1:
                        p3 = tv.reservations.pricing(
                            service_name=sc,
                            duration=RentalDuration.THREE_DAY,
                            number_type=NumberType.MOBILE,
                            capability=ReservationCapability.SMS,
                            area_code=False,
                            always_on=False,
                            is_renewable=False
                        )
                        cost = round(float(getattr(p3, 'price', 6.0) or 6.0) * 0.75, 2)
                    else:
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
            return False, "No prices could be updated. Please ensure migration 015 has been run in Supabase SQL editor.", 0

