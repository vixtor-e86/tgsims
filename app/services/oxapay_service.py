"""
OXAPay Cryptocurrency Payment Gateway Service.
Supports Nigeria, $1+ minimum, all major coins.
No third-party names are exposed to users on the frontend.
"""

import os
import hmac
import hashlib
import json
import datetime
import requests
from app.services.db_service import DBService

_OXAPAY_BASE = 'https://api.oxapay.com'


class OXAPayService:
    """OXAPay crypto payment gateway — invoices, status polling, and webhook verification."""

    MIN_DEPOSIT_USD: float = 1.0

    # Supported currencies shown in the UI (internal only — not shown on main fund page)
    SUPPORTED_CURRENCIES: list = [
        {'coin': 'USDT', 'network': 'TRON',     'label': 'USDT (TRC-20)'},
        {'coin': 'USDT', 'network': 'ETH',      'label': 'USDT (ERC-20)'},
        {'coin': 'USDT', 'network': 'BSC',      'label': 'USDT (BEP-20)'},
        {'coin': 'BTC',  'network': 'Bitcoin',  'label': 'Bitcoin (BTC)'},
        {'coin': 'ETH',  'network': 'ETH',      'label': 'Ethereum (ETH)'},
        {'coin': 'LTC',  'network': 'LTC',      'label': 'Litecoin (LTC)'},
        {'coin': 'TRX',  'network': 'TRON',     'label': 'TRON (TRX)'},
        {'coin': 'BNB',  'network': 'BSC',      'label': 'BNB (BEP-20)'},
        {'coin': 'SOL',  'network': 'SOL',      'label': 'Solana (SOL)'},
        {'coin': 'DOGE', 'network': 'DOGE',     'label': 'Dogecoin (DOGE)'},
    ]

    @staticmethod
    def get_api_key() -> str:
        key = (os.getenv('OXAPAY_API_KEY') or '').strip()
        if not key:
            # Fallback to config attribute
            try:
                from app.config import Config
                key = (Config.OXAPAY_API_KEY or '').strip()
            except Exception:
                pass
        return key

    @staticmethod
    def is_configured() -> bool:
        return bool(OXAPayService.get_api_key())

    # ------------------------------------------------------------------
    # Create Invoice
    # ------------------------------------------------------------------
    @staticmethod
    def create_payment(amount_usd: float, currency: str, network: str,
                       user_id: str, user_email: str, callback_url: str) -> dict:
        """
        Creates an OXAPay hosted payment invoice.
        Returns: { success, track_id, pay_link, amount_usd, currency, network }
        """
        api_key = OXAPayService.get_api_key()
        if not api_key:
            return {'success': False, 'message': 'Crypto payment gateway is currently unavailable.'}

        if amount_usd < OXAPayService.MIN_DEPOSIT_USD:
            return {
                'success': False,
                'message': f'Minimum crypto deposit is ${OXAPayService.MIN_DEPOSIT_USD:.2f} USD.'
            }

        # Normalise coin name for OXAPay (they use e.g. "USDT" not "USDT/TRON")
        pay_currency = currency.upper()

        order_id = f"TGS-{user_id[:8].replace('-','').upper()}-{datetime.datetime.utcnow().strftime('%H%M%S')}"

        payload = {
            'merchant':    api_key,
            'amount':      round(float(amount_usd), 2),
            'currency':    'USD',
            'payCurrency': pay_currency,
            'lifetime':    60,              # 60 minutes for the invoice to expire
            'callbackUrl': callback_url,
            'returnUrl':   callback_url.replace('/api/payments/crypto/webhook', '/wallet'),
            'orderId':     order_id,
            'description': f'Tgsims Wallet Topup — ${amount_usd:.2f}'
        }

        try:
            resp = requests.post(
                f'{_OXAPAY_BASE}/merchants/request',
                json=payload,
                timeout=20
            )
            data = resp.json()
        except Exception as e:
            print(f'[OXAPay] create_payment HTTP error: {e}')
            return {'success': False, 'message': 'Could not reach payment gateway. Please try again.'}

        # OXAPay returns result=100 on success
        if data.get('result') != 100:
            msg = data.get('message', 'Failed to create crypto invoice.')
            print(f'[OXAPay] create_payment error: {msg} | full: {data}')
            return {'success': False, 'message': msg}

        track_id = str(data.get('trackId', ''))
        pay_link  = data.get('payLink') or data.get('paymentLink') or ''

        if not track_id:
            return {'success': False, 'message': 'Gateway did not return a valid invoice ID.'}

        # Persist pending deposit record in DB
        DBService.record_pending_crypto_deposit(
            user_id=user_id,
            amount_usd=amount_usd,
            payment_id=track_id,
            pay_address=pay_link,   # OXAPay gives hosted page, not raw address
            pay_amount=amount_usd,
            pay_currency=pay_currency,
            network=network,
            order_id=order_id,
            extra_meta={
                'gateway':   'oxapay',
                'pay_link':  pay_link,
                'user_email': user_email,
            }
        )

        qr_code_url = f"https://api.qrserver.com/v1/create-qr-code/?size=260x260&margin=6&data={pay_link}" if pay_link else ""

        return {
            'success':     True,
            'track_id':    track_id,
            'pay_link':    pay_link,
            'qr_code_url': qr_code_url,
            'amount_usd':  amount_usd,
            'currency':    pay_currency,
            'network':     network,
            'order_id':    order_id,
        }

    # ------------------------------------------------------------------
    # Poll Payment Status
    # ------------------------------------------------------------------
    @staticmethod
    def get_payment_status(track_id: str) -> dict:
        """
        Fetches the latest status of an OXAPay invoice from their API.
        Statuses: Waiting | Confirming | Paid | Expired | Failed
        """
        api_key = OXAPayService.get_api_key()
        if not api_key:
            return {'success': False, 'status': 'Unknown', 'message': 'Gateway unavailable.'}

        try:
            resp = requests.post(
                f'{_OXAPAY_BASE}/merchants/inquiry',
                json={'merchant': api_key, 'trackId': track_id},
                timeout=15
            )
            data = resp.json()
        except Exception as e:
            print(f'[OXAPay] get_payment_status HTTP error: {e}')
            return {'success': False, 'status': 'Unknown', 'message': 'Could not check payment status.'}

        if data.get('result') != 100:
            return {
                'success': False,
                'status':  'Unknown',
                'message': data.get('message', 'Status check failed.')
            }

        raw_status = data.get('status', 'Waiting')
        return {
            'success':   True,
            'status':    raw_status,
            'track_id':  track_id,
            'amount':    data.get('amount'),
            'pay_amount': data.get('payAmount'),
            'pay_currency': data.get('payCurrency'),
            'raw':       data
        }

    # ------------------------------------------------------------------
    # Webhook Signature Verification
    # ------------------------------------------------------------------
    @staticmethod
    def verify_webhook_signature(payload_body: bytes, received_hmac: str) -> bool:
        """
        OXAPay webhooks include an HMAC-SHA512 signature in the 'hmac' header.
        Secret = merchant API key.
        """
        api_key = OXAPayService.get_api_key()
        if not api_key or not received_hmac:
            return False
        try:
            computed = hmac.new(
                api_key.encode('utf-8'),
                payload_body,
                hashlib.sha512
            ).hexdigest()
            return hmac.compare_digest(computed.lower(), received_hmac.lower())
        except Exception as e:
            print(f'[OXAPay] verify_webhook_signature error: {e}')
            return False

    # ------------------------------------------------------------------
    # Process Payment Update (webhook or status poll)
    # ------------------------------------------------------------------
    @staticmethod
    def process_payment_update(track_id: str,
                               webhook_payload: dict = None,
                               skip_remote_fetch: bool = False) -> dict:
        """
        Unified handler for both webhook-push and status-poll flows.
        Credits user wallet on Paid status; marks failed/expired otherwise.
        """
        if webhook_payload and not skip_remote_fetch:
            raw_status = webhook_payload.get('status', 'Waiting')
            actually_paid = webhook_payload.get('payAmount') or webhook_payload.get('amount')
            pay_currency  = webhook_payload.get('payCurrency', '')
            amount_usd    = webhook_payload.get('amount')
        else:
            remote = OXAPayService.get_payment_status(track_id)
            if not remote.get('success'):
                return {'success': False, 'status': 'unknown', 'message': remote.get('message', 'Status check failed.')}
            raw_status    = remote.get('status', 'Waiting')
            actually_paid = remote.get('pay_amount')
            pay_currency  = remote.get('pay_currency', '')
            amount_usd    = remote.get('amount')

        status_lower = raw_status.lower()

        if status_lower == 'paid':
            result = DBService.complete_crypto_deposit(
                payment_id=track_id,
                actually_paid=float(actually_paid) if actually_paid else None,
                notes='OXAPay IPN verified',
                metadata_update={'pay_currency': pay_currency, 'raw_status': raw_status}
            )
            if result.get('success'):
                # Fire user notification
                try:
                    user_id = result.get('user_id')
                    amount  = result.get('amount', 0.0)
                    if user_id:
                        DBService.create_user_notification(
                            user_id=user_id,
                            title='Crypto Deposit Confirmed!',
                            message=f'${amount:.2f} has been credited to your wallet. New balance: ${result.get("new_balance", 0.0):.2f}.',
                            type='deposit',
                            link='/wallet'
                        )
                except Exception:
                    pass
            return {
                'success':    result.get('success', False),
                'status':     'paid',
                'is_completed': True,
                'message':    result.get('message', 'Payment completed.'),
                'amount':     result.get('amount'),
                'new_balance': result.get('new_balance')
            }

        elif status_lower in ('expired', 'failed', 'canceled', 'cancelled'):
            DBService.fail_crypto_deposit(
                payment_id=track_id,
                reason=f'OXAPay status: {raw_status}'
            )
            return {
                'success': False,
                'status':  status_lower,
                'is_completed': False,
                'message': f'Payment {raw_status.lower()}.'
            }

        elif status_lower == 'confirming':
            return {
                'success': True,
                'status':  'confirming',
                'is_completed': False,
                'message': 'Payment received and confirming on blockchain…'
            }

        # Waiting / other
        return {
            'success': True,
            'status':  status_lower or 'waiting',
            'is_completed': False,
            'message': 'Awaiting payment…'
        }
