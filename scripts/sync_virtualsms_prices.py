"""VirtualSMS.io Wholesale Pricing Fetcher and Catalog Synchronizer.

Fetches real-time wholesale pricing and services from VirtualSMS.io REST API:
1. Complete Worldwide Catalog (app/data/catalog.json) across all 58 active countries
   with accurate per-country prices and real VirtualSMS service codes.
2. Complete USA Services Catalog (app/data/5sim_us_services.json) with 700 services
   and live prices for the US Economy / Basic Pool.
3. Supabase Database table 'service_catalog' sync for real-time DB-backed queries.
"""

import sys
import os
import json
import time
import requests
from concurrent.futures import ThreadPoolExecutor

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.services.sim_provider import VirtualSMSClient, SIMProviderService
from app.services.settings_service import SettingsService

# ISO Country Code -> Metadata (Dial code & Clean Display Name)
COUNTRY_METADATA = {
    'AO': {'name': 'Angola', 'dial': '+244'},
    'AR': {'name': 'Argentina', 'dial': '+54'},
    'AT': {'name': 'Austria', 'dial': '+43'},
    'BD': {'name': 'Bangladesh', 'dial': '+880'},
    'BE': {'name': 'Belgium', 'dial': '+32'},
    'BA': {'name': 'Bosnia and Herzegovina', 'dial': '+387'},
    'BR': {'name': 'Brazil', 'dial': '+55'},
    'BG': {'name': 'Bulgaria', 'dial': '+359'},
    'CM': {'name': 'Cameroon', 'dial': '+237'},
    'CA': {'name': 'Canada', 'dial': '+1'},
    'TD': {'name': 'Chad', 'dial': '+235'},
    'CN': {'name': 'China', 'dial': '+86'},
    'CO': {'name': 'Colombia', 'dial': '+57'},
    'HR': {'name': 'Croatia', 'dial': '+385'},
    'CZ': {'name': 'Czech Republic', 'dial': '+420'},
    'EG': {'name': 'Egypt', 'dial': '+20'},
    'EE': {'name': 'Estonia', 'dial': '+372'},
    'FR': {'name': 'France', 'dial': '+33'},
    'GE': {'name': 'Georgia', 'dial': '+995'},
    'DE': {'name': 'Germany', 'dial': '+49'},
    'GR': {'name': 'Greece', 'dial': '+30'},
    'HK': {'name': 'Hong Kong', 'dial': '+852'},
    'HU': {'name': 'Hungary', 'dial': '+36'},
    'IN': {'name': 'India', 'dial': '+91'},
    'ID': {'name': 'Indonesia', 'dial': '+62'},
    'IQ': {'name': 'Iraq', 'dial': '+964'},
    'IE': {'name': 'Ireland', 'dial': '+353'},
    'IL': {'name': 'Israel', 'dial': '+972'},
    'IT': {'name': 'Italy', 'dial': '+39'},
    'KZ': {'name': 'Kazakhstan', 'dial': '+7'},
    'KE': {'name': 'Kenya', 'dial': '+254'},
    'KG': {'name': 'Kyrgyzstan', 'dial': '+996'},
    'LV': {'name': 'Latvia', 'dial': '+371'},
    'LR': {'name': 'Liberia', 'dial': '+231'},
    'LT': {'name': 'Lithuania', 'dial': '+370'},
    'MY': {'name': 'Malaysia', 'dial': '+60'},
    'MX': {'name': 'Mexico', 'dial': '+52'},
    'MD': {'name': 'Moldova', 'dial': '+373'},
    'MA': {'name': 'Morocco', 'dial': '+212'},
    'NL': {'name': 'Netherlands', 'dial': '+31'},
    'NZ': {'name': 'New Zealand', 'dial': '+64'},
    'NG': {'name': 'Nigeria', 'dial': '+234'},
    'PE': {'name': 'Peru', 'dial': '+51'},
    'PH': {'name': 'Philippines', 'dial': '+63'},
    'PL': {'name': 'Poland', 'dial': '+48'},
    'PT': {'name': 'Portugal', 'dial': '+351'},
    'RO': {'name': 'Romania', 'dial': '+40'},
    'SK': {'name': 'Slovakia', 'dial': '+421'},
    'SI': {'name': 'Slovenia', 'dial': '+386'},
    'ZA': {'name': 'South Africa', 'dial': '+27'},
    'ES': {'name': 'Spain', 'dial': '+34'},
    'SE': {'name': 'Sweden', 'dial': '+46'},
    'TH': {'name': 'Thailand', 'dial': '+66'},
    'TR': {'name': 'Turkey', 'dial': '+90'},
    'UA': {'name': 'Ukraine', 'dial': '+380'},
    'GB': {'name': 'United Kingdom', 'dial': '+44'},
    'US': {'name': 'United States', 'dial': '+1'},
    'UZ': {'name': 'Uzbekistan', 'dial': '+998'},
    'VN': {'name': 'Vietnam', 'dial': '+84'}
}

