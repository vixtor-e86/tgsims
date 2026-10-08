"""
Korapay Payment Gateway Service for Tgsims.
Handles Dedicated Virtual Bank Accounts (Permanent NGN bank accounts that auto-credit user wallets).

Korapay Docs: https://developers.korapay.com/docs/virtual-bank-accounts-ngn
"""
import os
import hmac
import hashlib
import uuid
import datetime
import requests
from typing import Dict, Any, Optional
from app.config import Config
from app.services.db_service import DBService
from app.services.settings_service import SettingsService


class KorapayService:
    """
    Korapay payment gateway integration.
    Provides permanent dedicated virtual bank accounts (Fidelity, Wema, etc.)
    and webhook processing to auto-credit user wallets on bank transfer.
    """

    BASE_URL = 'https://api.korapay.com/merchant/api/v1'

    SUPPORTED_BANKS = [
        {'code': '070', 'name': 'Fidelity Bank'},
        {'code': '035', 'name': 'Wema Bank'},
        {'code': '090405', 'name': 'Moniepoint'},
        {'code': '103', 'name': 'Globus Bank'},
        {'code': '033', 'name': 'UBA'},
        {'code': '104', 'name': 'Parallex Bank'},
        {'code': '214', 'name': 'FCMB'},
    ]

    @classmethod
    def get_secret_key(cls) -> str:
        return (os.getenv('KORAPAY_SECRET_KEY') or getattr(Config, 'KORAPAY_SECRET_KEY', '') or '').strip()

    @classmethod
    def get_public_key(cls) -> str:
        return (os.getenv('KORAPAY_PUBLIC_KEY') or getattr(Config, 'KORAPAY_PUBLIC_KEY', '') or '').strip()

    @classmethod
    def get_encryption_key(cls) -> str:
        return (os.getenv('KORAPAY_ENCRYPTION_KEY') or getattr(Config, 'KORAPAY_ENCRYPTION_KEY', '') or '').strip()

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
        url = f"{cls.BASE_URL}/{endpoint.lstrip('/')}"
        try:
            resp = requests.get(url, headers=cls._headers(), params=params, timeout=20)
            data = resp.json()
            if resp.status_code in (200, 201) and data.get('status') is True:
                return {'success': True, 'data': data.get('data', data)}
            err = data.get('message') or data.get('error') or resp.text
            return {'success': False, 'message': str(err), 'status_code': resp.status_code, 'raw': data}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    @classmethod
    def _post(cls, endpoint: str, payload: dict) -> dict:
        url = f"{cls.BASE_URL}/{endpoint.lstrip('/')}"
        try:
            resp = requests.post(url, json=payload, headers=cls._headers(), timeout=25)
            data = resp.json()
            if resp.status_code in (200, 201) and data.get('status') is True:
                return {'success': True, 'data': data.get('data', data)}
            err = data.get('message') or data.get('error') or resp.text
            return {'success': False, 'message': str(err), 'status_code': resp.status_code, 'raw': data}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    # =========================================================================
    # DEDICATED VIRTUAL ACCOUNT CREATION
    # =========================================================================

    @classmethod
    def create_virtual_account(cls, user_id: str, full_name: str, email: str,
                               bvn: str, bank_code: str = '070',
                               nin: str = '') -> dict:
        """
        Creates a permanent dedicated virtual account for the user via Korapay.
        Requires BVN as per CBN/NIBSS regulations.
        """
        if not cls.is_configured():
            return {
                'success': False,
                'message': 'Korapay payment gateway is not configured. Please check API keys.'
            }

        # Clean BVN: must be exactly 11 digits
        clean_bvn = ''.join(c for c in (bvn or '') if c.isdigit())
        if len(clean_bvn) != 11:
            return {
                'success': False,
                'message': 'A valid 11-digit Bank Verification Number (BVN) is required to generate your dedicated bank account.'
            }

        # Unique reference per creation
        account_ref = f"TGS-VBA-{user_id[:8].upper()}-{uuid.uuid4().hex[:6].upper()}"

        clean_name = full_name.strip() if full_name else 'Tgsims User'
        clean_email = email.strip() if email else 'user@tgsims.com'

        payload = {
            'account_name': clean_name[:100],
            'account_reference': account_ref,
            'permanent': True,
            'bank_code': bank_code or '070',
            'customer': {
                'name': clean_name[:100],
                'email': clean_email
            },
            'kyc': {
                'bvn': clean_bvn
            }
        }
        if nin and nin.strip():
            payload['kyc']['nin'] = nin.strip()

        result = cls._post('virtual-bank-account', payload)

        if not result.get('success'):
            raw_msg = result.get('message', '')
            raw_data = result.get('raw', {})
            # Check for specific merchant activation notice
            if 'not enabled' in raw_msg.lower() or 'not enabled' in str(raw_data).lower():
                return {
                    'success': False,
                    'code': 'MERCHANT_NOT_ENABLED',
                    'message': (
                        'Virtual bank account service is not yet enabled on this Korapay merchant account. '
                        'Please request activation for "Virtual Bank Accounts" in your Korapay Dashboard '
                        'or contact support@korapay.com.'
                    )
                }
            return {
                'success': False,
                'message': raw_msg or 'Failed to generate virtual account from Korapay.'
            }

        data = result.get('data', {})
        account_number = data.get('account_number')
        account_name = data.get('account_name') or clean_name
        bank_name = data.get('bank_name') or 'Fidelity Bank'
        unique_id = data.get('unique_id') or data.get('account_reference') or account_ref

        return {
            'success': True,
            'data': {
                'account_number': account_number,
                'account_name': account_name,
                'bank_name': bank_name,
                'bank_code': bank_code,
                'account_reference': account_ref,
                'unique_id': unique_id,
                'raw': data
            }
        }

    @classmethod
    def get_virtual_account_details(cls, account_reference: str) -> dict:
        """Retrieves details of an existing virtual bank account from Korapay."""
        return cls._get(f'virtual-bank-account/{account_reference}')

    @classmethod
    def verify_charge(cls, reference: str) -> dict:
        """Queries transaction details by reference."""
        return cls._get(f'charges/{reference}')

    # =========================================================================
    # WEBHOOK VERIFICATION & PROCESSING
    # =========================================================================

    @classmethod
    def verify_webhook_signature(cls, raw_body: bytes, signature_header: str) -> bool:
        """
        Validates Korapay HMAC SHA256 signature in `x-korapay-signature` header.
        """
        if not signature_header:
            return False
        secret = cls.get_secret_key()
        if not secret:
            return False
        try:
            if isinstance(raw_body, str):
                raw_body = raw_body.encode('utf-8')
            computed = hmac.new(secret.encode('utf-8'), raw_body, hashlib.sha256).hexdigest()
            return hmac.compare_digest(computed.lower(), signature_header.strip().lower())
        except Exception as e:
            print(f"[Korapay] Signature verification error: {e}")
            return False

    @classmethod
    def process_webhook(cls, payload: dict, raw_body: bytes = None, signature: str = None) -> dict:
        """
        Processes incoming Korapay webhook notification.
        Handles event 'charge.success' for virtual bank account transfers.
        """
        # Signature check if provided
        if raw_body and signature:
            if not cls.verify_webhook_signature(raw_body, signature):
                print("[Korapay Webhook] Invalid HMAC signature detected!")
                return {'success': False, 'message': 'Invalid signature'}

        event = payload.get('event')
        if event != 'charge.success':
            print(f"[Korapay Webhook] Ignored non-payment event: {event}")
            return {'success': True, 'message': f"Ignored event {event}"}

        data = payload.get('data') or {}
        reference = data.get('reference') or ''
        status = data.get('status', '').lower()

        if status != 'success':
            print(f"[Korapay Webhook] Transaction {reference} status is '{status}', not 'success'.")
            return {'success': True, 'message': 'Payment not successful yet.'}

        ref_key = f"KPY-VA-{reference}"

        # Idempotency check: has this reference been credited before?
        if DBService.transaction_exists(ref_key):
            print(f"[Korapay Webhook] Transaction {ref_key} already processed. Skipping.")
            return {'success': True, 'message': 'Transaction already processed.'}

        amount_ngn = float(data.get('amount') or 0.0)
        currency = data.get('currency', 'NGN')

        # Extract virtual account details from payload
        va_details = data.get('virtual_bank_account_details') or {}
        vba = va_details.get('virtual_bank_account') or data.get('virtual_bank_account') or {}

        account_number = vba.get('account_number') or ''
        account_ref = vba.get('account_reference') or ''

        # Look up user by account number
        user_id = None
        if account_number:
            user_id = DBService.get_user_by_virtual_account(account_number)

        # Fallback: query account by reference if not found
        if not user_id and account_ref:
            user_id = DBService.get_user_by_virtual_account_ref(account_ref)

        if not user_id:
            print(f"[Korapay Webhook] No user found for virtual account: {account_number} (ref: {account_ref})")
            return {'success': False, 'message': f'Account not linked to any user: {account_number}'}

        # Exchange rate: convert NGN to USD
        settings = SettingsService.get_settings()
        rate = float(settings.get('ngn_per_usd_rate', 1600.00))
        if rate <= 0:
            rate = 1600.00
        amount_usd = round(amount_ngn / rate, 2)

        if amount_usd <= 0:
            print(f"[Korapay Webhook] Computed USD amount {amount_usd} is <= 0 for NGN {amount_ngn}.")
            return {'success': False, 'message': 'Invalid deposit amount.'}

        # Payer information for transaction metadata
        payer = va_details.get('payer_bank_account') or {}
        payer_name = payer.get('account_name', 'Bank Transfer')
        payer_bank = payer.get('bank_name', '')

        metadata = {
            'provider': 'korapay',
            'type': 'dedicated_virtual_account',
            'account_number': account_number,
            'account_reference': account_ref,
            'amount_ngn': amount_ngn,
            'ngn_per_usd_rate': rate,
            'currency': currency,
            'payer_name': payer_name,
            'payer_bank': payer_bank,
            'payment_channel': 'korapay_virtual_account',
            'raw_event': payload
        }

        # Credit wallet atomically
        tx_result = DBService.credit_wallet_balance(
            user_id=user_id,
            amount=amount_usd,
            trans_type='deposit',
            reference=ref_key,
            description=f"Bank Transfer (Korapay) - ₦{amount_ngn:,.2f}",
            metadata=metadata
        )

        if not tx_result.get('success'):
            print(f"[Korapay Webhook] Failed to credit wallet for {user_id}: {tx_result.get('message')}")
            return tx_result

        # Notify user
        try:
            DBService.create_user_notification(
                user_id=user_id,
                title="Wallet Funded (Bank Transfer)",
                message=(
                    f"Your dedicated virtual account received ₦{amount_ngn:,.2f}. "
                    f"${amount_usd:.2f} has been added to your balance."
                ),
                type="deposit",
                link="/wallet"
            )
        except Exception as e:
            print(f"[Korapay Webhook] Notification dispatch error: {e}")

        print(f"[Korapay Webhook] Successfully credited {user_id} with ${amount_usd:.2f} (₦{amount_ngn:,.2f})")
        return {
            'success': True,
            'user_id': user_id,
            'amount_usd': amount_usd,
            'amount_ngn': amount_ngn,
            'reference': ref_key
        }
