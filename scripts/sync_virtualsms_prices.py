"""VirtualSMS.io Wholesale Pricing Fetcher and Catalog Synchronizer.

Fetches the complete real-time wholesale pricing catalog from VirtualSMS.io
for US Basic services and global country offerings.
"""

import sys
import os
import json
import requests

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.services.sim_provider import VirtualSMSClient


CORE_SERVICES = [
    {'service_name': 'WhatsApp', 'service_code': 'wa', 'fallback_price': 1.95},
    {'service_name': 'WhatsApp Business', 'service_code': 'wa', 'fallback_price': 1.95},
    {'service_name': 'Google / Gmail / YouTube', 'service_code': 'go', 'fallback_price': 1.05},
    {'service_name': 'Instagram', 'service_code': 'ig', 'fallback_price': 0.75},
    {'service_name': 'Twitter / X', 'service_code': 'tw', 'fallback_price': 0.75},
    {'service_name': 'TikTok', 'service_code': 'lf', 'fallback_price': 1.31},
    {'service_name': 'Facebook', 'service_code': 'fb', 'fallback_price': 1.05},
    {'service_name': 'Tinder', 'service_code': 'oi', 'fallback_price': 0.75},
    {'service_name': 'Apple ID / iCloud', 'service_code': 'wx', 'fallback_price': 0.75},
    {'service_name': 'PayPal', 'service_code': 'ts', 'fallback_price': 0.75},
    {'service_name': 'Amazon', 'service_code': 'am', 'fallback_price': 1.05},
    {'service_name': 'Discord', 'service_code': 'ds', 'fallback_price': 1.05},
    {'service_name': 'Other Platforms', 'service_code': 'ot', 'fallback_price': 1.00},
]


def sync_virtualsms_us_services():
    """Fetch live wholesale prices for US Basic services from VirtualSMS.io."""
    client = VirtualSMSClient()
    if not client.is_configured:
        print("[-] VirtualSMSClient is not configured with an API key.")
        return False

    headers = client._headers()
    print("[*] Fetching live VirtualSMS prices for US services...")

    us_services = []
    for item in CORE_SERVICES:
        svc_code = item['service_code']
        svc_name = item['service_name']
        fallback = item['fallback_price']

        price = fallback
        count = 1000
        try:
            url = f"{client.base_url}/catalog/countries?service={svc_code}"
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code == 200:
                data = r.json()
                countries = data.get('countries', [])
                us_match = next((c for c in countries if c.get('id') == 'US'), None)
                if us_match:
                    p = float(us_match.get('price') or fallback)
                    if p > 0:
                        price = p
                    count = int(us_match.get('count') or 1000)
        except Exception as e:
            print(f"[!] Warning checking {svc_code}: {e}")

        us_services.append({
            'id': f"{svc_code}_us",
            'service_name': svc_name,
            'service_code': svc_code,
            'operator': 'standard',
            'name': svc_name,
            'quality': 'Economy Pool',
            'price_usd': round(price, 2),
            'count': count
        })

    # Save to app/data/5sim_us_services.json for seamless drop-in
    target_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'data', '5sim_us_services.json')
    try:
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(us_services, f, indent=2)
        print(f"[+] Successfully synced {len(us_services)} US services to {target_path}")
        return True
    except Exception as e:
        print(f"[-] Error writing file: {e}")
        return False


if __name__ == '__main__':
    sync_virtualsms_us_services()
