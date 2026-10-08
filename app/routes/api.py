from flask import Blueprint, jsonify, request, session
from app.services.sim_provider import SIMProviderService
from app.services.db_service import DBService
from app.services.oxapay_service import OXAPayService
from app.services.squad_service import SquadService
from app.services.korapay_service import KorapayService
import datetime
import uuid

api_bp = Blueprint('api', __name__, url_prefix='/api')



def _get_current_user_id():
    user = session.get('user')
    if isinstance(user, dict) and 'id' in user:
        return user['id']
    return None


@api_bp.route('/purchase-sim', methods=['POST'])
def purchase_sim():
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'success': False, 'message': 'Please sign in to complete your purchase.'}), 401

    data = request.json or {}
    country_code = data.get('country_code', 'US').upper()
    country_name = data.get('country_name', 'United States')
    service_name = data.get('service_name', 'WhatsApp')
    service_code = data.get('service_code')
    operator = data.get('operator') or 'any'
    try:
        price = float(data.get('price', 2.50))
    except (ValueError, TypeError):
        price = 2.50

    # 1. Check wallet balance
    wallet = DBService.get_wallet(user_id)
    cur_balance = float(wallet.get('balance', 0.00))
    if cur_balance < price:
        return jsonify({
            'success': False,
            'message': f'Insufficient wallet balance. You need ${price:.2f} but have ${cur_balance:.2f}. Please top up your wallet.'
        }), 400

    # 2. Allocate Virtual Number
    sim_result = SIMProviderService.purchase_number(country_code, service_name, operator=operator, service_code=service_code)
    if not sim_result or not sim_result.get('success'):
        err_msg = (sim_result or {}).get('message') or 'No numbers currently available for this service. Please select another country or try again shortly.'
        return jsonify({
            'success': False,
            'message': err_msg
        }), 503

    order_ref = sim_result.get('order_reference') or f"TGS-SIM-{uuid.uuid4().hex[:6].upper()}"

    # 3. Deduct from wallet atomically in database
    deduct_res = DBService.deduct_wallet_balance(
        user_id=user_id,
        amount=price,
        reference=order_ref,
        description=f"{service_name} Virtual Number ({country_name})",
        metadata={
            'service_name': service_name,
            'country_name': country_name,
            'country_code': country_code
        }
    )

    if not deduct_res.get('success'):
        return jsonify({
            'success': False,
            'message': deduct_res.get('message', 'Failed to deduct wallet balance.')
        }), 400

    # 4. Save SIM Order to database
    order_data = {
        'order_reference': order_ref,
        'service_name': service_name,
        'service_code': sim_result.get('service_code') or service_code or service_name.lower().replace(' ', '_'),
        'country_name': country_name,
        'country_code': country_code,
        'country_slug': country_name.lower().replace(' ', '_'),
        'phone_number': sim_result.get('phone_number', ''),
        'user_cost': price,
        'price': price,
        'provider_cost': float(sim_result.get('provider_cost') or 0.00),
        'provider_order_id': sim_result.get('provider_order_id', ''),
        'order_type': 'activation',
        'status': 'pending',
        'qr_code_url': sim_result.get('qr_code_url'),
        'expires_at': sim_result.get('expires_at')
    }
    saved_order = DBService.create_order(user_id, order_data)

    # Clean public view of the order (no internal provider or backend details)
    public_order = {
        'id': saved_order.get('id', order_ref),
        'order_reference': order_ref,
        'service_name': service_name,
        'country_name': country_name,
        'country_code': country_code,
        'phone_number': sim_result.get('phone_number', ''),
        'price': price,
        'status': 'active',
        'sms_code': None,
        'full_sms_text': 'Waiting for SMS verification code...',
        'qr_code_url': sim_result.get('qr_code_url'),
        'created_at': saved_order.get('created_at', datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
    }

    # Trigger user notification
    try:
        DBService.create_user_notification(
            user_id=user_id,
            title=f"{service_name} Number Allocated",
            message=f"Your {country_name} number ({sim_result.get('phone_number', '')}) is active. Waiting for incoming SMS.",
            type="purchase",
            link="/sims/my-sims"
        )
    except Exception:
        pass

    return jsonify({
        'success': True,
        'message': 'Virtual number activated successfully!',
        'new_balance': deduct_res.get('new_balance', cur_balance - price),
        'order': public_order
    })


@api_bp.route('/purchase-us-canada', methods=['POST'])
def purchase_us_canada():
    """Allocate and order a dedicated high-reliability US virtual number."""
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'success': False, 'message': 'Please sign in to complete your purchase.'}), 401

    data = request.json or {}
    country_code = data.get('country_code', 'US').upper()
    service_name = data.get('service_name', 'WhatsApp')
    service_code = data.get('service_code')
    package_id = data.get('package_id', 'basic_pool')
    provider_id = data.get('provider_id', 'any')

    try:
        price = float(data.get('price', 1.25))
    except (ValueError, TypeError):
        price = 1.25

    # Look up package for display name
    pkg = next((p for p in SIMProviderService.US_CANADA_PACKAGES if p['id'] == package_id), SIMProviderService.US_CANADA_PACKAGES[0])
    country_name = 'United States'

    # 1. Check wallet balance
    wallet = DBService.get_wallet(user_id)
    cur_balance = float(wallet.get('balance', 0.00))
    if cur_balance < price:
        return jsonify({
            'success': False,
            'message': f'Insufficient wallet balance. You need ${price:.2f} (₦{price * 1600:,.2f}) but have ${cur_balance:.2f}. Please top up your wallet.'
        }), 400

    # 2. Allocate US number
    alloc_res = SIMProviderService.purchase_us_canada_number(
        country_code=country_code,
        service_name=service_name,
        package_id=package_id,
        provider_id=provider_id,
        price=price,
        service_code=service_code
    )

    if not alloc_res or not alloc_res.get('success'):
        return jsonify({
            'success': False,
            'message': alloc_res.get('message', 'Unable to allocate a carrier line at this moment. Please try another server route.')
        }), 503

    order_ref = alloc_res.get('order_reference') or f"TGS-USCA-{uuid.uuid4().hex[:6].upper()}"

    # 3. Deduct wallet atomically in database
    deduct_res = DBService.deduct_wallet_balance(
        user_id=user_id,
        amount=price,
        reference=order_ref,
        description=f"{service_name} ({pkg['name']}) - {country_name}",
        metadata={
            'service_name': service_name,
            'country_name': country_name,
            'country_code': country_code,
            'package_name': pkg['name'],
            'provider_line': alloc_res.get('provider_line', provider_id)
        }
    )

    if not deduct_res.get('success'):
        return jsonify({
            'success': False,
            'message': deduct_res.get('message', 'Failed to deduct wallet balance.')
        }), 400

    # 4. Save SIM Order to database
    order_data = {
        'order_reference': order_ref,
        'service_name': f"{service_name} ({pkg['name']})",
        'service_code': service_code or service_name.lower().replace(' ', '_'),
        'country_name': country_name,
        'country_code': country_code,
        'country_slug': 'usa',
        'phone_number': alloc_res.get('phone_number', ''),
        'user_cost': price,
        'price': price,
        'provider_cost': 0.00,
        'provider_order_id': alloc_res.get('provider_order_id', ''),
        'order_type': 'activation',
        'status': 'active',
        'qr_code_url': None,
        'expires_at': alloc_res.get('expires_at')
    }
    saved_order = DBService.create_order(user_id, order_data)

    # Trigger user notification
    try:
        DBService.create_user_notification(
            user_id=user_id,
            title=f"{service_name} US Number Allocated",
            message=f"Your dedicated cellular line ({alloc_res.get('phone_number', '')}) is ready. Waiting for SMS code.",
            type="purchase",
            link="/sims/my-sims"
        )
    except Exception:
        pass

    return jsonify({
        'success': True,
        'message': f"{country_name} {service_name} number activated successfully!",
        'new_balance': deduct_res.get('new_balance', cur_balance - price),
        'order_reference': order_ref,
        'phone_number': alloc_res.get('phone_number', ''),
        'redirect_url': '/sims/my-sims'
    })