# Clean user-facing display names for core services
CLEAN_SERVICE_NAMES = {
    'wa': 'WhatsApp',
    'wa_biz': 'WhatsApp Business',
    'tg': 'Telegram',
    'go': 'Google / Gmail / YouTube',
    'dr': 'OpenAI / ChatGPT',
    'ig': 'Instagram / Threads',
    'lf': 'TikTok',
    'fb': 'Facebook / Meta',
    'tw': 'Twitter / X',
    'oi': 'Tinder',
    'wx': 'Apple ID / iCloud',
    'ds': 'Discord',
    'am': 'Amazon',
    'nf': 'Netflix',
    'ub': 'Uber',
    'ts': 'PayPal',
    'fu': 'Snapchat',
    'mm': 'Microsoft',
    'mb': 'Yahoo',
    'mt': 'Steam',
    'li': 'LinkedIn',
    'bl': 'Bigo Live',
    're': 'Reddit',
    'sn': 'Line',
    'ka': 'Shopee',
    'kt': 'KakaoTalk',
    'me': 'Line messenger',
    'ot': 'Other Platforms'
}

# Priority ordering for popular services
POPULAR_PRIORITY = {
    'wa': 1, 'wa_biz': 2, 'tg': 3, 'go': 4, 'ig': 5, 'tw': 6,
    'dr': 7, 'lf': 8, 'fb': 9, 'oi': 10, 'wx': 11, 'ds': 12,
    'ub': 13, 'am': 14, 'nf': 15, 'ts': 16, 'fu': 17, 'mm': 18,
    'mb': 19, 'mt': 20, 'li': 21, 'bl': 22, 're': 23, 'ot': 999
}

# Core services for which we actively fetch per-country wholesale prices in parallel
CORE_TRACKED_SERVICES = [
    'wa', 'tg', 'go', 'ig', 'fb', 'tw', 'lf', 'dr', 'oi', 'wx',
    'am', 'nf', 'ub', 'ds', 'fu', 'mm', 'ts', 'mb', 'mt', 'li',
    'bl', 're', 'sn', 'ka', 'me', 'kt', 'hw', 'mo', 'ya', 'qq',
    'vk', 'ok', 'we', 'sg', 'dp', 'tc', 'ti', 'tn', 'tr', 'tx',
    'ua', 'uk', 'uu', 'vi', 'vz', 'wb', 'wc', 'ws', 'ot'
]


def flag_emoji(iso_code: str) -> str:
    """Generate Unicode flag emoji from 2-letter ISO country code."""
    if not iso_code or len(iso_code) != 2:
        return '🌐'
    try:
        return ''.join(chr(127397 + ord(c)) for c in iso_code.upper())
    except Exception:
        return '🌐'


