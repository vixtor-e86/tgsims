"""5SIM Wholesale Pricing Fetcher and Catalog Synchronizer.

Fetches the complete real-time wholesale pricing catalog from 5SIM API
(https://5sim.net/v1/guest/prices) for all 155+ countries, services, and operators.

Usage:
  # 1. Update app catalog with real wholesale costs:
  python scripts/sync_5sim_prices.py

  # 2. Search wholesale prices for a specific service (e.g. WhatsApp):
  python scripts/sync_5sim_prices.py --search whatsapp

  # 3. View wholesale prices for a specific country (e.g. England, USA, Nigeria):
  python scripts/sync_5sim_prices.py --country england

  # 4. Export CSV report:
  python scripts/sync_5sim_prices.py --export-csv
"""

import sys
import os
import json
import csv
import argparse
import requests

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.services.sim_provider import FiveSimClient, SIMProviderService


def fetch_5sim_live_prices():
    """Fetch complete live wholesale price book from 5sim API."""
    client = FiveSimClient()
    headers = client._headers()
    url = f"{client.base_url}/guest/prices"
    print(f"[*] Fetching live wholesale prices from {url}...")
    try:
        r = requests.get(url, headers=headers, timeout=40)
        if r.status_code == 200:
            data = r.json()
            print(f"[+] Successfully retrieved prices for {len(data)} countries from 5SIM.")
            return data
        else:
            print(f"[-] Error fetching prices: HTTP {r.status_code} - {r.text[:200]}")
            return None
    except Exception as e:
        print(f"[-] Exception while connecting to 5SIM: {e}")
        return None


def extract_best_service_prices(raw_5sim_data, country_slug: str):
    """Extract lowest cost with active inventory for each service in a country."""
    if not raw_5sim_data or country_slug not in raw_5sim_data:
        return {}

    country_svcs = raw_5sim_data[country_slug]
    result = {}
    for svc_code, ops in country_svcs.items():
        if not ops or not isinstance(ops, dict):
            continue

        best_cost = None
        best_op = None
        total_count = 0
        min_catalog_cost = None

        for op_name, info in ops.items():
            cost = float(info.get('cost') or 0.0)
            count = int(info.get('count') or 0)
            total_count += count

            if min_catalog_cost is None or (cost > 0 and cost < min_catalog_cost):
                min_catalog_cost = cost

            # Prioritize operators that actually have available phone lines
            if count > 0 and cost > 0:
                if best_cost is None or cost < best_cost:
                    best_cost = cost
                    best_op = op_name

        # If no operator has stock right now, use minimum catalog cost
        final_cost = best_cost if best_cost is not None else (min_catalog_cost or 0.50)

        result[svc_code] = {
            'service_code': svc_code,
            'wholesale_cost': round(final_cost, 4),
            'best_operator': best_op or 'any',
            'available_count': total_count
        }
    return result


def sync_catalog(raw_5sim_data=None):
    """Updates app/data/catalog.json and app/data/5sim_us_services.json with real wholesale costs."""
    if raw_5sim_data is None:
        raw_5sim_data = fetch_5sim_live_prices()
        if not raw_5sim_data:
            print("[-] Cannot sync: Failed to retrieve 5SIM pricing data.")
            return False

    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app', 'data'))
    catalog_path = os.path.join(data_dir, 'catalog.json')
    us_services_path = os.path.join(data_dir, '5sim_us_services.json')

    # 1. Update app/data/catalog.json
    if os.path.exists(catalog_path):
        with open(catalog_path, 'r', encoding='utf-8') as f:
            catalog = json.load(f)

        updated_services_count = 0
        for country in catalog:
            slug = country.get('country_slug') or country.get('slug') or country.get('country_name', '').lower().replace(' ', '')
            if slug not in raw_5sim_data:
                # Try fallback mappings
                slug_map = {
                    'uk': 'england',
                    'unitedkingdom': 'england',
                    'greatbritain': 'england',
                    'us': 'usa',
                    'unitedstates': 'usa'
                }
                slug = slug_map.get(slug, slug)

            if slug in raw_5sim_data:
                live_svcs = extract_best_service_prices(raw_5sim_data, slug)
                for svc in country.get('services', []):
                    code = (svc.get('code') or svc.get('name', '')).strip().lower().replace(' ', '').replace('/', '')
                    # Direct lookup or common code normalization
                    match = live_svcs.get(code)
                    if not match and svc.get('name'):
                        # Try name-based search
                        n = svc['name'].lower()
                        for k, v in live_svcs.items():
                            if k in n or n in k:
                                match = v
                                break

                    if match:
                        real_cost = match['wholesale_cost']
                        svc['base_cost'] = real_cost
                        svc['price'] = real_cost  # Base cost before markup
                        if match['available_count'] > 0:
                            svc['available'] = match['available_count']
                        updated_services_count += 1

        with open(catalog_path, 'w', encoding='utf-8') as f:
            json.dump(catalog, f, indent=2)
        print(f"[+] Updated {updated_services_count} services in {catalog_path} with real wholesale base costs.")

    # 2. Update app/data/5sim_us_services.json
    if os.path.exists(us_services_path) and 'usa' in raw_5sim_data:
        usa_svcs = raw_5sim_data['usa']
        with open(us_services_path, 'r', encoding='utf-8') as f:
            us_data = json.load(f)

        updated_us = 0
        for item in us_data:
            sc = item.get('service_code')
            op = item.get('operator')
            if sc in usa_svcs and op in usa_svcs[sc]:
                cost = float(usa_svcs[sc][op].get('cost') or 0.0)
                count = int(usa_svcs[sc][op].get('count') or 0)
                if cost > 0:
                    item['price_usd'] = round(cost, 2)
                    item['count'] = count
                    updated_us += 1

        with open(us_services_path, 'w', encoding='utf-8') as f:
            json.dump(us_data, f, indent=2)
        print(f"[+] Updated {updated_us} US route items in {us_services_path} with real 5SIM wholesale prices.")

    # Invalidate SIMProviderService memory cache
    SIMProviderService._cached_raw_catalog = None
    SIMProviderService._cached_5sim_us_services_raw = None
    print("[+] Cleared in-memory catalog cache for immediate application.")
    return True