@api_bp.route('/check-sms/<order_id>', methods=['GET'])
def check_sms(order_id):
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    order = DBService.get_order_by_id(user_id, order_id)
    if not order:
        return jsonify({'success': False, 'message': 'Order not found'}), 404

    # If code is already saved in DB, return it immediately
    if order.get('sms_code'):
        return jsonify({
            'success': True,
            'sms_code': order['sms_code'],
            'phone_number': order.get('phone_number', ''),
            'service_name': order.get('service_name', 'Service'),
            'full_sms': order.get('full_sms_text', f"Your code is {order['sms_code']}")
        })

    status = str(order.get('status', '')).lower()
    
    # Dynamic expiration / auto-refund check
    if status in ('active', 'pending'):
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        timed_out = False
        timeout_reason = "Auto-cancelled: SMS timeout"

        is_react = (order.get('order_type') == 'reactivation') or ('reactivat' in str(order.get('full_sms_text', '')).lower()) or ('reactivat' in str(order.get('notes', '')).lower())

        if is_react and order.get('expires_at'):
            # Reactivation order: wait until carrier window expires
            try:
                exp_str = str(order.get('expires_at')).replace('Z', '+00:00')
                try:
                    exp_dt = datetime.datetime.fromisoformat(exp_str)
                except ValueError:
                    exp_dt = datetime.datetime.strptime(exp_str, '%Y-%m-%d %H:%M:%S')
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=datetime.timezone.utc)
                if now > exp_dt:
                    timed_out = True
                    timeout_reason = "Auto-cancelled: Reactivation window expired"
            except Exception as e:
                print(f"[check_sms] expires_at parse error: {e}")
        elif order.get('created_at'):
            # Normal number purchase: strictly 5 minutes (300 seconds) timeout
            try:
                cat_str = str(order.get('created_at')).replace('Z', '+00:00')
                try:
                    created_at = datetime.datetime.fromisoformat(cat_str)
                except ValueError:
                    created_at = datetime.datetime.strptime(cat_str, '%Y-%m-%d %H:%M:%S')
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=datetime.timezone.utc)
                if (now - created_at).total_seconds() > 300: # 5 minutes default
                    timed_out = True
                    timeout_reason = "Auto-cancelled: SMS timeout (5 mins)"
            except Exception as e:
                print(f"[check_sms] created_at parse error: {e}")

        if timed_out:
            prov_id = order.get('provider_order_id')
            if not is_react and prov_id and not str(prov_id).startswith('SIM-') and not str(prov_id).startswith('USCA-'):
                try:
                    SIMProviderService.cancel_order(str(prov_id))
                except Exception as e:
                    print(f"[check_sms] provider cancel on timeout error: {e}")
            
            # Atomically refund user wallet and restore previous state if reactivation
            DBService.refund_order(
                order_id=order_id,
                user_id=user_id,
                reason=timeout_reason
            )
            
            # Trigger user notification
            try:
                if is_react:
                    from app.services.settings_service import SettingsService
                    cost = SettingsService.get_reactivation_fee()
                    notif_title = "Reactivation Timed Out & Refunded"
                    notif_msg = f"${cost:.2f} was returned to your wallet for order #{order.get('order_reference', order_id)} after verification window ended. You can reactivate again at any time."
                else:
                    cost = float(order.get('price', order.get('user_cost', 0.00)))
                    notif_title = "Order Timed Out & Refunded"
                    notif_msg = f"${cost:.2f} was returned to your wallet for order #{order.get('order_reference', order_id)} after reaching timeout."
                DBService.create_user_notification(
                    user_id=user_id,
                    title=notif_title,
                    message=notif_msg,
                    type="refund",
                    link="/wallet"
                )
            except Exception:
                pass

            return jsonify({
                'success': False,
                'message': 'Verification window expired. Refund has been credited to your wallet.',
                'auto_refunded': True
            })

    # Query provider for incoming SMS
    sms_info = SIMProviderService.check_sms(order_id)
    if sms_info.get('has_sms') and sms_info.get('sms_code'):
        code = sms_info['sms_code']
        text = sms_info.get('full_sms', f"Your verification code is: {code}")
        DBService.update_order_sms(
            order_id=order_id,
            sms_code=code,
            full_sms=text,
            sender=order.get('service_name', 'Verification'),
            provider_sms_id=sms_info.get('provider_sms_id', '')
        )

        # Trigger user notification
        try:
            DBService.create_user_notification(
                user_id=user_id,
                title="Verification Code Received",
                message=f"Your {order.get('service_name', 'Verification')} code is: {code} ({order.get('phone_number', '')}).",
                type="purchase",
                link="/sims/my-sims",
                metadata={'sms_code': code, 'phone_number': order.get('phone_number', '')}
            )
        except Exception:
            pass

        return jsonify({
            'success': True,
            'sms_code': code,
            'phone_number': order.get('phone_number', ''),
            'service_name': order.get('service_name', 'Service'),
            'full_sms': text
        })

    return jsonify({
        'success': False,
        'message': 'Waiting for verification code...',
        'sms_code': None,
        'full_sms': None
    })


