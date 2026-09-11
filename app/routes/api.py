from flask import Blueprint, jsonify, request, session
from app.services.sim_provider import SIMProviderService
from app.services.db_service import DBService
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
    sim_result = SIMProviderService.purchase_number(country_code, service_name)
    if not sim_result or not sim_result.get('success'):
        return jsonify({
            'success': False,
            'message': 'No numbers currently available for this service. Please select another country or try again shortly.'
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
        'service_code': service_name.lower().replace(' ', '_'),
        'country_name': country_name,
        'country_code': country_code,
        'country_slug': country_name.lower().replace(' ', '_'),
        'phone_number': sim_result.get('phone_number', ''),
        'user_cost': price,
        'price': price,
        'provider_cost': 0.00,
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

    return jsonify({
        'success': True,
        'message': 'Virtual number activated successfully!',
        'new_balance': deduct_res.get('new_balance', cur_balance - price),
        'order': public_order
    })


@api_bp.route('/purchase-us-canada', methods=['POST'])
def purchase_us_canada():
    """Allocate and order a dedicated high-reliability US or Canada virtual number."""
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'success': False, 'message': 'Please sign in to complete your purchase.'}), 401

    data = request.json or {}
    country_code = data.get('country_code', 'US').upper()
    service_name = data.get('service_name', 'WhatsApp')
    package_id = data.get('package_id', 'whatsapp_guaranteed')
    provider_id = data.get('provider_id', 'auto')

    # Look up package
    pkg = next((p for p in SIMProviderService.US_CANADA_PACKAGES if p['id'] == package_id), SIMProviderService.US_CANADA_PACKAGES[0])
    price = float(pkg['price_usd'])
    country_name = 'United States' if country_code == 'US' else 'Canada'

    # 1. Check wallet balance
    wallet = DBService.get_wallet(user_id)
    cur_balance = float(wallet.get('balance', 0.00))
    if cur_balance < price:
        return jsonify({
            'success': False,
            'message': f'Insufficient wallet balance. You need ${price:.2f} but have ${cur_balance:.2f}. Please top up your wallet.'
        }), 400

    # 2. Allocate US/Canada number
    alloc_res = SIMProviderService.purchase_us_canada_number(
        country_code=country_code,
        service_name=service_name,
        package_id=package_id,
        provider_id=provider_id
    )

    if not alloc_res or not alloc_res.get('success'):
        return jsonify({
            'success': False,
            'message': 'Unable to allocate a carrier line at this moment. Please try another package or line.'
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
            'provider_line': alloc_res.get('provider_line', 'Titan Line')
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
        'service_code': service_name.lower().replace(' ', '_'),
        'country_name': country_name,
        'country_code': country_code,
        'country_slug': 'usa' if country_code == 'US' else 'canada',
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
            'full_sms': order.get('full_sms_text', f"Your code is {order['sms_code']}")
        })

    status = str(order.get('status', '')).lower()
    
    # 5-minute auto-refund check
    if status == 'pending' and order.get('created_at'):
        import datetime
        try:
            # Handle standard ISO formats, drop the 'Z' if present
            cat_str = str(order.get('created_at')).replace('Z', '+00:00')
            try:
                created_at = datetime.datetime.fromisoformat(cat_str)
            except ValueError:
                # Fallback for simple format
                created_at = datetime.datetime.strptime(cat_str, '%Y-%m-%d %H:%M:%S')
                
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=datetime.timezone.utc)
                
            now = datetime.datetime.now(datetime.timezone.utc)
            if (now - created_at).total_seconds() > 300: # 5 minutes
                # Auto refund
                prov_id = order.get('provider_order_id')
                if prov_id and not str(prov_id).startswith('SIM-') and not str(prov_id).startswith('USCA-'):
                    SIMProviderService.cancel_order(str(prov_id))
                
                price = float(order.get('user_cost') or order.get('price') or 0.0)
                DBService.credit_wallet_balance(
                    user_id=user_id,
                    amount=price,
                    reference=f"REFUND-{order_id}",
                    description=f"Auto Refund: Timeout ({order.get('service_name', 'SIM')})"
                )
                DBService.update_order_status(order_id, 'cancelled', reason="Auto-cancelled: SMS timeout (5 mins)")
                
                return jsonify({
                    'success': False,
                    'message': 'Order timed out (5 mins) and was automatically refunded to your wallet.',
                    'auto_refunded': True
                })
        except Exception as e:
            print(f"Error auto-refunding: {e}")

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
        return jsonify({
            'success': True,
            'sms_code': code,
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

    # 2. Cancel order on 5sim
    prov_id = order.get('provider_order_id')
    if prov_id and not str(prov_id).startswith('SIM-'):
        cancel_res = SIMProviderService.cancel_order(str(prov_id))
        if not cancel_res.get('success'):
            raw_err = str(cancel_res.get('message', '')).lower()
            if 'already' in raw_err or 'received' in raw_err or 'finished' in raw_err:
                return jsonify({'success': False, 'message': 'Cannot cancel order: verification code has already arrived.'}), 400
            elif 'not found' in raw_err:
                # Order may have timed out or expired in 5sim already
                pass
            else:
                return jsonify({'success': False, 'message': 'Unable to cancel order at this moment. Please try again or contact support.'}), 400

    # 3. Atomically refund wallet in database
    refund_result = DBService.refund_order(order_id, user_id, reason="Cancelled by user before receiving code")
    if not refund_result.get('success'):
        return jsonify(refund_result), 400

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
