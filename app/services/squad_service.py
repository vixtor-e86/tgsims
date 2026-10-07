"""
Squad (GetSquad.Africa) Payment Gateway Service for Tgsims.
Handles:
  1. Dedicated Virtual Account (Permanent - auto-credits wallet on transfer)
  2. Dynamic Virtual Account (Temporary bank transfer)
  3. Card payments via Squad inline checkout

Squad Docs: https://developer.squadco.com/
"""
import os
import hashlib
import hmac
import uuid
import datetime
import requests
from app.config import Config
from app.services.db_service import DBService


class SquadService:
    """
    Squad payment gateway integration.
    Provides dedicated virtual bank accounts, dynamic virtual accounts,
    and card payment links for Nigerian naira funding.
    """

    SANDBOX_BASE_URL = 'https://sandbox-api-d.squadco.com'
    LIVE_BASE_URL = 'https://api-d.squadco.com'

    @classmethod
    def get_secret_key(cls) -> str:
        return (os.getenv('SQUAD_SECRET_KEY') or getattr(Config, 'SQUAD_SECRET_KEY', '') or '').strip()

    @classmethod
    def get_public_key(cls) -> str:
        return (os.getenv('SQUAD_PUBLIC_KEY') or getattr(Config, 'SQUAD_PUBLIC_KEY', '') or '').strip()

    @classmethod
    def is_sandbox(cls) -> bool:
        secret = cls.get_secret_key()
        # Squad sandbox keys start with sandbox_ or test_
        return secret.startswith('sandbox_') or secret.startswith('test_')

    @classmethod
    def get_base_url(cls) -> str:
        return cls.SANDBOX_BASE_URL if cls.is_sandbox() else cls.LIVE_BASE_URL

    @classmethod
    def is_configured(cls) -> bool:
        return bool(cls.get_secret_key() and cls.get_public_key())

    @classmethod
    def _headers(cls) -> dict:
        return {
            'Authorization': f'Bearer {cls.get_secret_key()}',
            'Content-Type': 'application/json'
        }

    @classmethod
    def _get(cls, endpoint: str, params: dict = None) -> dict:
        url = f"{cls.get_base_url()}/{endpoint.lstrip('/')}"
        try:
            resp = requests.get(url, headers=cls._headers(), params=params, timeout=20)
            data = resp.json()
            if resp.status_code in (200, 201):
                return {'success': True, 'data': data.get('data', data)}
            err = data.get('message') or data.get('error') or resp.text
            return {'success': False, 'message': str(err), 'status_code': resp.status_code}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    @classmethod
    def _post(cls, endpoint: str, payload: dict) -> dict:
        url = f"{cls.get_base_url()}/{endpoint.lstrip('/')}"
        try:
            resp = requests.post(url, json=payload, headers=cls._headers(), timeout=20)
            data = resp.json()
            if resp.status_code in (200, 201):
                return {'success': True, 'data': data.get('data', data)}
            err = data.get('message') or data.get('error') or resp.text
            return {'success': False, 'message': str(err), 'status_code': resp.status_code}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    # =========================================================================
    # DEDICATED VIRTUAL ACCOUNT (Permanent - Wallet auto-credit on deposit)
    # =========================================================================

    @classmethod
    def create_dedicated_virtual_account(cls, user_id: str, full_name: str,
                                          email: str, phone: str = '',
                                          bvn: str = '') -> dict:
        """
        Creates a permanent dedicated virtual account for the user.
        Once created, any bank transfer to this account auto-credits their wallet.
        """
        if not cls.is_configured():
            return {'success': False, 'message': 'Payment gateway not configured.'}

        # Customer ref must be unique per user
        customer_ref = f"TGS{user_id[:8].replace('-', '').upper()}"

        payload = {
            'customer_identifier': customer_ref,
            'first_name': (full_name.split(' ')[0] if ' ' in full_name else full_name)[:50],
            'last_name': (full_name.split(' ', 1)[1] if ' ' in full_name else 'User')[:50],
            'middle_name': '',
            'email': email,
            'phone': phone or '08000000000',
            'bvn': bvn or '',
        }

        result = cls._post('virtual-account/create', payload)
        return result

    @classmethod
    def get_dedicated_account(cls, customer_identifier: str) -> dict:
        """Retrieves an existing dedicated virtual account by customer identifier."""
        return cls._get(f'virtual-account/{customer_identifier}')

    @classmethod
    def get_all_dedicated_accounts(cls) -> dict:
        """Retrieves all dedicated virtual accounts on the merchant."""
        return cls._get('virtual-account')

    # =========================================================================
    # DYNAMIC VIRTUAL ACCOUNT (Temporary - expires after payment)
    # =========================================================================

    @classmethod
    def create_dynamic_virtual_account(cls, amount_ngn: float, user_id: str,
                                        user_email: str = '') -> dict:
        """
        Creates a temporary dynamic virtual account for a specific payment amount.
        User sends exact NGN amount; account expires after transaction or timeout.
        """
        if not cls.is_configured():
            return {'success': False, 'message': 'Payment gateway not configured.'}

        order_ref = f"TGS-BNK-{uuid.uuid4().hex[:10].upper()}"
        amount_kobo = int(round(amount_ngn * 100))  # Squad expects amount in kobo

        payload = {
            'amount': amount_kobo,
            'email': user_email or 'user@tgsims.com',
            'initiation_point': 'inline',
            'expiry_life': 10,  # minutes before account expires
            'beneficiaries': [],
            'reference': order_ref,
            'currency': 'NGN',
        }

        result = cls._post('payment/dynamic-virtual-account', payload)
        if result.get('success'):
            data = result['data']
            return {
                'success': True,
                'reference': order_ref,
                'account_number': data.get('virtual_account_number') or data.get('account_number'),
                'bank_name': data.get('bank_name') or 'GTBank',
                'account_name': data.get('account_name') or 'Tgsims Wallet',
                'amount_ngn': amount_ngn,
                'expires_in_minutes': 10,
                'raw': data
            }
        return result

    # =========================================================================
    # CARD PAYMENT (Squad Inline Checkout)
    # =========================================================================

    @classmethod
    def initialize_card_payment(cls, amount_ngn: float, user_id: str,
                                 user_email: str, callback_url: str = None) -> dict:
        """
        Initializes a Squad card payment transaction.
        Returns a checkout URL or transaction reference for Squad inline checkout.
        """
        if not cls.is_configured():
            return {'success': False, 'message': 'Payment gateway not configured.'}

        order_ref = f"TGS-CARD-{uuid.uuid4().hex[:10].upper()}"
        amount_kobo = int(round(amount_ngn * 100))

        payload = {
            'amount': amount_kobo,
            'email': user_email,
            'currency': 'NGN',
            'transaction_ref': order_ref,
            'callback_url': callback_url or 'https://tgsims.com/api/payments/squad/card/callback',
            'payment_channels': ['card'],
            'is_recurring': False,
            'pass_charge': False,  # Platform absorbs fee
        }

        result = cls._post('transaction/initiate', payload)
        if result.get('success'):
            data = result['data']
            checkout_url = data.get('checkout_url') or data.get('url') or ''
            return {
                'success': True,
                'reference': order_ref,
                'checkout_url': checkout_url,
                'amount_ngn': amount_ngn,
                'public_key': cls.get_public_key(),
                'raw': data
            }
        return result

    # =========================================================================
    # WEBHOOK VERIFICATION
    # =========================================================================

    @classmethod
    def verify_webhook_signature(cls, payload_body: bytes, received_hash: str) -> bool:
        """
        Verifies Squad webhook HMAC-SHA512 signature.
        Squad sends: x-squad-encrypted-body: HMAC-SHA512(body, secret_key)
        """
        secret = cls.get_secret_key()
        if not secret or not received_hash:
            return False
        try:
            computed = hmac.new(
                key=secret.encode('utf-8'),
                msg=payload_body,
                digestmod=hashlib.sha512
            ).hexdigest()
            return hmac.compare_digest(computed.lower(), received_hash.lower())
        except Exception as e:
            print(f"[Squad] Webhook signature verification error: {e}")
            return False

    # =========================================================================
    # TRANSACTION VERIFICATION
    # =========================================================================

    @classmethod
    def verify_transaction(cls, transaction_ref: str) -> dict:
        """Verifies a transaction status directly with Squad."""
        result = cls._get(f'transaction/verify/{transaction_ref}')
        return result

    # =========================================================================
    # PROCESS INCOMING WEBHOOK (Auto-credit wallet)
    # =========================================================================

    @classmethod
    def process_webhook(cls, payload: dict) -> dict:
        """
        Processes an incoming Squad webhook event and credits user wallet.
        Handles: virtual account deposits, card payments.
        """
        event = payload.get('Event') or payload.get('event') or ''
        body = payload.get('Body') or payload.get('data') or payload

        transaction_ref = (body.get('transaction_ref') or body.get('reference') or
                           body.get('virtual_account_number') or '')

        # --- Dedicated Virtual Account Deposit ---
        if event in ('virtual-account/approve', 'charge.success', 'virtual_account_payment'):
            amount_ngn = float(body.get('principal_amount') or body.get('amount') or 0) / 100
            account_number = body.get('virtual_account_number') or ''
            sender_name = body.get('sender_name') or 'Bank Transfer'
            squad_ref = body.get('transaction_ref') or body.get('reference') or ''

            if not amount_ngn:
                return {'success': False, 'message': 'Zero amount payment ignored.'}

            # Look up user by virtual account
            user_id = DBService.get_user_by_virtual_account(account_number)
            if not user_id:
                print(f"[Squad] No user found for virtual account: {account_number}")
                return {'success': False, 'message': f'No user for account {account_number}'}

            # Convert NGN to USD for wallet
            from app.services.settings_service import SettingsService
            settings = SettingsService.get_settings()
            ngn_per_usd = float(settings.get('ngn_per_usd_rate', 1600))
            amount_usd = round(amount_ngn / ngn_per_usd, 4)

            ref_key = f"SQ-VA-{squad_ref or uuid.uuid4().hex[:10].upper()}"

            # Idempotency check
            if DBService.transaction_exists(ref_key):
                return {'success': True, 'already_processed': True}

            credit_res = DBService.credit_wallet_balance(
                user_id=user_id,
                amount=amount_usd,
                trans_type='deposit',
                reference=ref_key,
                description=f"Bank Transfer - ₦{amount_ngn:,.2f} from {sender_name}",
                metadata={
                    'gateway': 'squad',
                    'type': 'virtual_account',
                    'amount_ngn': amount_ngn,
                    'account_number': account_number,
                    'sender_name': sender_name,
                    'squad_ref': squad_ref,
                    'payment_channel': 'bank_transfer'
                }
            )

            if credit_res.get('success'):
                try:
                    DBService.create_user_notification(
                        user_id=user_id,
                        title="Bank Transfer Received!",
                        message=f"₦{amount_ngn:,.2f} (${amount_usd:.2f}) credited from {sender_name}.",
                        type="deposit",
                        link="/wallet",
                        metadata={'amount_ngn': amount_ngn, 'amount_usd': amount_usd}
                    )
                except Exception:
                    pass

            return credit_res

        # --- Card Payment Success ---
        elif event in ('charge.success', 'transaction.success') and body.get('transaction_ref', '').startswith('TGS-CARD-'):
            squad_ref = body.get('transaction_ref') or body.get('reference') or ''
            amount_ngn = float(body.get('amount') or 0) / 100
            user_email = body.get('email') or ''

            if not amount_ngn:
                return {'success': False, 'message': 'Zero amount card payment ignored.'}

            # Look up user by transaction reference in DB
            tx = DBService.get_transaction_by_reference(squad_ref)
            if not tx:
                print(f"[Squad] Card payment: no transaction found for ref {squad_ref}")
                return {'success': False, 'message': f'Transaction {squad_ref} not found'}

            user_id = tx.get('user_id')
            if not user_id:
                return {'success': False, 'message': 'No user linked to card transaction'}

            if tx.get('status') == 'completed':
                return {'success': True, 'already_processed': True}

            from app.services.settings_service import SettingsService
            settings = SettingsService.get_settings()
            ngn_per_usd = float(settings.get('ngn_per_usd_rate', 1600))
            amount_usd = round(amount_ngn / ngn_per_usd, 4)

            # Mark transaction completed
            DBService.complete_pending_payment(squad_ref, amount_ngn=amount_ngn, amount_usd=amount_usd)

            try:
                DBService.create_user_notification(
                    user_id=user_id,
                    title="Card Payment Successful!",
                    message=f"₦{amount_ngn:,.2f} (${amount_usd:.2f}) added to your wallet via card.",
                    type="deposit",
                    link="/wallet"
                )
            except Exception:
                pass

            return {'success': True, 'credited': True, 'amount_usd': amount_usd}

        return {'success': True, 'message': f'Event {event} acknowledged but not processed.'}