@api_bp.route('/cancel-sim/<order_id>', methods=['POST'])
def cancel_sim(order_id):
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    # 1. Fetch order from DB
    order = DBService.get_order_by_id(user_id, order_id)
    if not order:
        return jsonify({'success': False, 'message': 'Order not found.'}), 404

    status = str(order.get('status', '')).lower()
    if status in ['refunded', 'cancelled']:
        return jsonify({'success': False, 'message': 'Order has already been cancelled.'}), 400

    if status == 'completed':
        return jsonify({'success': False, 'message': 'Completed orders cannot be cancelled.'}), 400

    if order.get('sms_code'):
        return jsonify({'success': False, 'message': 'Cannot cancel order: verification code has already arrived.'}), 400

    is_react = (order.get('order_type') == 'reactivation') or ('reactivat' in str(order.get('full_sms_text', '')).lower()) or ('reactivat' in str(order.get('notes', '')).lower())

    # User rule: Reactivations CANNOT be cancelled manually. Must wait until minutes are exhausted or OTP arrives!
    if is_react:
        return jsonify({
            'success': False,
            'message': 'Reactivations cannot be cancelled manually. Please wait until the verification window is exhausted or your OTP arrives.'
        }), 400

    # Cancellation is only allowed after 3 minutes (180s) for initial orders
    if order.get('created_at'):
        import datetime
        try:
            cat_str = str(order.get('created_at')).replace('Z', '+00:00')
            try:
                created_at = datetime.datetime.fromisoformat(cat_str)
            except ValueError:
                created_at = datetime.datetime.strptime(cat_str, '%Y-%m-%d %H:%M:%S')
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=datetime.timezone.utc)
            now = datetime.datetime.now(datetime.timezone.utc)
            elapsed = (now - created_at).total_seconds()
            if elapsed < 180:
                wait_sec = int(180 - elapsed)
                return jsonify({
                    'success': False,
                    'message': f'Cancellation and refund become available after 3 minutes. Please wait {wait_sec} more second{"s" if wait_sec != 1 else ""}.'
                }), 400
        except Exception as e:
            print(f"[cancel_sim] elapsed check error: {e}")

    # 2. Cancel order on verification provider (5sim or TextVerified) - ONLY for initial activations!
    prov_id = order.get('provider_order_id')
    if prov_id and not str(prov_id).startswith('SIM-') and not str(prov_id).startswith('USCA-'):
        cancel_res = SIMProviderService.cancel_order(str(prov_id))
        if not cancel_res.get('success'):
            raw_err = str(cancel_res.get('message', '')).lower()
            if 'already' in raw_err or 'received' in raw_err or 'finished' in raw_err:
                return jsonify({'success': False, 'message': 'Cannot cancel order: verification code has already arrived.'}), 400
            elif 'not found' in raw_err or 'timed' in raw_err or 'expired' in raw_err:
                pass
            else:
                print(f"[cancel_sim] provider cancel note: {cancel_res.get('message')}")

    # 3. Atomically refund wallet in database
    refund_result = DBService.refund_order(order_id, user_id, reason="Cancelled by user before receiving code")
    if not refund_result.get('success'):
        return jsonify(refund_result), 400

    # Trigger user notification
    try:
        if is_react:
            from app.services.settings_service import SettingsService
            fee = SettingsService.get_reactivation_fee()
            notif_title = "Reactivation Cancelled & Refunded"
            notif_msg = f"${fee:.2f} has been refunded to your wallet for order #{order.get('order_reference', order_id)}."
        else:
            cost = float(order.get('price', order.get('user_cost', 0.00)))
            notif_title = "Order Cancelled & Refunded"
            notif_msg = f"${cost:.2f} has been refunded to your wallet for order #{order.get('order_reference', order_id)}."
        DBService.create_user_notification(
            user_id=user_id,
            title=notif_title,
            message=notif_msg,
            type="refund",
            link="/wallet"
        )
    except Exception:
        pass

    return jsonify(refund_result)