def export_csv_report(raw_5sim_data, output_file='5sim_wholesale_prices.csv'):
    """Export all available wholesale numbers and costs into a CSV report."""
    rows = []
    for country, svcs in raw_5sim_data.items():
        for svc_code, ops in svcs.items():
            for op_name, info in ops.items():
                cost = float(info.get('cost') or 0.0)
                count = int(info.get('count') or 0)
                if count > 0 or cost > 0:
                    rows.append({
                        'Country': country,
                        'Service': svc_code,
                        'Operator': op_name,
                        'Wholesale_Cost_USD': f"{cost:.4f}",
                        'Available_Stock': count
                    })

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['Country', 'Service', 'Operator', 'Wholesale_Cost_USD', 'Available_Stock'])
        writer.writeheader()
        writer.writerows(rows)
    print(f"[+] Exported {len(rows)} wholesale pricing entries to {output_file}.")


def main():
    parser = argparse.ArgumentParser(description="5SIM Wholesale Price Viewer & Catalog Synchronizer")
    parser.add_argument('--search', type=str, help='Search wholesale prices for a service across popular countries (e.g. whatsapp, telegram, google)')
    parser.add_argument('--country', type=str, help='Show real 5SIM wholesale prices for a specific country (e.g. england, usa, nigeria)')
    parser.add_argument('--export-csv', action='store_true', help='Export complete 5SIM price book to CSV')
    parser.add_argument('--sync-only', action='store_true', help='Sync catalog without extra output')
    args = parser.parse_args()

    data = fetch_5sim_live_prices()
    if not data:
        sys.exit(1)

    # Search for a service
    if args.search:
        q = args.search.strip().lower()
        print(f"\n=== REAL 5SIM WHOLESALE PRICES FOR: {q.upper()} ===")
        print(f"{'Country':<15} {'Operator':<15} {'Cost ($ USD)':<15} {'Available Stock':<15}")
        print("-" * 60)
        popular_countries = ['england', 'usa', 'nigeria', 'kenya', 'india', 'indonesia', 'philippines', 'brazil', 'canada', 'germany']
        for c in popular_countries:
            if c in data and q in data[c]:
                ops = data[c][q]
                with_stock = [(op, info['cost'], info.get('count', 0)) for op, info in ops.items() if info.get('count', 0) > 0]
                if with_stock:
                    with_stock.sort(key=lambda x: x[1])
                    for op, cost, count in with_stock[:2]:
                        print(f"{c:<15} {op:<15} ${cost:<14.2f} {count:<15}")
                else:
                    lowest = sorted([(op, info['cost']) for op, info in ops.items()], key=lambda x: x[1])[0]
                    print(f"{c:<15} {lowest[0]:<15} ${lowest[1]:<14.2f} (0 in stock)")

    # Country report
    elif args.country:
        c = args.country.strip().lower()
        if c in data:
            print(f"\n=== REAL 5SIM WHOLESALE PRICES FOR COUNTRY: {c.upper()} ===")
            print(f"{'Service':<20} {'Best Operator':<15} {'Cost ($ USD)':<15} {'Available Stock':<15}")
            print("-" * 65)
            best_svcs = extract_best_service_prices(data, c)
            # Sort by highest available stock first
            sorted_svcs = sorted(best_svcs.values(), key=lambda x: x['available_count'], reverse=True)
            for s in sorted_svcs[:35]:
                print(f"{s['service_code']:<20} {s['best_operator']:<15} ${s['wholesale_cost']:<14.2f} {s['available_count']:<15}")
        else:
            print(f"[-] Country '{c}' not found in 5SIM price book.")

    if args.export_csv:
        export_csv_report(data)

    # Always sync catalog to update live wholesale prices
    print("\n[*] Updating catalog with live wholesale prices...")
    sync_catalog(data)
    print("\n[OK] Catalog sync complete! Numbers now reflect real wholesale costs with your configured profit margin applied.")


if __name__ == '__main__':
    main()