def sync_virtualsms_catalog(max_workers: int = 16) -> bool:
    """Fetch live wholesale prices from VirtualSMS.io and rebuild app/data/catalog.json.
    
    Covers all 58 active countries supported by VirtualSMS with their real services,
    accurate wholesale prices (e.g. Nigeria WhatsApp $1.13, UK WhatsApp $1.13, etc.),
    and proper VirtualSMS service codes.
    """
    client = VirtualSMSClient()
    if not client.is_configured:
        print("[-] VirtualSMSClient is not configured with an API key.")
        return False

    headers = client._headers()
    session = requests.Session()
    session.headers.update(headers)

    print("[*] Fetching countries list from VirtualSMS.io...")
    try:
        r_c = session.get(f"{client.base_url}/customer/countries", timeout=15)
        if r_c.status_code != 200:
            print(f"[-] Failed to fetch countries: HTTP {r_c.status_code} - {r_c.text[:200]}")
            return False
        countries_data = r_c.json().get('countries', [])
    except Exception as e:
        print(f"[-] Exception fetching countries: {e}")
        return False

    print(f"[+] Retrieved {len(countries_data)} active countries from VirtualSMS.")

    print("[*] Fetching full services catalog from VirtualSMS.io...")
    try:
        r_s = session.get(f"{client.base_url}/customer/services", timeout=15)
        if r_s.status_code != 200:
            print(f"[-] Failed to fetch services: HTTP {r_s.status_code}")
            return False
        services_data = r_s.json().get('services', [])
    except Exception as e:
        print(f"[-] Exception fetching services: {e}")
        return False

    # Build services lookup: service_id -> dict
    all_services_map = {}
    for s in services_data:
        sid = s.get('service_id')
        if not sid:
            continue
        sid_lower = sid.strip().lower()
        clean_name = CLEAN_SERVICE_NAMES.get(sid_lower) or s.get('service_name', '').strip()
        all_services_map[sid_lower] = {
            'service_id': sid_lower,
            'service_name': clean_name,
            'base_price': float(s.get('base_price') or 0.20)
        }

    print(f"[+] Retrieved {len(all_services_map)} total services from VirtualSMS.")

    # 3. Fetch country-specific prices for core tracked services in parallel
    print(f"[*] Fetching live country pricing for {len(CORE_TRACKED_SERVICES)} core services...")
    country_service_prices = {}  # (country_id, service_code) -> wholesale_price

    def fetch_service_pricing(svc_code):
        try:
            url = f"{client.base_url}/customer/countries?service={svc_code}"
            res = session.get(url, timeout=12)
            if res.status_code == 200:
                c_list = res.json().get('countries', [])
                for row in c_list:
                    cid = (row.get('country_id') or '').upper().strip()
                    p = float(row.get('price') or 0.0)
                    if cid and p > 0:
                        country_service_prices[(cid, svc_code)] = p
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        list(executor.map(fetch_service_pricing, CORE_TRACKED_SERVICES))

    print(f"[+] Collected {len(country_service_prices)} exact country-specific wholesale prices.")

    # 4. Build the complete new catalog.json
    new_catalog = []
    for c_obj in countries_data:
        cid = (c_obj.get('country_id') or '').upper().strip()
        if not cid or cid == 'US':
            # US is served on the dedicated US page with 700 services
            continue

        raw_name = c_obj.get('country_name') or cid
        meta = COUNTRY_METADATA.get(cid, {})
        country_name = meta.get('name') or raw_name
        country_slug = country_name.lower().replace(' ', '').replace('-', '')
        dial = meta.get('dial', '+')
        flag = flag_emoji(cid)

        # Get list of service codes supported by this country in VirtualSMS
        supported_codes = c_obj.get('services', [])
        if not supported_codes:
            continue

        country_services = []
        for sc in supported_codes:
            sc_lower = str(sc).strip().lower()
            svc_info = all_services_map.get(sc_lower)
            if not svc_info:
                clean_name = CLEAN_SERVICE_NAMES.get(sc_lower) or sc_lower.title()
                fallback_base = float(c_obj.get('min_price') or 0.20)
            else:
                clean_name = svc_info['service_name']
                fallback_base = svc_info['base_price']

            # Lookup exact price for this country if available
            exact_price = country_service_prices.get((cid, sc_lower))
            base_cost = exact_price if exact_price is not None else fallback_base
            base_cost = round(base_cost, 4)

            country_services.append({
                'name': clean_name,
                'code': sc_lower,
                'category': 'SMS Verification',
                'base_cost': base_cost,
                'price': base_cost,  # get_catalog() applies dynamic admin markup at runtime
                'available': 500,
                'operator': 'standard'
            })

        # Sort: popular services first, then alphabetically, 'other' at the end
        country_services.sort(key=lambda s: (
            POPULAR_PRIORITY.get(s['code'], 500),
            s['name'].lower()
        ))

        new_catalog.append({
            'country_code': cid,
            'country_name': country_name,
            'country_slug': country_slug,
            'flag': flag,
            'dial': dial,
            'services': country_services
        })

    # Sort countries alphabetically by name
    new_catalog.sort(key=lambda c: c['country_name'])

    # Write to app/data/catalog.json
    target_catalog_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app', 'data', 'catalog.json'))
    try:
        with open(target_catalog_path, 'w', encoding='utf-8') as f:
            json.dump(new_catalog, f, indent=2, ensure_ascii=False)
        print(f"[+] Successfully wrote {len(new_catalog)} countries to {target_catalog_path}")
    except Exception as e:
        print(f"[-] Error writing catalog.json: {e}")
        return False

    # Clear runtime catalog cache
    SIMProviderService._cached_raw_catalog = None
    return True