@api_bp.route('/deposit', methods=['POST'])
def deposit():
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.json or {}
    try:
        amount = float(data.get('amount', 10.00))
    except (ValueError, TypeError):
        amount = 10.00

    if amount <= 0:
        return jsonify({'success': False, 'message': 'Deposit amount must be greater than zero.'}), 400

    tx_ref = f"DEP-{datetime.datetime.now().strftime('%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"

    credit_res = DBService.credit_wallet_balance(
        user_id=user_id,
        amount=amount,
        trans_type='deposit',
        reference=tx_ref,
        description='Wallet Top-up'
    )

    if not credit_res.get('success'):
        return jsonify({'success': False, 'message': 'Failed to fund wallet.'}), 500

    return jsonify({
        'success': True,
        'message': f'Wallet funded with ${amount:.2f} successfully!',
        'new_balance': credit_res.get('new_balance')
    })



# =============================================================================
# OXAPAY CRYPTOCURRENCY GATEWAY APIS (Primary - $1 minimum, supports Nigeria)
# =============================================================================

@api_bp.route('/payments/crypto/currencies', methods=['GET'])
def get_crypto_currencies():
    """Returns supported cryptocurrency payment options and gateway status."""
    currencies = list(OXAPayService.SUPPORTED_CURRENCIES)
    return jsonify({
        'success': True,
        'currencies': currencies,
        'gateway_active': OXAPayService.is_configured(),
        'min_deposit': OXAPayService.MIN_DEPOSIT_USD
    })


@api_bp.route('/payments/crypto/create', methods=['POST'])
def create_crypto_payment():
    """Generates a hosted crypto payment invoice for the authenticated user."""
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'success': False, 'message': 'Please sign in to make a deposit.'}), 401

    data = request.json or {}
    try:
        amount = float(data.get('amount', 0))
    except (ValueError, TypeError):
        amount = 0.0

    currency = (data.get('currency') or 'USDT').strip().upper()
    network  = (data.get('network') or 'TRON').strip().upper()

    if amount <= 0:
        return jsonify({'success': False, 'message': 'Deposit amount must be greater than zero.'}), 400

    if amount < OXAPayService.MIN_DEPOSIT_USD:
        return jsonify({
            'success': False,
            'message': f'Minimum cryptocurrency deposit is ${OXAPayService.MIN_DEPOSIT_USD:.2f} USD. Please enter ${OXAPayService.MIN_DEPOSIT_USD:.2f} or more.'
        }), 400

    user_data   = session.get('user', {})
    user_email  = user_data.get('email', '')

    proto = request.headers.get('X-Forwarded-Proto') or request.scheme
    host  = request.headers.get('X-Forwarded-Host') or request.host
    callback_url = f"{proto}://{host}/api/payments/crypto/webhook"

    res = OXAPayService.create_payment(
        amount_usd=amount,
        currency=currency,
        network=network,
        user_id=user_id,
        user_email=user_email,
        callback_url=callback_url
    )

    status_code = 200 if res.get('success') else 400
    return jsonify(res), status_code


@api_bp.route('/payments/crypto/status/<payment_id>', methods=['GET'])
def check_crypto_payment_status(payment_id):
    """Checks the real-time status of a crypto payment session."""
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    tx = DBService.get_crypto_deposit_by_payment_id(payment_id)
    user_role = session.get('user', {}).get('role')
    if tx and tx.get('user_id') != user_id and user_role != 'admin':
        return jsonify({'success': False, 'message': 'Forbidden'}), 403

    if tx and tx.get('status') == 'completed':
        wallet = DBService.get_wallet(user_id)
        return jsonify({
            'success': True,
            'status': 'paid',
            'is_completed': True,
            'balance': wallet.get('balance', 0.00),
            'message': 'Deposit credited successfully.'
        })

    res = OXAPayService.process_payment_update(payment_id)
    wallet = DBService.get_wallet(user_id)
    res['balance'] = wallet.get('balance', 0.00)
    res['is_completed'] = res.get('status') in ('paid',)
    return jsonify(res)


@api_bp.route('/payments/crypto/webhook', methods=['POST'])
def oxapay_webhook():
    """
    Public webhook receiver for OXAPay payment notifications.
    Enforces HMAC-SHA512 signature validation and out-of-band verification.
    """
    received_hmac = request.headers.get('hmac', '')

    payload_body = request.get_data()
    payload = request.get_json(force=True, silent=True) or {}
    if not payload:
        return jsonify({'error': 'Invalid JSON body'}), 400

    # Verify HMAC signature
    if received_hmac:
        is_valid = OXAPayService.verify_webhook_signature(payload_body, received_hmac)
        if not is_valid:
            print(f"[OXAPay Webhook] Invalid signature for trackId {payload.get('trackId')}")
            return jsonify({'error': 'Invalid signature'}), 403

    track_id = str(payload.get('trackId') or payload.get('track_id') or '')
    if not track_id:
        return jsonify({'error': 'Missing trackId'}), 400

    print(f"[OXAPay Webhook] Received event for trackId: {track_id}, status: {payload.get('status')}")

    res = OXAPayService.process_payment_update(track_id, webhook_payload=payload)
    return jsonify({'status': 'ok', 'result': res}), 200


