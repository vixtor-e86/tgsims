import random
import uuid
import time

class SIMProviderService:
    """Service adapter for communicating with Virtual SIM / eSIM APIs."""
    
    @staticmethod
    def get_catalog():
        """Returns available countries and service rates."""
        return [
            {
                'country_code': 'US',
                'country_name': 'United States',
                'flag': '🇺🇸',
                'services': [
                    {'name': 'WhatsApp', 'price': 2.50, 'available': 1420, 'category': 'SMS Verification'},
                    {'name': 'Telegram', 'price': 2.20, 'available': 890, 'category': 'SMS Verification'},
                    {'name': 'OpenAI / ChatGPT', 'price': 3.00, 'available': 450, 'category': 'SMS Verification'},
                    {'name': 'Google / Gmail', 'price': 1.50, 'available': 2300, 'category': 'SMS Verification'},
                    {'name': 'Tinder', 'price': 2.00, 'available': 610, 'category': 'SMS Verification'},
                    {'name': 'eSIM 5GB Travel Data', 'price': 12.00, 'available': 999, 'category': 'eSIM Data'}
                ]
            },
            {
                'country_code': 'GB',
                'country_name': 'United Kingdom',
                'flag': '🇬🇧',
                'services': [
                    {'name': 'WhatsApp', 'price': 1.80, 'available': 950, 'category': 'SMS Verification'},
                    {'name': 'Telegram', 'price': 1.60, 'available': 1120, 'category': 'SMS Verification'},
                    {'name': 'Instagram', 'price': 1.40, 'available': 1500, 'category': 'SMS Verification'},
                    {'name': 'eSIM 10GB Europe', 'price': 18.00, 'available': 999, 'category': 'eSIM Data'}
                ]
            },
            {
                'country_code': 'CA',
                'country_name': 'Canada',
                'flag': '🇨🇦',
                'services': [
                    {'name': 'WhatsApp', 'price': 2.40, 'available': 420, 'category': 'SMS Verification'},
                    {'name': 'Telegram', 'price': 2.10, 'available': 380, 'category': 'SMS Verification'},
                    {'name': 'TikTok', 'price': 1.90, 'available': 750, 'category': 'SMS Verification'}
                ]
            },
            {
                'country_code': 'DE',
                'country_name': 'Germany',
                'flag': '🇩🇪',
                'services': [
                    {'name': 'WhatsApp', 'price': 2.00, 'available': 540, 'category': 'SMS Verification'},
                    {'name': 'Telegram', 'price': 1.90, 'available': 600, 'category': 'SMS Verification'},
                    {'name': 'eSIM Unlimited 7 Days', 'price': 25.00, 'available': 999, 'category': 'eSIM Data'}
                ]
            },
            {
                'country_code': 'NG',
                'country_name': 'Nigeria',
                'flag': '🇳🇬',
                'services': [
                    {'name': 'WhatsApp', 'price': 1.20, 'available': 3100, 'category': 'SMS Verification'},
                    {'name': 'Telegram', 'price': 1.00, 'available': 4200, 'category': 'SMS Verification'},
                    {'name': 'Bank Verification', 'price': 1.50, 'available': 1200, 'category': 'SMS Verification'}
                ]
            }
        ]

    @staticmethod
    def purchase_number(country_code, service_name):
        """Simulates buying a number from the provider API."""
        prefix_map = {
            'US': '+1 555',
            'GB': '+44 7700',
            'CA': '+1 416',
            'DE': '+49 151',
            'NG': '+234 803'
        }
        prefix = prefix_map.get(country_code, '+1 555')
        random_digits = f"{random.randint(100,999)}-{random.randint(1000,9999)}"
        phone_number = f"{prefix} {random_digits}"
        order_ref = f"TGS-SIM-{random.randint(10000, 99999)}"
        provider_id = f"PRV-{uuid.uuid4().hex[:10].upper()}"
        
        is_esim = 'esim' in service_name.lower()
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=LPA:1$esim.tgsims.com${provider_id}" if is_esim else None

        return {
            'success': True,
            'order_reference': order_ref,
            'phone_number': phone_number,
            'provider_order_id': provider_id,
            'is_esim': is_esim,
            'qr_code_url': qr_url,
            'status': 'active'
        }

    @staticmethod
    def check_sms(order_id):
        """Simulates fetching SMS code for an active order."""
        codes = ['381-902', '749-102', '129-847', '904-112', '552-390']
        chosen_code = random.choice(codes)
        return {
            'has_sms': True,
            'sms_code': chosen_code,
            'full_sms': f"Your verification code is {chosen_code}. Do not share this code with anyone."
        }