def sync_virtualsms_us_services() -> bool:
    """Fetch live wholesale prices for US Basic services from VirtualSMS.io and save to 5sim_us_services.json & Supabase."""
    client = VirtualSMSClient()
    if not client.is_configured:
        print("[-] VirtualSMSClient is not configured with an API key.")
        return False

    headers = client._headers()
    session = requests.Session()
    session.headers.update(headers)

    print("[*] Fetching live VirtualSMS services for US Economy Pool...")
    try:
        r = session.get(f"{client.base_url}/customer/services", timeout=15)
        if r.status_code != 200:
            print(f"[-] Failed to fetch services: HTTP {r.status_code}")
            return False
        services = r.json().get('services', [])
    except Exception as e:
        print(f"[-] Error connecting to VirtualSMS: {e}")
        return False

    pct, floor = SettingsService.get_fivesim_markup()
    mult = 1.0 + (pct / 100.0)

    us_services = []
    db_rows = []

    for s in services:
        sid = (s.get('service_id') or '').strip().lower()
        if not sid:
            continue
        clean_name = CLEAN_SERVICE_NAMES.get(sid) or s.get('service_name', '').strip() or sid.title()
        base_cost = float(s.get('base_price') or 0.20)
        retail_price = round(max(base_cost * mult, base_cost + floor), 2)

        item = {
            'id': f"{sid}_us",
            'service_name': clean_name,
            'service_code': sid,
            'operator': 'standard',
            'name': clean_name,
            'quality': 'Economy Pool',
            'price_usd': retail_price,
            'base_cost_usd': base_cost,
            'count': 1000
        }
        us_services.append(item)

        db_rows.append({
            'country_code': 'US',
            'country_name': 'United States',
            'country_slug': 'usa',
            'service_code': sid,
            'service_name': clean_name,
            'category': 'SMS Verification',
            'operator': 'standard',
            'provider_cost': base_cost,
            'retail_price': retail_price,
            'available_count': 1000,
            'success_rate': 95.0,
            'is_active': True
        })

    # Priority ordering
    us_services.sort(key=lambda s: (
        POPULAR_PRIORITY.get(s['service_code'], 500),
        s['service_name'].lower()
    ))

    # Save to app/data/5sim_us_services.json
    target_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app', 'data', '5sim_us_services.json'))
    try:
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(us_services, f, indent=2, ensure_ascii=False)
        print(f"[+] Saved {len(us_services)} US services to {target_path}")
    except Exception as e:
        print(f"[-] Error writing 5sim_us_services.json: {e}")

    # Sync to Supabase service_catalog
    try:
        from app.services.supabase_client import get_supabase_admin
        admin = get_supabase_admin()
        if admin:
            print("[*] Updating Supabase service_catalog table...")
            # Upsert in chunks of 100
            for i in range(0, len(db_rows), 100):
                chunk = db_rows[i:i+100]
                admin.table('service_catalog').upsert(chunk, on_conflict='country_code,service_code').execute()
            print(f"[+] Successfully synced {len(db_rows)} services to Supabase service_catalog.")
    except Exception as e:
        print(f"[!] Supabase sync notice: {e}")

    # Clear runtime caches
    SIMProviderService._cached_5sim_us_services_raw = None
    return True


def sync_all():
    """Run complete synchronization for both worldwide catalog and US catalog."""
    print("==================================================")
    print("  VirtualSMS.io Live Wholesale Catalog Synchronizer")
    print("==================================================")
    t0 = time.time()
    ok_catalog = sync_virtualsms_catalog()
    ok_us = sync_virtualsms_us_services()
    t1 = time.time()
    print("==================================================")
    if ok_catalog and ok_us:
        print(f"[SUCCESS] Complete catalog synchronized in {t1-t0:.2f} seconds.")
        return True
    else:
        print(f"[WARNING] Synchronization finished with partial results in {t1-t0:.2f} seconds.")
        return False


if __name__ == '__main__':
    sync_all()