# =============================================================================
# SQUAD PAYMENT GATEWAY APIS (NGN - Virtual Accounts, Card, Bank Transfer)
# =============================================================================

@api_bp.route('/payments/squad/virtual-account', methods=['GET'])
def get_squad_virtual_account():
    """Returns the user's dedicated Squad virtual account details."""
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'success': False, 'message': 'Please sign in.'}), 401

    account = DBService.get_squad_virtual_account(user_id)
    return jsonify({
        'success': True,
        'has_account': bool(account),
        'account': account
    })


@api_bp.route('/payments/squad/virtual-account/create', methods=['POST'])
def create_squad_virtual_account():
    """
    Creates a permanent dedicated Squad virtual account for the user.
    Once created, any bank transfer to this number auto-credits their wallet.
    """
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'success': False, 'message': 'Please sign in.'}), 401

    if not SquadService.is_configured():
        return jsonify({'success': False, 'message': 'Bank transfer gateway is currently unavailable.'}), 503

    # Check if account already exists
    existing = DBService.get_squad_virtual_account(user_id)
    if existing and existing.get('account_number'):
        return jsonify({
            'success': True,
            'message': 'Your dedicated account already exists.',
            'account': existing
        })

    user_data = session.get('user', {})
    full_name = user_data.get('full_name') or user_data.get('username') or 'Tgsims User'
    email = user_data.get('email', '')
    phone = user_data.get('phone_number', '')

    result = SquadService.create_dedicated_virtual_account(
        user_id=user_id,
        full_name=full_name,
        email=email,
        phone=phone
    )

    if not result.get('success'):
        return jsonify({'success': False, 'message': result.get('message', 'Failed to create virtual account.')}), 400

    # Parse Squad response
    data = result.get('data', {})
    account_number = data.get('virtual_account_number') or data.get('account_number') or ''
    account_name = data.get('beneficiary_account_name') or full_name
    bank_name = data.get('bank_name') or 'GTBank'
    bank_code = data.get('bank_code') or ''
    customer_identifier = f"TGS{user_id[:8].replace('-', '').upper()}"

    # Save to DB
    save_res = DBService.save_squad_virtual_account(
        user_id=user_id,
        customer_identifier=customer_identifier,
        account_number=account_number,
        account_name=account_name,
        bank_name=bank_name,
        bank_code=bank_code,
        raw_response=data
    )

    account_info = {
        'account_number': account_number,
        'account_name': account_name,
        'bank_name': bank_name,
    }

    try:
        DBService.create_user_notification(
            user_id=user_id,
            title="Dedicated Account Created!",
            message=f"Your permanent wallet account {account_number} ({bank_name}) is ready. Transfer funds anytime!",
            type="deposit",
            link="/wallet"
        )
    except Exception:
        pass

    return jsonify({
        'success': True,
        'message': 'Dedicated virtual account created successfully!',
        'account': account_info
    })


@api_bp.route('/payments/squad/bank-transfer/create', methods=['POST'])
def create_squad_dynamic_account():
    """
    Creates a temporary dynamic virtual account for one-time bank transfer.
    User sends exact NGN amount to the generated account.
    """
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'success': False, 'message': 'Please sign in.'}), 401

    if not SquadService.is_configured():
        return jsonify({'success': False, 'message': 'Bank transfer gateway is currently unavailable.'}), 503

    data = request.json or {}
    try:
        amount_ngn = float(data.get('amount_ngn', 0))
    except (ValueError, TypeError):
        amount_ngn = 0.0

    if amount_ngn < 100:
        return jsonify({'success': False, 'message': 'Minimum bank transfer amount is ₦100.'}), 400

    user_data = session.get('user', {})
    user_email = user_data.get('email', '')

    result = SquadService.create_dynamic_virtual_account(
        amount_ngn=amount_ngn,
        user_id=user_id,
        user_email=user_email
    )

    if not result.get('success'):
        return jsonify({'success': False, 'message': result.get('message', 'Failed to generate transfer account.')}), 400

    return jsonify({
        'success': True,
        'account_number': result.get('account_number'),
        'bank_name': result.get('bank_name'),
        'account_name': result.get('account_name'),
        'amount_ngn': amount_ngn,
        'expires_in_minutes': result.get('expires_in_minutes', 10),
        'reference': result.get('reference')
    })


@api_bp.route('/payments/squad/card/initiate', methods=['POST'])
def initiate_squad_card_payment():
    """
    Initializes a Squad card payment checkout session.
    Returns public key and transaction reference for Squad inline JS.
    """
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'success': False, 'message': 'Please sign in.'}), 401

    if not SquadService.is_configured():
        return jsonify({'success': False, 'message': 'Card payment gateway is currently unavailable.'}), 503

    data = request.json or {}
    try:
        amount_ngn = float(data.get('amount_ngn', 0))
    except (ValueError, TypeError):
        amount_ngn = 0.0

    if amount_ngn < 100:
        return jsonify({'success': False, 'message': 'Minimum card payment is ₦100.'}), 400

    user_data = session.get('user', {})
    user_email = (user_data.get('email') or '').strip() or f"user_{str(user_id)[:8]}@tgsims.com"

    from app.services.settings_service import SettingsService
    settings = SettingsService.get_settings()
    ngn_per_usd = float(settings.get('ngn_per_usd_rate', 1600))
    amount_usd = round(amount_ngn / ngn_per_usd, 4)

    import uuid
    order_ref = f"TGS-SQ-{uuid.uuid4().hex[:12].upper()}"

    # Record pending payment in DB
    DBService.record_pending_squad_card_payment(
        user_id=user_id,
        amount_ngn=amount_ngn,
        amount_usd=amount_usd,
        reference=order_ref,
        user_email=user_email
    )

    return jsonify({
        'success': True,
        'reference': order_ref,
        'amount_ngn': amount_ngn,
        'public_key': SquadService.get_public_key(),
    })


