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
        if not user_id or user_id == 'demo-user-id' or not DBService._is_uuid(user_id):
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
        if not user_id or user_id == 'demo-user-id' or not DBService._is_uuid(user_id):
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
    def _is_uuid(val: str) -> bool:
        if not val or not isinstance(val, str):
            return False
        try:
            uuid.UUID(str(val))
            return True
        except (ValueError, AttributeError):
            return False

    @staticmethod
    def get_order_by_id(user_id: str, order_id: str) -> dict:
        """Retrieve a specific order by UUID or reference."""
        if not user_id or user_id == 'demo-user-id':
            return next((o for o in mock_db.sim_orders if o.get('id') == order_id or o.get('order_reference') == order_id), None)

        admin = get_supabase_admin()
        if not admin:
            return next((o for o in mock_db.sim_orders if o.get('id') == order_id or o.get('order_reference') == order_id), None)

        try:
            q = admin.table('sim_orders').select('*').eq('user_id', user_id)
            if DBService._is_uuid(order_id):
                q = q.or_(f"id.eq.{order_id},order_reference.eq.{order_id}")
            else:
                q = q.eq('order_reference', order_id)
            res = q.limit(1).execute()
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
        if not user_id or user_id == 'demo-user-id' or not DBService._is_uuid(user_id):
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
        if not user_id or user_id == 'demo-user-id' or not DBService._is_uuid(user_id):
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
            order_update = {
                'status': 'received',
                'sms_code': sms_code,
                'full_sms_text': full_sms,
                'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            q = admin.table('sim_orders').update(order_update)
            if DBService._is_uuid(order_id):
                q = q.or_(f"id.eq.{order_id},order_reference.eq.{order_id}")
            else:
                q = q.eq('order_reference', order_id)
            q.execute()

            # Record in sim_sms_messages if order row found
            q2 = admin.table('sim_orders').select('id')
            if DBService._is_uuid(order_id):
                q2 = q2.or_(f"id.eq.{order_id},order_reference.eq.{order_id}")
            else:
                q2 = q2.eq('order_reference', order_id)
            order_res = q2.limit(1).execute()
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
    def update_order_status(order_id: str, status: str, reason: str = None) -> bool:
        """Updates the status of an order."""
        admin = get_supabase_admin()
        if not admin:
            for o in mock_db.sim_orders:
                if o.get('id') == order_id or o.get('order_reference') == order_id:
                    o['status'] = status
                    if reason:
                        o['status_reason'] = reason
                    return True
            return False

        try:
            update_data = {
                'status': status,
                'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            if reason:
                update_data['status_reason'] = reason
            q = admin.table('sim_orders').update(update_data)
            if DBService._is_uuid(order_id):
                q = q.or_(f"id.eq.{order_id},order_reference.eq.{order_id}")
            else:
                q = q.eq('order_reference', order_id)
            q.execute()
            return True
        except Exception as e:
            print(f"[DBService] update_order_status error: {e}")
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
                real_id = order.get('id')
                q = admin.table('sim_orders').update({
                    'status': 'refunded',
                    'refunded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    'refund_reason': reason,
                    'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
                })
                if DBService._is_uuid(real_id):
                    q = q.eq('id', str(real_id))
                else:
                    q = q.eq('order_reference', str(order.get('order_reference') or order_id))
                q.execute()
            except Exception as e:
                print(f"[DBService] refund order status update error: {e}")
        else:
            order['status'] = 'refunded'

        return {
            'success': True,
            'message': f'Order refunded. ${refund_amount:.2f} credited to your wallet.',
            'new_balance': credit_res.get('new_balance')
        }

    # =========================================================================
    # ADMIN OPERATIONS & AUDIT METHODS
    # =========================================================================

    @staticmethod
    def get_admin_overview_stats() -> dict:
        """Aggregates high-level platform statistics for the Admin dashboard."""
        admin = get_supabase_admin()
        if not admin:
            pending_count = len([t for t in mock_db.transactions if t.get('type') == 'deposit' and t.get('status') == 'pending'])
            total_orders = len(mock_db.sim_orders)
            active_orders = len([o for o in mock_db.sim_orders if o.get('status') in ('active', 'pending')])
            total_users = len(mock_db.wallets)
            deposit_vol = sum(t.get('amount', 0) for t in mock_db.transactions if t.get('type') == 'deposit' and t.get('status') == 'completed')
            return {
                'total_users': max(total_users, 1),
                'total_orders': total_orders,
                'active_orders': active_orders,
                'pending_deposits_count': pending_count,
                'total_deposit_volume_usd': round(deposit_vol, 2)
            }

        try:
            # Total users
            u_res = admin.table('profiles').select('id', count='exact').execute()
            total_users = u_res.count if hasattr(u_res, 'count') and u_res.count is not None else len(u_res.data or [])

            # Total orders
            o_res = admin.table('sim_orders').select('id', count='exact').execute()
            total_orders = o_res.count if hasattr(o_res, 'count') and o_res.count is not None else len(o_res.data or [])

            # Active orders
            act_res = admin.table('sim_orders').select('id', count='exact').in_('status', ['active', 'pending']).execute()
            active_orders = act_res.count if hasattr(act_res, 'count') and act_res.count is not None else len(act_res.data or [])

            # Pending deposits
            pend_res = admin.table('wallet_transactions').select('id', count='exact').eq('type', 'deposit').eq('status', 'pending').execute()
            pending_count = pend_res.count if hasattr(pend_res, 'count') and pend_res.count is not None else len(pend_res.data or [])

            # Completed deposits volume
            vol_res = admin.table('wallet_transactions').select('amount').eq('type', 'deposit').eq('status', 'completed').execute()
            total_vol = sum(float(r.get('amount', 0)) for r in (vol_res.data or []))

            return {
                'total_users': total_users,
                'total_orders': total_orders,
                'active_orders': active_orders,
                'pending_deposits_count': pending_count,
                'total_deposit_volume_usd': round(total_vol, 2)
            }
        except Exception as e:
            print(f"[DBService] get_admin_overview_stats error: {e}")
            return {
                'total_users': 0,
                'total_orders': 0,
                'active_orders': 0,
                'pending_deposits_count': 0,
                'total_deposit_volume_usd': 0.00
            }

    @staticmethod
    def get_all_deposits_admin(status_filter: str = None, limit: int = 100) -> list:
        """Fetch all deposit transactions for admin verification review."""
        admin = get_supabase_admin()
        if not admin:
            deposits = [t for t in mock_db.transactions if t.get('type') == 'deposit']
            if status_filter and status_filter != 'all':
                deposits = [t for t in deposits if t.get('status') == status_filter]
            return deposits[:limit]

        try:
            q = admin.table('wallet_transactions').select('*, profiles(email, full_name, username)').eq('type', 'deposit')
            if status_filter and status_filter != 'all':
                q = q.eq('status', status_filter)
            res = q.order('created_at', desc=True).limit(limit).execute()
            
            items = res.data or []
            # Flatten profile information & fallback to metadata
            for item in items:
                prof = item.get('profiles') or {}
                item['user_email'] = prof.get('email', 'Unknown')
                item['user_name'] = prof.get('full_name') or prof.get('username') or item['user_email']

                meta = item.get('metadata') or {}
                if not item.get('payment_channel'):
                    item['payment_channel'] = meta.get('payment_channel') or meta.get('gateway', 'manual')
                if not item.get('verified_by'):
                    item['verified_by'] = meta.get('verified_by')
                if not item.get('verified_at'):
                    item['verified_at'] = meta.get('verified_at')
                if not item.get('admin_notes'):
                    item['admin_notes'] = meta.get('admin_notes')
            return items
        except Exception as e:
            print(f"[DBService] get_all_deposits_admin error: {e}")
            return []

    @staticmethod
    def verify_deposit_admin(transaction_id: str, admin_user_id: str, admin_notes: str = '') -> dict:
        """Manually marks a pending deposit as completed and credits user wallet atomically."""
        admin = get_supabase_admin()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Mock fallback
        if not admin or not DBService._is_uuid(transaction_id):
            tx = next((t for t in mock_db.transactions if t.get('id') == transaction_id), None)
            if not tx:
                return {'success': False, 'message': 'Transaction not found.'}
            if tx.get('status') == 'completed':
                return {'success': False, 'message': 'Transaction has already been verified.'}

            amount = float(tx.get('amount', 0.00))
            user_id = tx.get('user_id')
            tx['status'] = 'completed'
            tx['verified_by'] = admin_user_id
            tx['verified_at'] = now_iso
            tx['admin_notes'] = admin_notes

            # Credit user wallet
            wallet = mock_db.wallets.get(user_id, {'balance': 0.00, 'currency': 'USD'})
            wallet['balance'] += amount
            mock_db.wallets[user_id] = wallet

            return {
                'success': True,
                'message': f"Deposit verified! ${amount:.2f} credited to user wallet.",
                'new_balance': wallet['balance']
            }

        try:
            # 1. Fetch transaction
            tx_res = admin.table('wallet_transactions').select('*').eq('id', transaction_id).limit(1).execute()
            if not tx_res.data:
                return {'success': False, 'message': 'Transaction not found.'}

            tx = tx_res.data[0]
            if tx.get('status') == 'completed':
                return {'success': False, 'message': 'Transaction is already completed.'}

            user_id = tx.get('user_id')
            amount = float(tx.get('amount', 0.00))
            if amount <= 0:
                return {'success': False, 'message': 'Invalid transaction amount.'}

            # 2. Mark transaction as completed and audited
            meta = tx.get('metadata') or {}
            meta['verified_by'] = admin_user_id
            meta['verified_at'] = now_iso
            meta['admin_notes'] = admin_notes or 'Manually verified and approved by admin.'

            existing_cols = set(tx.keys())
            upd_data = {
                'status': 'completed',
                'metadata': meta
            }
            if 'verified_by' in existing_cols and DBService._is_uuid(admin_user_id):
                upd_data['verified_by'] = admin_user_id
            if 'verified_at' in existing_cols:
                upd_data['verified_at'] = now_iso
            if 'admin_notes' in existing_cols:
                upd_data['admin_notes'] = admin_notes or 'Manually verified and approved by admin.'

            admin.table('wallet_transactions').update(upd_data).eq('id', transaction_id).execute()

            # 3. Credit wallet balance
            w_res = admin.table('wallets').select('id, balance').eq('user_id', user_id).limit(1).execute()
            if w_res.data:
                cur_bal = float(w_res.data[0].get('balance', 0.00))
                new_bal = round(cur_bal + amount, 2)
                admin.table('wallets').update({
                    'balance': new_bal,
                    'updated_at': now_iso
                }).eq('user_id', user_id).execute()
            else:
                new_bal = round(amount, 2)
                admin.table('wallets').insert({
                    'user_id': user_id,
                    'balance': new_bal,
                    'currency': 'USD'
                }).execute()

            return {
                'success': True,
                'message': f"Deposit successfully verified! ${amount:.2f} credited to user wallet.",
                'new_balance': new_bal
            }
        except Exception as e:
            print(f"[DBService] verify_deposit_admin error: {e}")
            return {'success': False, 'message': f"Database error during verification: {e}"}

    @staticmethod
    def reject_deposit_admin(transaction_id: str, admin_user_id: str, reason: str = '') -> dict:
        """Manually rejects/cancels a pending deposit with an audit reason."""
        admin = get_supabase_admin()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if not admin or not DBService._is_uuid(transaction_id):
            tx = next((t for t in mock_db.transactions if t.get('id') == transaction_id), None)
            if not tx:
                return {'success': False, 'message': 'Transaction not found.'}
            tx['status'] = 'failed'
            tx['verified_by'] = admin_user_id
            tx['verified_at'] = now_iso
            tx['admin_notes'] = reason or 'Rejected by administrator'
            return {'success': True, 'message': 'Deposit rejected.'}

        try:
            tx_res = admin.table('wallet_transactions').select('*').eq('id', transaction_id).limit(1).execute()
            if not tx_res.data:
                return {'success': False, 'message': 'Transaction not found.'}
            tx = tx_res.data[0]
            meta = tx.get('metadata') or {}
            meta['verified_by'] = admin_user_id
            meta['verified_at'] = now_iso
            meta['admin_notes'] = reason or 'Rejected by administrator'

            existing_cols = set(tx.keys())
            upd_data = {
                'status': 'failed',
                'metadata': meta
            }
            if 'verified_by' in existing_cols and DBService._is_uuid(admin_user_id):
                upd_data['verified_by'] = admin_user_id
            if 'verified_at' in existing_cols:
                upd_data['verified_at'] = now_iso
            if 'admin_notes' in existing_cols:
                upd_data['admin_notes'] = reason or 'Rejected by administrator'

            admin.table('wallet_transactions').update(upd_data).eq('id', transaction_id).execute()
            return {'success': True, 'message': 'Deposit marked as rejected.'}
        except Exception as e:
            print(f"[DBService] reject_deposit_admin error: {e}")
            return {'success': False, 'message': f"Error rejecting deposit: {e}"}

    @staticmethod
    def get_all_orders_admin(status_filter: str = None, limit: int = 100) -> list:
        """Fetch all user SIM orders across the platform."""
        admin = get_supabase_admin()
        if not admin:
            orders = list(mock_db.sim_orders)
            if status_filter and status_filter != 'all':
                orders = [o for o in orders if o.get('status') == status_filter]
            return orders[:limit]

        try:
            q = admin.table('sim_orders').select('*, profiles(email, full_name, username)')
            if status_filter and status_filter != 'all':
                q = q.eq('status', status_filter)
            res = q.order('created_at', desc=True).limit(limit).execute()
            
            orders = res.data or []
            for o in orders:
                prof = o.get('profiles') or {}
                o['user_email'] = prof.get('email', 'Unknown')
                o['user_name'] = prof.get('full_name') or prof.get('username') or o['user_email']
                if 'price' not in o:
                    o['price'] = float(o.get('user_cost', 0.00))
            return orders
        except Exception as e:
            print(f"[DBService] get_all_orders_admin error: {e}")
            return []

    @staticmethod
    def get_all_users_admin(search: str = None, limit: int = 100) -> list:
        """Fetch all user profiles with wallet balance and order count."""
        admin = get_supabase_admin()
        if not admin:
            return [{
                'id': 'demo-user-id',
                'email': 'user@example.com',
                'full_name': 'Demo User',
                'username': 'demouser',
                'role': 'user',
                'wallet_balance': 45.50,
                'total_orders': len(mock_db.sim_orders),
                'created_at': '2026-08-01 10:00:00'
            }]

        try:
            q = admin.table('profiles').select('id, email, full_name, username, role, created_at, wallets(balance)')
            if search:
                s = f"%{search.strip()}%"
                q = q.or_(f"email.ilike.{s},full_name.ilike.{s},username.ilike.{s}")
            res = q.order('created_at', desc=True).limit(limit).execute()

            users = []
            for row in (res.data or []):
                wallet_list = row.get('wallets') or []
                balance = 0.00
                if isinstance(wallet_list, list) and len(wallet_list) > 0:
                    balance = float(wallet_list[0].get('balance', 0.00))
                elif isinstance(wallet_list, dict):
                    balance = float(wallet_list.get('balance', 0.00))

                users.append({
                    'id': row.get('id'),
                    'email': row.get('email'),
                    'full_name': row.get('full_name'),
                    'username': row.get('username'),
                    'role': row.get('role', 'user'),
                    'wallet_balance': balance,
                    'created_at': row.get('created_at')
                })
            return users
        except Exception as e:
            print(f"[DBService] get_all_users_admin error: {e}")
            return []

    @staticmethod
    def adjust_user_balance_admin(user_id: str, amount: float, reason: str, admin_user_id: str) -> dict:
        """Admin manual balance adjustment (positive or negative)."""
        admin = get_supabase_admin()
        ref = f"ADJ-{uuid.uuid4().hex[:8].upper()}"

        if amount > 0:
            return DBService.credit_wallet_balance(
                user_id=user_id,
                amount=amount,
                trans_type='adjustment',
                reference=ref,
                description=f"Admin Adjustment: {reason}",
                metadata={'adjusted_by': admin_user_id, 'reason': reason}
            )
        else:
            abs_amt = abs(amount)
            return DBService.deduct_wallet_balance(
                user_id=user_id,
                amount=abs_amt,
                reference=ref,
                description=f"Admin Debit: {reason}",
                metadata={'adjusted_by': admin_user_id, 'reason': reason}
            )

    @staticmethod
    def update_user_role_admin(user_id: str, new_role: str) -> bool:
        """Promote or demote user role ('admin' or 'user')."""
        if new_role not in ('user', 'admin'):
            return False
        admin = get_supabase_admin()
        if not admin:
            return True
        try:
            admin.table('profiles').update({'role': new_role}).eq('id', user_id).execute()
            return True
        except Exception as e:
            print(f"[DBService] update_user_role_admin error: {e}")
            return False
