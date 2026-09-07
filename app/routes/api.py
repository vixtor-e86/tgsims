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