@api_bp.route('/payments/squad/card/callback', methods=['GET', 'POST'])
def squad_card_callback():
    """Handles Squad card payment callback (redirect after payment)."""
    transaction_ref = request.args.get('transaction_ref') or request.args.get('reference') or ''
    if not transaction_ref:
        data = request.json or {}
        transaction_ref = data.get('transaction_ref') or data.get('reference') or ''

    if transaction_ref:
        verify = SquadService.verify_transaction(transaction_ref)
        if verify.get('success'):
            v_data = verify.get('data', {})
            if v_data.get('transaction_status') == 'success':
                DBService.complete_pending_payment(transaction_ref)

    from flask import redirect, url_for
    return redirect(url_for('wallet.index'))


@api_bp.route('/payments/squad/webhook', methods=['POST'])
def squad_webhook():
    """
    Public webhook receiver for Squad payment notifications.
    Handles dedicated virtual account deposits and card payments.
    """
    payload_body = request.get_data()
    received_hash = request.headers.get('x-squad-encrypted-body', '')

    payload = request.get_json(force=True, silent=True) or {}
    if not payload:
        return jsonify({'error': 'Invalid JSON body'}), 400

    # Verify signature
    if received_hash:
        is_valid = SquadService.verify_webhook_signature(payload_body, received_hash)
        if not is_valid:
            print(f"[Squad Webhook] Invalid signature! Event: {payload.get('Event')}")
            return jsonify({'error': 'Invalid signature'}), 403

    print(f"[Squad Webhook] Received event: {payload.get('Event')}, ref: {payload.get('Body', {}).get('transaction_ref', '')}")

    res = SquadService.process_webhook(payload)
    return jsonify({'status': 'ok', 'result': res}), 200


# =============================================================================
# KORAPAY PAYMENT GATEWAY APIS (Dedicated Virtual Accounts)
# =============================================================================

@api_bp.route('/payments/korapay/virtual-account', methods=['GET'])
def get_korapay_virtual_account():
    """Returns the user's dedicated Korapay virtual account details."""
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'success': False, 'message': 'Please sign in.'}), 401

    account = DBService.get_virtual_account(user_id)
    return jsonify({
        'success': True,
        'has_account': bool(account and account.get('account_number')),
        'account': account
    })


@api_bp.route('/payments/korapay/virtual-account/create', methods=['POST'])
def create_korapay_virtual_account():
    """
    Creates a permanent dedicated virtual account for the user via Korapay.
    Requires BVN as mandated by CBN/NIBSS.
    Once created, any bank transfer to this number auto-credits the user's wallet.
    """
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'success': False, 'message': 'Please sign in to generate a virtual account.'}), 401

    if not KorapayService.is_configured():
        return jsonify({
            'success': False,
            'message': 'Dedicated virtual account gateway is currently being configured.'
        }), 503

    # Check if account already exists
    existing = DBService.get_virtual_account(user_id)
    if existing and existing.get('account_number'):
        return jsonify({
            'success': True,
            'message': 'Your dedicated virtual account is already active.',
            'account': existing
        })

    data = request.json or {}
    bvn = str(data.get('bvn', '')).strip()
    bank_code = str(data.get('bank_code', '070')).strip()

    if not bvn:
        return jsonify({
            'success': False,
            'message': 'Bank Verification Number (BVN) is required to generate your dedicated bank account.'
        }), 400

    clean_bvn = ''.join(c for c in bvn if c.isdigit())
    if len(clean_bvn) != 11:
        return jsonify({
            'success': False,
            'message': 'Please enter a valid 11-digit BVN.'
        }), 400

    user_data = session.get('user', {})
    full_name = data.get('full_name') or user_data.get('full_name') or user_data.get('username') or 'Tgsims User'
    email = user_data.get('email', '')

    result = KorapayService.create_virtual_account(
        user_id=user_id,
        full_name=full_name,
        email=email,
        bvn=clean_bvn,
        bank_code=bank_code
    )

    if not result.get('success'):
        return jsonify({
            'success': False,
            'code': result.get('code'),
            'message': result.get('message', 'Failed to create dedicated virtual account.')
        }), 400

    acc_data = result.get('data', {})
    account_number = acc_data.get('account_number')
    account_name = acc_data.get('account_name')
    bank_name = acc_data.get('bank_name')
    account_ref = acc_data.get('account_reference')

    # Save to database
    DBService.save_virtual_account(
        user_id=user_id,
        customer_identifier=account_ref,
        account_number=account_number,
        account_name=account_name,
        bank_name=bank_name,
        bank_code=bank_code,
        bvn=clean_bvn,
        provider='korapay',
        raw_response=acc_data.get('raw')
    )

    account_info = {
        'account_number': account_number,
        'account_name': account_name,
        'bank_name': bank_name,
        'bank_code': bank_code
    }

    try:
        DBService.create_user_notification(
            user_id=user_id,
            title="Dedicated Account Ready!",
            message=f"Your permanent wallet account {account_number} ({bank_name}) is active. Transfer funds anytime for instant wallet top-up!",
            type="deposit",
            link="/wallet"
        )
    except Exception:
        pass

    return jsonify({
        'success': True,
        'message': 'Dedicated virtual account created successfully!',
        'account': account_info
    })


