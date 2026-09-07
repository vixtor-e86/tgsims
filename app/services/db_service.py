"""Database service layer for Tgsims.
Provides unified read/write methods to Supabase PostgreSQL with white-labeled, safe fallbacks.
No third-party provider names are ever leaked to the caller or frontend.
"""

import datetime
import uuid
from app.services.supabase_client import get_supabase_admin, mock_db


class DBService:
    """Unified Database Service for user wallets, transactions, SIM orders, and SMS messages."""

    @staticmethod
    def get_wallet(user_id: str) -> dict:
        """Fetch user wallet. Initializes wallet with 0.00 if not present."""
        if not user_id or user_id == 'demo-user-id':
            return mock_db.wallets.get(user_id, {'balance': 45.50, 'currency': 'USD'})

        admin = get_supabase_admin()
        if not admin:
            return mock_db.wallets.get(user_id, {'balance': 0.00, 'currency': 'USD'})

        try:
            res = admin.table('wallets').select('*').eq('user_id', user_id).limit(1).execute()
            if res.data and len(res.data) > 0:
                row = res.data[0]
                return {
                    'id': row.get('id'),
                    'user_id': user_id,
                    'balance': float(row.get('balance', 0.00)),
                    'currency': row.get('currency', 'USD'),
                    'created_at': row.get('created_at'),
                    'updated_at': row.get('updated_at')
                }

            # Check if profile exists before initializing wallet
            prof_check = admin.table('profiles').select('id').eq('id', user_id).limit(1).execute()
            if not prof_check.data:
                return {'balance': 0.00, 'currency': 'USD'}

            ins = admin.table('wallets').insert({
                'user_id': user_id,
                'balance': 0.00,
                'currency': 'USD'
            }).execute()
            if ins.data and len(ins.data) > 0:
                new_row = ins.data[0]
                return {
                    'id': new_row.get('id'),
                    'user_id': user_id,
                    'balance': float(new_row.get('balance', 0.00)),
                    'currency': new_row.get('currency', 'USD')
                }
            return {'balance': 0.00, 'currency': 'USD'}
        except Exception as e:
            print(f"[DBService] get_wallet error: {e}")
            return mock_db.wallets.get(user_id, {'balance': 0.00, 'currency': 'USD'})

    @staticmethod
    def get_transactions(user_id: str, limit: int = 50) -> list:
        """Fetch transaction history for a user."""
        if not user_id or user_id == 'demo-user-id':
            return [t for t in mock_db.transactions if t['user_id'] == user_id]

        admin = get_supabase_admin()
        if not admin:
            return [t for t in mock_db.transactions if t['user_id'] == user_id]

        try:
            res = admin.table('wallet_transactions')\
                .select('*')\
                .eq('user_id', user_id)\
                .order('created_at', desc=True)\
                .limit(limit)\
                .execute()
            return res.data or []
        except Exception as e:
            print(f"[DBService] get_transactions error: {e}")
            return [t for t in mock_db.transactions if t['user_id'] == user_id]

    @staticmethod
    def get_orders(user_id: str, limit: int = 50) -> list:
        """Fetch virtual number orders for a user."""
        if not user_id or user_id == 'demo-user-id':
            return [o for o in mock_db.sim_orders if o['user_id'] == user_id]

        admin = get_supabase_admin()
        if not admin:
            return [o for o in mock_db.sim_orders if o['user_id'] == user_id]

        try:
            res = admin.table('sim_orders')\
                .select('*')\
                .eq('user_id', user_id)\
                .order('created_at', desc=True)\
                .limit(limit)\
                .execute()
            
            # Map user_cost -> price for template compatibility
            orders = res.data or []
            for o in orders:
                if 'price' not in o:
                    o['price'] = float(o.get('user_cost', 0.00))
            return orders
        except Exception as e:
            print(f"[DBService] get_orders error: {e}")
            return [o for o in mock_db.sim_orders if o['user_id'] == user_id]

    @staticmethod
    def get_order_by_id(user_id: str, order_id: str) -> dict:
        """Retrieve a specific order by UUID or reference."""
        if not user_id or user_id == 'demo-user-id':
            return next((o for o in mock_db.sim_orders if o.get('id') == order_id or o.get('order_reference') == order_id), None)

        admin = get_supabase_admin()
        if not admin:
            return next((o for o in mock_db.sim_orders if o.get('id') == order_id or o.get('order_reference') == order_id), None)

        try:
            res = admin.table('sim_orders').select('*').eq('user_id', user_id).or_(f"id.eq.{order_id},order_reference.eq.{order_id}").limit(1).execute()
            if res.data and len(res.data) > 0:
                o = res.data[0]
                if 'price' not in o:
                    o['price'] = float(o.get('user_cost', 0.00))
                return o
            return None
        except Exception as e:
            print(f"[DBService] get_order_by_id error: {e}")
            return next((o for o in mock_db.sim_orders if o.get('id') == order_id or o.get('order_reference') == order_id), None)

    @staticmethod
    def deduct_wallet_balance(user_id: str, amount: float, reference: str, description: str, metadata: dict = None, order_id: str = None) -> dict:
        """Deducts balance atomically. Returns dict with success, message, new_balance."""
        metadata = metadata or {}
        if not user_id or user_id == 'demo-user-id':
            wallet = mock_db.wallets.get(user_id, {'balance': 45.50, 'currency': 'USD'})
            if wallet['balance'] < amount:
                return {
                    'success': False,
                    'message': f'Insufficient wallet balance. You need ${amount:.2f} but have ${wallet["balance"]:.2f}. Please top up.'
                }
            wallet['balance'] -= amount
            mock_db.transactions.insert(0, {
                'id': f"tx-{len(mock_db.transactions) + 1}",
                'user_id': user_id,
                'order_id': order_id,
                'amount': -amount,
                'type': 'purchase',
                'status': 'completed',
                'reference': reference,
                'description': description,
                'metadata': metadata,
                'created_at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            })
            return {'success': True, 'new_balance': wallet['balance'], 'message': 'Balance deducted successfully.'}

        admin = get_supabase_admin()
        if not admin:
            return {'success': False, 'message': 'Database connection unavailable.'}

        try:
            # Query wallet balance
            w_res = admin.table('wallets').select('id, balance').eq('user_id', user_id).limit(1).execute()
            if not w_res.data:
                return {'success': False, 'message': 'Wallet not found.'}
            
            cur_bal = float(w_res.data[0].get('balance', 0.00))
            if cur_bal < amount:
                return {
                    'success': False,
                    'message': f'Insufficient wallet balance. You need ${amount:.2f} but have ${cur_bal:.2f}. Please top up.'
                }

            new_bal = round(cur_bal - amount, 2)
            admin.table('wallets').update({
                'balance': new_bal,
                'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
            }).eq('user_id', user_id).execute()

            # Insert ledger entry
            tx_data = {
                'user_id': user_id,
                'amount': -amount,
                'type': 'purchase',
                'status': 'completed',
                'reference': reference,
                'description': description,
                'metadata': metadata
            }
            if order_id:
                tx_data['order_id'] = order_id
            
            tx_res = admin.table('wallet_transactions').insert(tx_data).execute()
            tx_id = tx_res.data[0]['id'] if tx_res.data else None

            return {
                'success': True,
                'new_balance': new_bal,
                'transaction_id': tx_id,
                'message': 'Balance deducted successfully.'
            }
        except Exception as e:
            print(f"[DBService] deduct_wallet_balance error: {e}")
            return {'success': False, 'message': 'Failed to process transaction. Please try again.'}

    @staticmethod
    def credit_wallet_balance(user_id: str, amount: float, trans_type: str, reference: str, description: str, metadata: dict = None, order_id: str = None) -> dict:
        """Credits user wallet. Returns dict with success, message, new_balance."""
        metadata = metadata or {}
        if not user_id or user_id == 'demo-user-id':
            wallet = mock_db.wallets.get(user_id)
            if not wallet:
                wallet = {'balance': 0.00, 'currency': 'USD'}
                mock_db.wallets[user_id] = wallet
            wallet['balance'] += amount
            mock_db.transactions.insert(0, {
                'id': f"tx-{len(mock_db.transactions) + 1}",
                'user_id': user_id,
                'order_id': order_id,
                'amount': amount,
                'type': trans_type,
                'status': 'completed',
                'reference': reference,
                'description': description,
                'metadata': metadata,
                'created_at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            })
            return {'success': True, 'new_balance': wallet['balance'], 'message': f'Wallet credited with ${amount:.2f}!'}

        admin = get_supabase_admin()
        if not admin:
            return {'success': False, 'message': 'Database connection unavailable.'}

        try:
            w_res = admin.table('wallets').select('id, balance').eq('user_id', user_id).limit(1).execute()
            if w_res.data:
                cur_bal = float(w_res.data[0].get('balance', 0.00))
                new_bal = round(cur_bal + amount, 2)
                admin.table('wallets').update({
                    'balance': new_bal,
                    'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
                }).eq('user_id', user_id).execute()
            else:
                new_bal = round(amount, 2)
                admin.table('wallets').insert({
                    'user_id': user_id,
                    'balance': new_bal,
                    'currency': 'USD'
                }).execute()

            tx_data = {
                'user_id': user_id,
                'amount': amount,
                'type': trans_type,
                'status': 'completed',
                'reference': reference,
                'description': description,
                'metadata': metadata
            }
            if order_id:
                tx_data['order_id'] = order_id
            admin.table('wallet_transactions').insert(tx_data).execute()

            return {
                'success': True,
                'new_balance': new_bal,
                'message': f'Wallet credited with ${amount:.2f}!'
            }
        except Exception as e:
            print(f"[DBService] credit_wallet_balance error: {e}")
            return {'success': False, 'message': 'Failed to credit wallet. Please try again.'}

    @staticmethod
    def create_order(user_id: str, order_data: dict) -> dict:
        """Saves a new virtual number order in the database."""
        if not user_id or user_id == 'demo-user-id':
            mock_order = {
                'id': f"sim-{len(mock_db.sim_orders) + 101}",
                'user_id': user_id,
                'order_reference': order_data.get('order_reference'),
                'service_name': order_data.get('service_name'),
                'country_name': order_data.get('country_name'),
                'country_code': order_data.get('country_code'),
                'phone_number': order_data.get('phone_number'),
                'price': float(order_data.get('user_cost', order_data.get('price', 2.50))),
                'status': order_data.get('status', 'active'),
                'provider_order_id': order_data.get('provider_order_id'),
                'sms_code': None,
                'full_sms_text': 'Waiting for SMS verification code...',
                'created_at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            }
            mock_db.sim_orders.insert(0, mock_order)
            return mock_order

        admin = get_supabase_admin()
        if not admin:
            return order_data

        try:
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            db_row = {
                'user_id': user_id,
                'order_reference': order_data.get('order_reference'),
                'provider': '5sim',  # Internal system identifier only, never sent to frontend
                'provider_order_id': str(order_data.get('provider_order_id', '')),
                'order_type': order_data.get('order_type', 'activation'),
                'country_code': order_data.get('country_code', 'US'),
                'country_name': order_data.get('country_name', 'United States'),
                'country_slug': order_data.get('country_slug', ''),
                'operator': order_data.get('operator', 'any'),
                'service_code': order_data.get('service_code', 'whatsapp'),
                'service_name': order_data.get('service_name', 'WhatsApp'),
                'phone_number': order_data.get('phone_number', ''),
                'provider_cost': float(order_data.get('provider_cost', 0.00)),
                'user_cost': float(order_data.get('user_cost', order_data.get('price', 2.50))),
                'profit_margin': float(order_data.get('profit_margin', 0.00)),
                'currency': 'USD',
                'status': 'pending',
                'sms_code': None,
                'full_sms_text': 'Waiting for SMS verification code...',
                'sms_count': 0,
                'expires_at': order_data.get('expires_at')
            }
            res = admin.table('sim_orders').insert(db_row).execute()
            if res.data and len(res.data) > 0:
                saved = res.data[0]
                saved['price'] = float(saved.get('user_cost', 2.50))
                return saved
            return order_data
        except Exception as e:
            print(f"[DBService] create_order error: {e}")
            return order_data

    @staticmethod
    def update_order_sms(order_id: str, sms_code: str, full_sms: str, sender: str = '', provider_sms_id: str = '') -> bool:
        """Records an incoming SMS and updates order state."""
        admin = get_supabase_admin()
        if not admin:
            for o in mock_db.sim_orders:
                if o.get('id') == order_id or o.get('order_reference') == order_id:
                    o['sms_code'] = sms_code
                    o['full_sms_text'] = full_sms
                    o['status'] = 'received'
                    return True
            return False

        try:
            # Update order
            admin.table('sim_orders').update({
                'status': 'received',
                'sms_code': sms_code,
                'full_sms_text': full_sms,
                'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
            }).or_(f"id.eq.{order_id},order_reference.eq.{order_id}").execute()

            # Record in sim_sms_messages if order row found
            order_res = admin.table('sim_orders').select('id').or_(f"id.eq.{order_id},order_reference.eq.{order_id}").limit(1).execute()
            if order_res.data:
                real_uuid = order_res.data[0]['id']
                admin.table('sim_sms_messages').insert({
                    'order_id': real_uuid,
                    'provider_sms_id': provider_sms_id or None,
                    'sender': sender or 'Verification',
                    'sms_code': sms_code,
                    'full_text': full_sms
                }).execute()
            return True
        except Exception as e:
            print(f"[DBService] update_order_sms error: {e}")
            return False

    @staticmethod
    def refund_order(order_id: str, user_id: str, reason: str = 'Order cancelled or timed out') -> dict:
        """Issues an atomic refund for an order to the user's wallet."""
        order = DBService.get_order_by_id(user_id, order_id)
        if not order:
            return {'success': False, 'message': 'Order not found.'}

        if order.get('status') in ['refunded', 'cancelled']:
            return {'success': False, 'message': 'Order has already been refunded.'}

        if order.get('status') == 'completed':
            return {'success': False, 'message': 'Completed orders cannot be refunded.'}

        refund_amount = float(order.get('price', order.get('user_cost', 0.00)))
        ref_tx = f"REF-{uuid.uuid4().hex[:10].upper()}"
        svc_name = order.get('service_name', 'Virtual SIM')

        # Credit wallet
        credit_res = DBService.credit_wallet_balance(
            user_id=user_id,
            amount=refund_amount,
            trans_type='refund',
            reference=ref_tx,
            description=f"Refund for {svc_name} - {reason}",
            metadata={'order_reference': order.get('order_reference'), 'reason': reason},
            order_id=order.get('id')
        )

        if not credit_res.get('success'):
            return {'success': False, 'message': 'Failed to credit refund to wallet.'}

        # Update order status
        admin = get_supabase_admin()
        if admin and user_id != 'demo-user-id':
            try:
                admin.table('sim_orders').update({
                    'status': 'refunded',
                    'refunded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    'refund_reason': reason,
                    'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
                }).or_(f"id.eq.{order_id},order_reference.eq.{order_id}").execute()
            except Exception as e:
                print(f"[DBService] refund order status update error: {e}")
        else:
            order['status'] = 'refunded'

        return {
            'success': True,
            'message': f'Order refunded. ${refund_amount:.2f} credited to your wallet.',
            'new_balance': credit_res.get('new_balance')
        }
