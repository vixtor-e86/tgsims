from flask import Blueprint, jsonify, request, session
from app.services.sim_provider import SIMProviderService
from app.services.payment_service import PaymentService
from app.services.supabase_client import mock_db
import datetime

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/purchase-sim', methods=['POST'])
def purchase_sim():
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.json or {}
    country_code = data.get('country_code', 'US')
    country_name = data.get('country_name', 'United States')
    service_name = data.get('service_name', 'WhatsApp')
    price = float(data.get('price', 2.50))
    user_id = session['user']['id']

    # 1. Check wallet balance
    wallet = mock_db.wallets.get(user_id, {'balance': 0.00, 'currency': 'USD'})
    if wallet['balance'] < price:
        return jsonify({
            'success': False,
            'message': f'Insufficient wallet balance. You need ${price:.2f} but have ${wallet["balance"]:.2f}. Please top up.'
        }), 400

    # 2. Call SIM Provider Service
    sim_result = SIMProviderService.purchase_number(country_code, service_name)
    
    if not sim_result['success']:
        return jsonify({'success': False, 'message': 'Failed to purchase SIM from provider.'}), 500

    # 3. Atomic deduction from wallet
    wallet['balance'] -= price
    
    # 4. Record SIM Order & Transaction
    new_order = {
        'id': f"sim-{len(mock_db.sim_orders) + 101}",
        'user_id': user_id,
        'order_reference': sim_result['order_reference'],
        'service_name': service_name,
        'country_name': country_name,
        'country_code': country_code,
        'phone_number': sim_result['phone_number'],
        'price': price,
        'status': 'active',
        'provider_order_id': sim_result['provider_order_id'],
        'sms_code': None,
        'full_sms_text': 'Waiting for SMS verification code...',
        'qr_code_url': sim_result.get('qr_code_url'),
        'created_at': datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    }
    mock_db.sim_orders.insert(0, new_order)

    mock_db.transactions.insert(0, {
        'id': f"tx-{len(mock_db.transactions) + 1}",
        'user_id': user_id,
        'amount': -price,
        'type': 'purchase',
        'status': 'completed',
        'reference': sim_result['order_reference'],
        'description': f"{service_name} Virtual SIM ({country_name})",
        'created_at': datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    })

    return jsonify({
        'success': True,
        'message': 'SIM purchased successfully!',
        'new_balance': wallet['balance'],
        'order': new_order
    })

@api_bp.route('/check-sms/<order_id>', methods=['GET'])
def check_sms(order_id):
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    order = next((s for s in mock_db.sim_orders if s['id'] == order_id), None)
    if not order:
        return jsonify({'success': False, 'message': 'Order not found'}), 404

    sms_info = SIMProviderService.check_sms(order_id)
    order['sms_code'] = sms_info['sms_code']
    order['full_sms_text'] = sms_info['full_sms']

    return jsonify({
        'success': True,
        'sms_code': sms_info['sms_code'],
        'full_sms': sms_info['full_sms']
    })

@api_bp.route('/deposit', methods=['POST'])
def deposit():
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.json or {}
    amount = float(data.get('amount', 10.00))
    user_id = session['user']['id']

    # Credit wallet balance
    wallet = mock_db.wallets.get(user_id)
    if not wallet:
        wallet = {'balance': 0.00, 'currency': 'USD'}
        mock_db.wallets[user_id] = wallet

    wallet['balance'] += amount

    tx_ref = f"DEP-{datetime.datetime.now().strftime('%H%M%S')}"
    mock_db.transactions.insert(0, {
        'id': f"tx-{len(mock_db.transactions) + 1}",
        'user_id': user_id,
        'amount': amount,
        'type': 'deposit',
        'status': 'completed',
        'reference': tx_ref,
        'description': 'Wallet Top-up',
        'created_at': datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    })

    return jsonify({
        'success': True,
        'message': f'Wallet funded with ${amount:.2f}!',
        'new_balance': wallet['balance']
    })