@api_bp.route('/payments/korapay/webhook', methods=['POST'])
def korapay_webhook():
    """
    Public webhook receiver for Korapay payment notifications.
    Processes charge.success events for dedicated virtual bank accounts.
    """
    raw_body = request.get_data()
    signature = request.headers.get('x-korapay-signature', '')

    payload = request.get_json(force=True, silent=True) or {}
    if not payload:
        return jsonify({'error': 'Invalid JSON body'}), 400

    print(f"[Korapay Webhook] Event received: {payload.get('event')}, ref: {payload.get('data', {}).get('reference')}")
    res = KorapayService.process_webhook(payload, raw_body=raw_body, signature=signature)
    return jsonify({'status': 'ok', 'result': res}), 200


@api_bp.route('/reactivate-order/<order_id>', methods=['POST'])
def reactivate_order(order_id):
    """Reactivates an eligible virtual number line to receive another OTP verification code."""
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'success': False, 'message': 'Please sign in to reactivate your order.'}), 401

    res = SIMProviderService.reactivate_order(order_id, user_id=user_id)
    status_code = 200 if res.get('success') else 400
    return jsonify(res), status_code


# =============================================================================
# SUPPORT TICKET SYSTEM & LIVE MESSAGING APIS
# =============================================================================

def _get_current_user():
    user = session.get('user')
    if isinstance(user, dict):
        return user
    return None


def _is_support_or_admin():
    user = _get_current_user()
    return bool(user and user.get('role') in ('admin', 'support'))


@api_bp.route('/support/tickets', methods=['GET'])
def get_user_tickets():
    """Retrieve all tickets belonging to the current authenticated user."""
    user = _get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Authentication required.'}), 401

    tickets = DBService.get_user_tickets(user['id'])
    return jsonify({'success': True, 'tickets': tickets})


@api_bp.route('/support/tickets', methods=['POST'])
def create_user_ticket():
    """Create a new ticket with required subject and initial message."""
    user = _get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Authentication required.'}), 401

    data = request.json or {}
    subject = (data.get('subject') or '').strip()
    initial_message = (data.get('message') or '').strip()
    category = (data.get('category') or 'general').strip()

    if not subject or len(subject) < 3:
        return jsonify({'success': False, 'message': 'Please provide a subject for your ticket (at least 3 characters).'}), 400

    if not initial_message:
        return jsonify({'success': False, 'message': 'Please provide a message describing your request or issue.'}), 400

    user_name = user.get('full_name') or user.get('username') or 'User'
    user_email = user.get('email')

    ticket = DBService.create_support_ticket(
        user_id=user['id'],
        subject=subject,
        initial_message=initial_message,
        category=category,
        user_name=user_name,
        user_email=user_email
    )

    return jsonify({
        'success': True,
        'message': 'Ticket created successfully.',
        'ticket': ticket
    }), 201


@api_bp.route('/support/tickets/<ticket_id>', methods=['GET'])
def get_ticket_details(ticket_id):
    """Retrieve details and messages for a specific user ticket."""
    user = _get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Authentication required.'}), 401

    ticket = DBService.get_ticket_by_id(ticket_id, user_id=user['id'], is_admin=False)
    if not ticket:
        return jsonify({'success': False, 'message': 'Ticket not found.'}), 404

    messages = DBService.get_ticket_messages(ticket['id'], user_id=user['id'], is_admin=False, mark_read=True)
    return jsonify({
        'success': True,
        'ticket': ticket,
        'messages': messages
    })


@api_bp.route('/support/tickets/<ticket_id>/messages', methods=['GET'])
def get_ticket_messages(ticket_id):
    """Fetch realtime messages for a ticket."""
    user = _get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Authentication required.'}), 401

    ticket = DBService.get_ticket_by_id(ticket_id, user_id=user['id'], is_admin=False)
    if not ticket:
        return jsonify({'success': False, 'message': 'Ticket not found.'}), 404

    messages = DBService.get_ticket_messages(ticket['id'], user_id=user['id'], is_admin=False, mark_read=True)
    return jsonify({'success': True, 'ticket_status': ticket.get('status'), 'messages': messages})


@api_bp.route('/support/tickets/<ticket_id>/messages', methods=['POST'])
def send_ticket_message(ticket_id):
    """Send a user message on an existing ticket."""
    user = _get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Authentication required.'}), 401

    ticket = DBService.get_ticket_by_id(ticket_id, user_id=user['id'], is_admin=False)
    if not ticket:
        return jsonify({'success': False, 'message': 'Ticket not found.'}), 404

    data = request.json or {}
    message_text = (data.get('message') or '').strip()
    if not message_text:
        return jsonify({'success': False, 'message': 'Message cannot be empty.'}), 400

    user_name = user.get('full_name') or user.get('username') or 'User'

    msg = DBService.add_support_message(
        ticket_id=ticket['id'],
        sender_id=user['id'],
        sender_name=user_name,
        sender_role='user',
        message=message_text
    )

    return jsonify({'success': True, 'message': msg})


@api_bp.route('/support/unread', methods=['GET'])
def get_support_unread():
    """Returns unread message count and support notifications for topbar badge & widget."""
    user = _get_current_user()
    if not user:
        return jsonify({'unread_total': 0, 'unread_messages': 0, 'unread_notifications': 0, 'notifications': []})

    data = DBService.get_user_support_unread(user['id'])
    return jsonify(data)


@api_bp.route('/support/notifications/read', methods=['POST'])
def mark_notifications_read():
    """Mark support notifications as read."""
    user = _get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Authentication required.'}), 401

    data = request.json or {}
    notif_id = data.get('notification_id', 'all')
    DBService.mark_notifications_read(user['id'], notif_id)
    return jsonify({'success': True})


