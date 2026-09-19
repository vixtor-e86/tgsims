import os
import json
import hmac
import hashlib
import uuid
import datetime
import requests
from app.config import Config
from app.services.db_service import DBService


class NOWPaymentsService:
    """
    Enterprise NOWPayments Cryptographic Payment Gateway Service.
    Handles dynamic payment address generation, rate estimation,
    tamper-proof HMAC-SHA512 webhook signature verification,
    and automated atomic wallet crediting with idempotency protection.
    """

    SUPPORTED_CURRENCIES = [
        {
            'ticker': 'usdttrc20',
            'symbol': 'USDT',
            'name': 'Tether (USDT - TRC20)',
            'network': 'Tron (TRC-20)',
            'badge': 'Popular & Fast',
            'icon': 'usdt'
        },
        {
            'ticker': 'usdtbsc',
            'symbol': 'USDT',
            'name': 'Tether (USDT - BEP20)',
            'network': 'BNB Smart Chain (BEP-20)',
            'badge': 'Lowest Network Fee',
            'icon': 'usdt'
        },
        {
            'ticker': 'usdterc20',
            'symbol': 'USDT',
            'name': 'Tether (USDT - ERC20)',
            'network': 'Ethereum (ERC-20)',
            'badge': 'High Liquidity',
            'icon': 'usdt'
        },
        {
            'ticker': 'ltc',
            'symbol': 'LTC',
            'name': 'Litecoin (LTC)',
            'network': 'Litecoin Network',
            'badge': 'Ultra Low Fee',
            'icon': 'ltc'
        },
        {
            'ticker': 'sol',
            'symbol': 'SOL',
            'name': 'Solana (SOL)',
            'network': 'Solana Network',
            'badge': 'Instant Finality',
            'icon': 'sol'
        },
        {
            'ticker': 'trx',
            'symbol': 'TRX',
            'name': 'TRON (TRX)',
            'network': 'Tron Network',
            'badge': 'Fast',
            'icon': 'trx'
        },
        {
            'ticker': 'btc',
            'symbol': 'BTC',
            'name': 'Bitcoin (BTC)',
            'network': 'Bitcoin Network',
            'badge': 'Original Crypto',
            'icon': 'btc'
        },
        {
            'ticker': 'eth',
            'symbol': 'ETH',
            'name': 'Ethereum (ETH)',
            'network': 'Ethereum Network',
            'badge': 'Standard',
            'icon': 'eth'
        },
        {
            'ticker': 'bnbbsc',
            'symbol': 'BNB',
            'name': 'Binance Coin (BNB)',
            'network': 'BNB Smart Chain (BEP-20)',
            'badge': 'BSC Native',
            'icon': 'bnb'
        },
        {
            'ticker': 'doge',
            'symbol': 'DOGE',
            'name': 'Dogecoin (DOGE)',
            'network': 'Dogecoin Network',
            'badge': 'Popular',
            'icon': 'doge'
        }
    ]

    @classmethod
    def get_api_key(cls) -> str:
        return (os.getenv('NOWPAYMENTS_API_KEY') or getattr(Config, 'NOWPAYMENTS_API_KEY', '') or '').strip()

    @classmethod
    def get_ipn_secret(cls) -> str:
        return (os.getenv('NOWPAYMENTS_IPN_SECRET') or getattr(Config, 'NOWPAYMENTS_IPN_SECRET', '') or '').strip()

    @classmethod
    def get_base_url(cls) -> str:
        return (os.getenv('NOWPAYMENTS_BASE_URL') or getattr(Config, 'NOWPAYMENTS_BASE_URL', 'https://api.nowpayments.io/v1')).strip().rstrip('/')

    @classmethod
    def is_configured(cls) -> bool:
        return bool(cls.get_api_key() and cls.get_ipn_secret())

    @classmethod
    def check_api_status(cls) -> dict:
        """Verifies connection with NOWPayments API."""
        api_key = cls.get_api_key()
        if not api_key:
            return {'success': False, 'message': 'NOWPayments API key is not configured.'}
        try:
            resp = requests.get(
                f"{cls.get_base_url()}/status",
                headers={'x-api-key': api_key},
                timeout=10
            )
            data = resp.json() if resp.status_code == 200 else {}
            return {'success': resp.status_code == 200, 'data': data, 'status_code': resp.status_code}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    @classmethod
    def get_min_amount(cls, pay_currency: str) -> float:
        """Returns the minimum deposit amount in USD for the selected crypto currency."""
        api_key = cls.get_api_key()
        if not api_key:
            return 20.0
        try:
            resp = requests.get(
                f"{cls.get_base_url()}/min-amount",
                params={'currency_from': 'usd', 'currency_to': pay_currency.lower()},
                headers={'x-api-key': api_key},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                return float(data.get('min_amount') or 20.0)
        except Exception as e:
            print(f"[NOWPayments] get_min_amount error for {pay_currency}: {e}")
        return 20.0

    @classmethod
    def estimate_price(cls, amount_usd: float, pay_currency: str) -> dict:
        """Calculates estimated crypto amount for a given USD fiat value."""
        api_key = cls.get_api_key()
        if not api_key:
            return {'success': False, 'message': 'NOWPayments is not configured.'}
        try:
            resp = requests.get(
                f"{cls.get_base_url()}/estimate",
                params={'amount': amount_usd, 'currency_from': 'usd', 'currency_to': pay_currency.lower()},
                headers={'x-api-key': api_key},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    'success': True,
                    'estimated_amount': data.get('estimated_amount'),
                    'currency_to': data.get('currency_to'),
                    'amount_from': data.get('amount_from')
                }
            return {'success': False, 'message': f"Estimate error: {resp.text}"}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    @classmethod
    def create_payment(cls, amount_usd: float, pay_currency: str, user_id: str,
                       user_email: str = '', ipn_callback_url: str = None) -> dict:
        """
        Creates a dedicated cryptocurrency payment session with NOWPayments.
        Generates a unique crypto deposit address, exact crypto amount, and records
        the pending transaction in Tgsims database for real-time tracking.
        """
        api_key = cls.get_api_key()
        if not api_key:
            return {'success': False, 'message': 'Cryptocurrency gateway is currently offline (API key missing).'}

        pay_currency = pay_currency.lower().strip()
        is_stablecoin = pay_currency in ('usdttrc20', 'usdtbsc', 'usdterc20', 'usdt', 'usdc', 'usdcbsc', 'usdcerc20')
        min_amt = max(20.0, cls.get_min_amount(pay_currency))
        if amount_usd < 20.0:
            return {
                'success': False,
                'message': f"Minimum deposit for Cryptocurrency is $20.00 USD (~ NGN {int(20.0 * 1600):,}). Please enter $20.00 or more."
            }

        order_id = f"TGS-DEP-{uuid.uuid4().hex[:10].upper()}"
        payload = {
            'price_amount': float(amount_usd),
            'price_currency': 'usd',
            'pay_currency': pay_currency,
            'order_id': order_id,
            'order_description': f"Tgsims Wallet Top-up (${amount_usd:.2f})",
            'is_fee_paid_by_user': False
        }
        # For USDT/USDC, enforce exact 1:1 USD amount so user sends clean $20 instead of 19.968958
        if is_stablecoin:
            payload['pay_amount'] = float(amount_usd)

        if ipn_callback_url:
            payload['ipn_callback_url'] = ipn_callback_url
        if user_email:
            payload['customer_email'] = user_email

        try:
            resp = requests.post(
                f"{cls.get_base_url()}/payment",
                json=payload,
                headers={'x-api-key': api_key, 'Content-Type': 'application/json'},
                timeout=15
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                payment_id = str(data.get('payment_id'))
                pay_address = data.get('pay_address')
                raw_pay_amount = float(data.get('pay_amount') or (amount_usd if is_stablecoin else 0.0))
                if is_stablecoin:
                    pay_amount = round(raw_pay_amount, 2)
                    pay_amount_str = f"{pay_amount:.2f}"
                else:
                    pay_amount = raw_pay_amount
                    pay_amount_str = f"{pay_amount:.6f}".rstrip('0').rstrip('.')

                network = data.get('network') or ''
                expiration = data.get('expiration_estimate_date') or ''

                # Record pending transaction in Supabase
                DBService.record_pending_crypto_deposit(
                    user_id=user_id,
                    amount_usd=amount_usd,
                    payment_id=payment_id,
                    pay_address=pay_address,
                    pay_amount=pay_amount,
                    pay_currency=pay_currency,
                    network=network,
                    order_id=order_id,
                    extra_meta={
                        'expiration_estimate_date': expiration,
                        'valid_until': data.get('valid_until'),
                        'purchase_id': str(data.get('purchase_id', ''))
                    }
                )

                # Return frontend-ready data (no secrets exposed)
                return {
                    'success': True,
                    'payment_id': payment_id,
                    'pay_address': pay_address,
                    'pay_amount': pay_amount_str,
                    'pay_currency': pay_currency.upper(),
                    'network': network.upper() if network else pay_currency.upper(),
                    'price_amount_usd': amount_usd,
                    'order_id': order_id,
                    'expiration_estimate_date': expiration,
                    'payin_extra_id': data.get('payin_extra_id'),
                    'qr_code_url': f"https://api.qrserver.com/v1/create-qr-code/?size=260x260&margin=10&data={pay_address}"
                }
            else:
                err_data = resp.json() if resp.headers.get('Content-Type') == 'application/json' else resp.text
                err_msg = err_data.get('message') if isinstance(err_data, dict) else str(err_data)
                return {'success': False, 'message': f"NOWPayments error: {err_msg}"}

        except Exception as e:
            print(f"[NOWPayments] create_payment exception: {e}")
            return {'success': False, 'message': f"Failed to initialize payment gateway: {str(e)}"}

    @classmethod
    def get_payment_status(cls, payment_id: str) -> dict:
        """Fetches the authoritative live payment status directly from NOWPayments API."""
        api_key = cls.get_api_key()
        if not api_key:
            return {'success': False, 'message': 'API key not configured.'}
        try:
            resp = requests.get(
                f"{cls.get_base_url()}/payment/{payment_id}",
                headers={'x-api-key': api_key},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                return {'success': True, 'data': data}
            return {'success': False, 'message': f"Status fetch error: {resp.status_code}"}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    @classmethod
    def verify_ipn_signature(cls, payload: dict, received_sig: str) -> bool:
        """
        Cryptographically validates the incoming webhook against the IPN secret key
        using HMAC-SHA512 with alphabetical key sorting and timing attack prevention.
        """
        secret = cls.get_ipn_secret()
        if not secret or not received_sig:
            return False

        try:
            # 1. Sort dictionary keys alphabetically and dump compact JSON
            sorted_payload = json.dumps(payload, separators=(',', ':'), sort_keys=True)
            # 2. Compute HMAC-SHA512
            expected_sig = hmac.new(
                key=secret.encode('utf-8'),
                msg=sorted_payload.encode('utf-8'),
                digestmod=hashlib.sha512
            ).hexdigest()
            # 3. Constant-time comparison
            return hmac.compare_digest(expected_sig.lower(), received_sig.lower())
        except Exception as e:
            print(f"[NOWPayments] IPN signature verification exception: {e}")
            return False

    @classmethod
    def process_payment_update(cls, payment_id: str, webhook_payload: dict = None,
                               skip_remote_fetch: bool = False) -> dict:
        """
        Processes a payment update with dual-layer security:
        1. Queries NOWPayments server out-of-band to verify actual status.
        2. Idempotently credits wallet on confirmation.
        """
        payment_id = str(payment_id).strip()
        if not payment_id:
            return {'success': False, 'message': 'Missing payment ID.'}

        remote_data = None
        if not skip_remote_fetch:
            status_res = cls.get_payment_status(payment_id)
            if status_res.get('success'):
                remote_data = status_res.get('data')

        data = remote_data or webhook_payload or {}
        payment_status = (data.get('payment_status') or '').lower().strip()
        actually_paid = float(data.get('actually_paid') or 0.0)
        pay_currency = (data.get('pay_currency') or '').upper()

        # SUCCESSFUL COMPLETION STATES
        if payment_status in ('finished', 'confirmed', 'sending'):
            credit_res = DBService.complete_crypto_deposit(
                payment_id=payment_id,
                actually_paid=actually_paid,
                notes=f"Automated NOWPayments IPN verification ({payment_status.upper()})",
                metadata_update={
                    'nowpayments_status': payment_status,
                    'actually_paid': actually_paid,
                    'outcome_amount': data.get('outcome_amount'),
                    'payin_hash': data.get('payin_hash'),
                    'payout_hash': data.get('payout_hash')
                }
            )
            return {
                'success': True,
                'status': payment_status,
                'credited': credit_res.get('success', False),
                'already_completed': credit_res.get('already_completed', False),
                'new_balance': credit_res.get('new_balance')
            }

        # FAILED OR EXPIRED STATES
        elif payment_status in ('failed', 'expired', 'refunded'):
            DBService.fail_crypto_deposit(
                payment_id=payment_id,
                reason=f"Payment marked as {payment_status} by NOWPayments"
            )
            return {
                'success': True,
                'status': payment_status,
                'credited': False,
                'message': f"Payment is {payment_status}"
            }

        # PENDING / CONFIRMING STATES
        else:
            return {
                'success': True,
                'status': payment_status or 'waiting',
                'credited': False,
                'message': f"Payment is currently {payment_status or 'waiting'}"
            }
