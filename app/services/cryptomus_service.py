"""
Cryptomus Payment Gateway Service for Tgsims.
Replaces NOWPayments with Cryptomus for lower minimum deposit ($1+).
Handles crypto invoice creation, webhook verification, and wallet crediting.
Docs: https://doc.cryptomus.com/
"""
import os
import uuid
import hashlib
import hmac
import base64
import json
import datetime
import requests
from app.config import Config
from app.services.db_service import DBService


class CryptomusService:
    """
    Cryptomus Cryptocurrency Payment Gateway.
    Supports minimum deposits from $1 USD - far lower than NowPayments ($20 min).
    Accepts USDT, BTC, ETH, LTC, SOL, TRX, BNB, DOGE and more.
    """

    SUPPORTED_CURRENCIES = [
        {
            'ticker': 'USDT',
            'network': 'TRON',
            'symbol': 'USDT',
            'name': 'Tether (USDT - TRC20)',
            'display_network': 'Tron (TRC-20)',
            'badge': 'Popular & Fast',
            'icon': 'usdt'
        },
        {
            'ticker': 'USDT',
            'network': 'BSC',
            'symbol': 'USDT',
            'name': 'Tether (USDT - BEP20)',
            'display_network': 'BNB Smart Chain (BEP-20)',
            'badge': 'Lowest Fee',
            'icon': 'usdt'
        },
        {
            'ticker': 'USDT',
            'network': 'ETH',
            'symbol': 'USDT',
            'name': 'Tether (USDT - ERC20)',
            'display_network': 'Ethereum (ERC-20)',
            'badge': 'High Liquidity',
            'icon': 'usdt'
        },
        {
            'ticker': 'LTC',
            'network': 'LTC',
            'symbol': 'LTC',
            'name': 'Litecoin (LTC)',
            'display_network': 'Litecoin Network',
            'badge': 'Ultra Low Fee',
            'icon': 'ltc'
        },
        {
            'ticker': 'SOL',
            'network': 'SOL',
            'symbol': 'SOL',
            'name': 'Solana (SOL)',
            'display_network': 'Solana Network',
            'badge': 'Instant Finality',
            'icon': 'sol'
        },
        {
            'ticker': 'TRX',
            'network': 'TRON',
            'symbol': 'TRX',
            'name': 'TRON (TRX)',
            'display_network': 'Tron Network',
            'badge': 'Fast',
            'icon': 'trx'
        },
        {
            'ticker': 'BTC',
            'network': 'BTC',
            'symbol': 'BTC',
            'name': 'Bitcoin (BTC)',
            'display_network': 'Bitcoin Network',
            'badge': 'Original Crypto',
            'icon': 'btc'
        },
        {
            'ticker': 'ETH',
            'network': 'ETH',
            'symbol': 'ETH',
            'name': 'Ethereum (ETH)',
            'display_network': 'Ethereum Network',
            'badge': 'Standard',
            'icon': 'eth'
        },
        {
            'ticker': 'BNB',
            'network': 'BSC',
            'symbol': 'BNB',
            'name': 'Binance Coin (BNB)',
            'display_network': 'BNB Smart Chain (BEP-20)',
            'badge': 'BSC Native',
            'icon': 'bnb'
        },
        {
            'ticker': 'DOGE',
            'network': 'DOGE',
            'symbol': 'DOGE',
            'name': 'Dogecoin (DOGE)',
            'display_network': 'Dogecoin Network',
            'badge': 'Popular',
            'icon': 'doge'
        },
    ]

    # Minimum deposit in USD (Cryptomus supports as low as $1)
    MIN_DEPOSIT_USD = 1.0

    BASE_URL = 'https://api.cryptomus.com/v1'

    @classmethod
    def get_merchant_id(cls) -> str:
        return (os.getenv('CRYPTOMUS_MERCHANT_ID') or getattr(Config, 'CRYPTOMUS_MERCHANT_ID', '') or '').strip()

    @classmethod
    def get_payment_api_key(cls) -> str:
        return (os.getenv('CRYPTOMUS_PAYMENT_API_KEY') or getattr(Config, 'CRYPTOMUS_PAYMENT_API_KEY', '') or '').strip()

    @classmethod
    def get_payout_api_key(cls) -> str:
        return (os.getenv('CRYPTOMUS_PAYOUT_API_KEY') or getattr(Config, 'CRYPTOMUS_PAYOUT_API_KEY', '') or '').strip()

    @classmethod
    def is_configured(cls) -> bool:
        return bool(cls.get_merchant_id() and cls.get_payment_api_key())

    @classmethod
    def _make_sign(cls, data: dict, api_key: str) -> str:
        """
        Cryptomus signature: base64(json_body) + api_key  => md5 hash
        """
        encoded = base64.b64encode(json.dumps(data, separators=(',', ':')).encode()).decode()
        raw = encoded + api_key
        return hashlib.md5(raw.encode()).hexdigest()

    @classmethod
    def _request(cls, method: str, endpoint: str, data: dict, api_key: str) -> dict:
        """Internal HTTP request helper with signature injection."""
        sign = cls._make_sign(data, api_key)
        merchant_id = cls.get_merchant_id()
        headers = {
            'merchant': merchant_id,
            'sign': sign,
            'Content-Type': 'application/json'
        }
        url = f"{cls.BASE_URL}/{endpoint.lstrip('/')}"
        try:
            if method.upper() == 'POST':
                resp = requests.post(url, json=data, headers=headers, timeout=20)
            else:
                resp = requests.get(url, params=data, headers=headers, timeout=20)

            resp_json = resp.json()
            if resp.status_code in (200, 201):
                return {'success': True, 'data': resp_json.get('result', resp_json)}
            err_msg = resp_json.get('message') or resp_json.get('error', {}).get('message') or resp.text
            return {'success': False, 'message': err_msg, 'status_code': resp.status_code}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    @classmethod
    def create_payment(cls, amount_usd: float, currency: str, network: str,
                       user_id: str, user_email: str = '',
                       callback_url: str = None) -> dict:
        """
        Creates a Cryptomus payment invoice.
        Returns payment address, QR code, and payment_uuid for tracking.
        """
        if not cls.is_configured():
            return {'success': False, 'message': 'Crypto gateway is currently offline (not configured).'}

        if amount_usd < cls.MIN_DEPOSIT_USD:
            return {
                'success': False,
                'message': f'Minimum cryptocurrency deposit is ${cls.MIN_DEPOSIT_USD:.2f} USD. Please enter ${cls.MIN_DEPOSIT_USD:.2f} or more.'
            }

        order_id = f"TGS-CM-{uuid.uuid4().hex[:10].upper()}"

        payload = {
            'amount': str(round(amount_usd, 2)),
            'currency': 'USD',
            'to_currency': currency.upper(),
            'network': network.upper(),
            'order_id': order_id,
            'is_payment_multiple': False,
            'lifetime': 7200,  # 2 hours
        }

        if callback_url:
            payload['url_callback'] = callback_url
        if user_email:
            payload['additional_data'] = user_email

        api_key = cls.get_payment_api_key()
        result = cls._request('POST', 'payment', payload, api_key)

        if not result.get('success'):
            return {'success': False, 'message': result.get('message', 'Failed to initialize crypto payment.')}

        data = result['data']
        payment_uuid = data.get('uuid')
        pay_address = data.get('address')
        pay_amount = data.get('payer_amount') or data.get('amount') or str(amount_usd)
        pay_currency = data.get('payer_currency') or currency.upper()
        pay_network = data.get('network') or network.upper()
        expired_at = data.get('expired_at', '')

        # Store pending deposit in DB
        DBService.record_pending_crypto_deposit(
            user_id=user_id,
            amount_usd=amount_usd,
            payment_id=payment_uuid,
            pay_address=pay_address,
            pay_amount=float(pay_amount) if pay_amount else amount_usd,
            pay_currency=pay_currency,
            network=pay_network,
            order_id=order_id,
            extra_meta={
                'gateway': 'cryptomus',
                'order_id': order_id,
                'expired_at': str(expired_at),
                'user_email': user_email
            }
        )

        return {
            'success': True,
            'payment_id': payment_uuid,
            'pay_address': pay_address,
            'pay_amount': str(pay_amount),
            'pay_currency': pay_currency.upper(),
            'network': pay_network.upper(),
            'price_amount_usd': amount_usd,
            'order_id': order_id,
            'expired_at': str(expired_at),
            'qr_code_url': f"https://api.qrserver.com/v1/create-qr-code/?size=260x260&margin=10&data={pay_address}"
        }

    @classmethod
    def get_payment_status(cls, payment_uuid: str) -> dict:
        """Fetches live status of a Cryptomus payment invoice."""
        if not cls.is_configured():
            return {'success': False, 'message': 'Gateway not configured.'}

        api_key = cls.get_payment_api_key()
        payload = {'uuid': payment_uuid}
        result = cls._request('POST', 'payment/info', payload, api_key)

        if result.get('success'):
            return {'success': True, 'data': result['data']}
        return {'success': False, 'message': result.get('message', 'Status fetch error.')}

    @classmethod
    def verify_webhook_signature(cls, payload_body: bytes, received_sign: str) -> bool:
        """
        Verifies Cryptomus webhook signature.
        Cryptomus sends: sign = md5(base64(payload_without_sign) + api_key)
        """
        api_key = cls.get_payment_api_key()
        if not api_key or not received_sign:
            return False
        try:
            data = json.loads(payload_body)
            # Remove sign from payload before verification
            data.pop('sign', None)
            encoded = base64.b64encode(json.dumps(data, separators=(',', ':')).encode()).decode()
            raw = encoded + api_key
            expected = hashlib.md5(raw.encode()).hexdigest()
            return hmac.compare_digest(expected.lower(), received_sign.lower())
        except Exception as e:
            print(f"[Cryptomus] Webhook signature verification error: {e}")
            return False

    @classmethod
    def process_payment_update(cls, payment_uuid: str, webhook_payload: dict = None,
                               skip_remote_fetch: bool = False) -> dict:
        """
        Processes a Cryptomus payment event.
        Verifies status remotely (or uses webhook payload) and credits wallet on success.
        """
        payment_uuid = str(payment_uuid).strip()
        if not payment_uuid:
            return {'success': False, 'message': 'Missing payment UUID.'}

        remote_data = None
        if not skip_remote_fetch:
            status_res = cls.get_payment_status(payment_uuid)
            if status_res.get('success'):
                remote_data = status_res.get('data')

        data = remote_data or webhook_payload or {}
        payment_status = (data.get('status') or data.get('payment_status') or '').lower().strip()

        # CONFIRMED / COMPLETED STATES
        if payment_status in ('paid', 'paid_over', 'wrong_amount_waiting', 'confirm_check'):
            if payment_status in ('paid', 'paid_over'):
                actually_paid = float(data.get('payer_amount') or data.get('actually_paid') or 0.0)
                credit_res = DBService.complete_crypto_deposit(
                    payment_id=payment_uuid,
                    actually_paid=actually_paid,
                    notes=f"Cryptomus IPN verified ({payment_status.upper()})",
                    metadata_update={
                        'cryptomus_status': payment_status,
                        'actually_paid': actually_paid,
                        'txid': data.get('txid'),
                        'gateway': 'cryptomus'
                    }
                )
                return {
                    'success': True,
                    'status': payment_status,
                    'credited': credit_res.get('success', False),
                    'already_completed': credit_res.get('already_completed', False),
                    'new_balance': credit_res.get('new_balance')
                }
            # confirm_check or wrong_amount_waiting - still confirming
            return {
                'success': True,
                'status': 'confirming',
                'credited': False,
                'message': 'Transaction detected, awaiting blockchain confirmation.'
            }

        # FAILED / EXPIRED STATES
        elif payment_status in ('cancel', 'fail', 'system_fail', 'refund_process',
                                'refund_fail', 'refund_paid'):
            DBService.fail_crypto_deposit(
                payment_id=payment_uuid,
                reason=f"Cryptomus: payment {payment_status}"
            )
            return {
                'success': True,
                'status': 'failed',
                'credited': False,
                'message': f"Payment {payment_status}"
            }

        # WAITING / PENDING
        else:
            return {
                'success': True,
                'status': payment_status or 'waiting',
                'credited': False,
                'message': f"Payment is {payment_status or 'waiting for transaction'}"
            }