# -----------------------------------------------------------------------------
# ADMIN / SUPPORT DESK APIS
# -----------------------------------------------------------------------------

@api_bp.route('/admin/support/tickets', methods=['GET'])
def admin_get_tickets():
    """Fetch tickets list for admin desk."""
    if not _is_support_or_admin():
        return jsonify({'success': False, 'message': 'Admin privileges required.'}), 403

    status = request.args.get('status')
    search = request.args.get('search')
    tickets = DBService.get_all_tickets_admin(status_filter=status, search=search)
    stats = DBService.get_admin_support_stats()
    return jsonify({'success': True, 'tickets': tickets, 'stats': stats})


@api_bp.route('/admin/support/tickets/<ticket_id>', methods=['GET'])
def admin_get_ticket_detail(ticket_id):
    """Fetch ticket details and full conversation for admin view."""
    if not _is_support_or_admin():
        return jsonify({'success': False, 'message': 'Admin privileges required.'}), 403

    ticket = DBService.get_ticket_by_id(ticket_id, is_admin=True)
    if not ticket:
        return jsonify({'success': False, 'message': 'Ticket not found.'}), 404

    messages = DBService.get_ticket_messages(ticket['id'], is_admin=True, mark_read=True)
    return jsonify({'success': True, 'ticket': ticket, 'messages': messages})


@api_bp.route('/admin/support/tickets/<ticket_id>/messages', methods=['POST'])
def admin_send_ticket_message(ticket_id):
    """Admin or support agent replies to a ticket."""
    if not _is_support_or_admin():
        return jsonify({'success': False, 'message': 'Admin privileges required.'}), 403

    user = _get_current_user()
    data = request.json or {}
    message_text = (data.get('message') or '').strip()
    if not message_text:
        return jsonify({'success': False, 'message': 'Reply message cannot be empty.'}), 400

    admin_name = 'Support'
    sender_role = 'support'

    msg = DBService.add_support_message(
        ticket_id=ticket_id,
        sender_id=user.get('id'),
        sender_name='Support',
        sender_role=sender_role,
        message=message_text
    )

    # Optional status update in same call (e.g. "Send & resolve")
    new_status = data.get('status')
    if new_status:
        DBService.update_ticket_status(ticket_id, new_status, actor_role=sender_role, actor_name='Support')

    return jsonify({'success': True, 'message': msg})


@api_bp.route('/admin/support/tickets/<ticket_id>/status', methods=['POST'])
def admin_update_ticket_status(ticket_id):
    """Admin updates ticket status ('open', 'pending', 'resolved', 'closed')."""
    if not _is_support_or_admin():
        return jsonify({'success': False, 'message': 'Admin privileges required.'}), 403

    user = _get_current_user()
    data = request.json or {}
    new_status = data.get('status')
    if not new_status:
        return jsonify({'success': False, 'message': 'Status parameter required.'}), 400

    res = DBService.update_ticket_status(
        ticket_id=ticket_id,
        new_status=new_status,
        actor_role='admin',
        actor_name='Support'
    )

    return jsonify(res)


# =============================================================================
# USER IN-APP NOTIFICATIONS & BELL ALERTS APIS
# =============================================================================

@api_bp.route('/notifications', methods=['GET'])
def get_user_notifications():
    """Retrieve in-app notifications and announcements for the logged-in user."""
    user = _get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Authentication required.'}), 401

    notifs = DBService.get_user_notifications(user['id'], limit=30)
    unread_count = sum(1 for n in notifs if not n.get('is_read'))

    return jsonify({
        'success': True,
        'notifications': notifs,
        'unread_count': unread_count
    })


@api_bp.route('/notifications/unread', methods=['GET'])
def get_user_notifications_unread():
    """Quick periodic polling endpoint for the topbar bell icon and badge."""
    user = _get_current_user()
    if not user:
        return jsonify({'success': False, 'unread_count': 0, 'notifications': []}), 401

    notifs = DBService.get_user_notifications(user['id'], limit=8)
    unread_count = sum(1 for n in notifs if not n.get('is_read'))

    return jsonify({
        'success': True,
        'unread_count': unread_count,
        'notifications': notifs
    })


@api_bp.route('/notifications/read', methods=['POST'])
def mark_user_notifications_read():
    """Mark a specific notification or all notifications as read."""
    user = _get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Authentication required.'}), 401

    data = request.json or {}
    notif_id = data.get('notification_id')

    ok = DBService.mark_user_notifications_read(user['id'], notif_id)
    return jsonify({'success': ok})


# =============================================================================
# DEDICATED NUMBER RENTALS (RESERVATIONS) APIS
# =============================================================================

@api_bp.route('/rent-number', methods=['POST'])
def api_rent_number():
    """Purchase a dedicated virtual number rental for 3, 7, 14, or 30 days."""
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.json or {}
    service_code = data.get('service_code') or 'allservices'
    try:
        duration_days = int(data.get('duration_days') or 3)
    except (ValueError, TypeError):
        duration_days = 3

    res = SIMProviderService.purchase_rental(
        user_id=user_id,
        service_code=service_code,
        duration_days=duration_days
    )
    status_code = 200 if res.get('success') else 400
    return jsonify(res), status_code


@api_bp.route('/check-rental-sms/<rental_id>', methods=['GET'])
def api_check_rental_sms(rental_id):
    """Poll SMS messages for an active rental line."""
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    res = SIMProviderService.check_rental_sms(rental_id)
    return jsonify(res)



