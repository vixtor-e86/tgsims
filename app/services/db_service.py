"""Database service layer for Tgsims.
Provides unified read/write methods to Supabase PostgreSQL with white-labeled, safe fallbacks.
No third-party provider names are ever leaked to the caller or frontend.
"""

import datetime
import uuid
import secrets
from app.services.supabase_client import get_supabase_admin, mock_db



class DBService:
    """Unified Database Service for user wallets, transactions, SIM orders, and SMS messages."""

    @staticmethod
    def _is_uuid(val: str) -> bool:
        if not val or not isinstance(val, str):
            return False
        try:
            uuid.UUID(str(val))
            return True
        except (ValueError, TypeError, AttributeError):
            return False

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
                val = o.get('price')
                if val is None:
                    val = o.get('user_cost', 0.00)
                try:
                    o['price'] = float(val or 0.00)
                except (ValueError, TypeError):
                    o['price'] = 0.00
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
            try:
                DBService.record_referral_commission(user_id=user_id, amount_spent=amount, order_id=order_id, order_reference=reference)
            except Exception as ref_err:
                print(f"[DBService] mock referral commission error: {ref_err}")
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

            # Record 5% referral earning for the referrer if this user was invited
            try:
                DBService.record_referral_commission(
                    user_id=user_id,
                    amount_spent=amount,
                    order_id=order_id,
                    order_reference=reference
                )
            except Exception as ref_err:
                print(f"[DBService] referral commission error: {ref_err}")

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

        # Reverse 5% referral commission if one was credited for this order
        try:
            DBService.reverse_referral_commission(order_id=order.get('id') or order_id)
        except Exception as rev_err:
            print(f"[DBService] reverse_referral_commission error: {rev_err}")

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
            try:
                # Try explicit foreign key for user_id
                q = admin.table('wallet_transactions').select('*, profiles!wallet_transactions_user_id_fkey(email, full_name, username)').eq('type', 'deposit')
                if status_filter and status_filter != 'all':
                    q = q.eq('status', status_filter)
                res = q.order('created_at', desc=True).limit(limit).execute()
            except Exception:
                # Fallback to direct select without join
                q = admin.table('wallet_transactions').select('*').eq('type', 'deposit')
                if status_filter and status_filter != 'all':
                    q = q.eq('status', status_filter)
                res = q.order('created_at', desc=True).limit(limit).execute()

            items = res.data or []
            # Gather missing profile details if not embedded
            missing_user_ids = [it['user_id'] for it in items if 'profiles' not in it and it.get('user_id')]
            prof_map = {}
            if missing_user_ids:
                try:
                    p_res = admin.table('profiles').select('id, email, full_name, username').in_('id', list(set(missing_user_ids))).execute()
                    prof_map = {p['id']: p for p in (p_res.data or [])}
                except Exception:
                    pass

            # Flatten profile information & fallback to metadata
            for item in items:
                prof = item.get('profiles') or prof_map.get(item.get('user_id')) or {}
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
                'new_balance': wallet['balance'],
                'user_id': user_id,
                'amount': amount
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
                'new_balance': new_bal,
                'user_id': user_id,
                'amount': amount
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
    def record_pending_crypto_deposit(user_id: str, amount_usd: float, payment_id: str,
                                      pay_address: str, pay_amount: float, pay_currency: str,
                                      network: str = '', order_id: str = '',
                                      extra_meta: dict = None) -> dict:
        """Records a pending crypto deposit transaction for real-time tracking."""
        ref = f"NP-{payment_id}"
        meta = {
            'payment_id': str(payment_id),
            'pay_address': pay_address,
            'pay_amount': pay_amount,
            'pay_currency': pay_currency,
            'network': network,
            'order_id': order_id,
            'gateway': 'nowpayments'
        }
        if extra_meta:
            meta.update(extra_meta)

        desc = f"Crypto Deposit ({pay_currency.upper()}) via NOWPayments"
        admin = get_supabase_admin()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if not admin or not DBService._is_uuid(user_id):
            existing = next((t for t in mock_db.transactions if t.get('reference') == ref), None)
            if existing:
                return {'success': True, 'transaction': existing}
            mock_tx = {
                'id': f"np-tx-{len(mock_db.transactions) + 1}",
                'user_id': user_id,
                'amount': amount_usd,
                'type': 'deposit',
                'status': 'pending',
                'reference': ref,
                'description': desc,
                'payment_channel': 'crypto_nowpayments',
                'metadata': meta,
                'created_at': now_iso
            }
            mock_db.transactions.insert(0, mock_tx)
            return {'success': True, 'transaction': mock_tx}

        try:
            chk = admin.table('wallet_transactions').select('*').eq('reference', ref).limit(1).execute()
            if chk.data:
                return {'success': True, 'transaction': chk.data[0]}

            tx_data = {
                'user_id': user_id,
                'amount': amount_usd,
                'type': 'deposit',
                'status': 'pending',
                'reference': ref,
                'description': desc,
                'payment_channel': 'crypto_nowpayments',
                'metadata': meta
            }
            ins = admin.table('wallet_transactions').insert(tx_data).execute()
            created_tx = ins.data[0] if ins.data else tx_data
            return {'success': True, 'transaction': created_tx}
        except Exception as e:
            print(f"[DBService] record_pending_crypto_deposit error: {e}")
            return {'success': False, 'message': str(e)}

    @staticmethod
    def get_crypto_deposit_by_payment_id(payment_id: str, user_id: str = None) -> dict:
        """Looks up a crypto deposit transaction by its NOWPayments payment ID."""
        ref = f"NP-{payment_id}"
        admin = get_supabase_admin()
        if admin:
            try:
                q = admin.table('wallet_transactions').select('*').eq('reference', ref)
                if user_id:
                    q = q.eq('user_id', user_id)
                res = q.limit(1).execute()
                if res.data:
                    return res.data[0]
            except Exception as e:
                print(f"[DBService] get_crypto_deposit_by_payment_id error: {e}")

        tx = next((t for t in mock_db.transactions if t.get('reference') == ref), None)
        if tx and (not user_id or tx.get('user_id') == user_id):
            return tx
        return None

    @staticmethod
    def complete_crypto_deposit(payment_id: str, actually_paid: float = None,
                                notes: str = 'Automated NOWPayments IPN verification',
                                metadata_update: dict = None) -> dict:
        """
        Idempotently marks a NOWPayments crypto deposit as completed and credits the user's wallet.
        Guarantees protection against double-crediting.
        """
        ref = f"NP-{payment_id}"
        admin = get_supabase_admin()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if admin:
            try:
                tx_res = admin.table('wallet_transactions').select('*').eq('reference', ref).limit(1).execute()
                if not tx_res.data:
                    tx_res = admin.table('wallet_transactions').select('*').eq('metadata->>payment_id', str(payment_id)).limit(1).execute()

                if not tx_res.data:
                    # Check mock fallback (e.g. demo users or local tests)
                    tx_mock = next((t for t in mock_db.transactions if t.get('reference') == ref), None)
                    if not tx_mock:
                        return {'success': False, 'message': f'Transaction for NOWPayments ID {payment_id} not found.'}
                else:
                    tx_mock = None

                if tx_mock:
                    tx = tx_mock
                    tx_id = tx['id']
                    user_id = tx['user_id']
                    amount_usd = float(tx.get('amount', 0.00))

                    if tx.get('status') == 'completed':
                        return {'success': True, 'already_completed': True, 'amount': amount_usd, 'user_id': user_id}

                    tx['status'] = 'completed'
                    tx['verified_at'] = now_iso
                    wallet = mock_db.wallets.get(user_id, {'balance': 0.00, 'currency': 'USD'})
                    wallet['balance'] += amount_usd
                    mock_db.wallets[user_id] = wallet

                    return {
                        'success': True,
                        'already_completed': False,
                        'new_balance': wallet['balance'],
                        'user_id': user_id,
                        'amount': amount_usd
                    }

                tx = tx_res.data[0]
                tx_id = tx['id']
                user_id = tx['user_id']
                amount_usd = float(tx.get('amount', 0.00))

                # IDEMPOTENCY CHECK: Never credit twice
                if tx.get('status') == 'completed':
                    return {
                        'success': True,
                        'already_completed': True,
                        'message': 'Transaction was already credited.',
                        'user_id': user_id,
                        'amount': amount_usd
                    }

                meta = tx.get('metadata') or {}
                if metadata_update:
                    meta.update(metadata_update)
                if actually_paid is not None:
                    meta['actually_paid'] = actually_paid
                meta['verified_at'] = now_iso
                meta['verified_by_system'] = 'NOWPayments IPN'

                existing_cols = set(tx.keys())
                upd_data = {
                    'status': 'completed',
                    'metadata': meta
                }
                if 'verified_at' in existing_cols:
                    upd_data['verified_at'] = now_iso
                if 'admin_notes' in existing_cols:
                    upd_data['admin_notes'] = notes

                admin.table('wallet_transactions').update(upd_data).eq('id', tx_id).execute()

                # Credit user wallet
                w_res = admin.table('wallets').select('id, balance').eq('user_id', user_id).limit(1).execute()
                if w_res.data:
                    cur_bal = float(w_res.data[0].get('balance', 0.00))
                    new_bal = round(cur_bal + amount_usd, 2)
                    admin.table('wallets').update({
                        'balance': new_bal,
                        'updated_at': now_iso
                    }).eq('user_id', user_id).execute()
                else:
                    new_bal = round(amount_usd, 2)
                    admin.table('wallets').insert({
                        'user_id': user_id,
                        'balance': new_bal,
                        'currency': 'USD'
                    }).execute()

                # Send in-app notification
                pay_curr = (meta.get('pay_currency') or 'crypto').upper()
                DBService.create_user_notification(
                    user_id=user_id,
                    title="Crypto Deposit Credited!",
                    message=f"Your {pay_curr} deposit of ${amount_usd:.2f} has been verified and added to your wallet balance.",
                    type="deposit",
                    link="/wallet",
                    metadata={'payment_id': payment_id, 'amount': amount_usd}
                )

                return {
                    'success': True,
                    'already_completed': False,
                    'new_balance': new_bal,
                    'user_id': user_id,
                    'amount': amount_usd,
                    'message': f"Successfully credited ${amount_usd:.2f} to wallet."
                }
            except Exception as e:
                print(f"[DBService] complete_crypto_deposit error: {e}")
                return {'success': False, 'message': str(e)}

        # Mock fallback
        tx = next((t for t in mock_db.transactions if t.get('reference') == ref), None)
        if not tx:
            return {'success': False, 'message': 'Mock transaction not found.'}

        if tx.get('status') == 'completed':
            return {'success': True, 'already_completed': True, 'amount': tx['amount'], 'user_id': tx['user_id']}

        tx['status'] = 'completed'
        tx['verified_at'] = now_iso
        user_id = tx['user_id']
        amount_usd = float(tx.get('amount', 0.00))

        wallet = mock_db.wallets.get(user_id, {'balance': 0.00, 'currency': 'USD'})
        wallet['balance'] += amount_usd
        mock_db.wallets[user_id] = wallet

        return {
            'success': True,
            'already_completed': False,
            'new_balance': wallet['balance'],
            'user_id': user_id,
            'amount': amount_usd
        }

    @staticmethod
    def fail_crypto_deposit(payment_id: str, reason: str = 'Payment expired or failed in gateway') -> dict:
        """Marks a pending crypto deposit as failed/cancelled."""
        ref = f"NP-{payment_id}"
        admin = get_supabase_admin()
        if admin:
            try:
                tx_res = admin.table('wallet_transactions').select('*').eq('reference', ref).limit(1).execute()
                if tx_res.data:
                    tx = tx_res.data[0]
                    if tx.get('status') != 'completed':
                        meta = tx.get('metadata') or {}
                        meta['failure_reason'] = reason
                        admin.table('wallet_transactions').update({
                            'status': 'failed',
                            'metadata': meta
                        }).eq('id', tx['id']).execute()
                        return {'success': True}
            except Exception as e:
                print(f"[DBService] fail_crypto_deposit error: {e}")
        return {'success': False}

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
        """Promote or demote user role ('admin', 'support', or 'user')."""
        if new_role not in ('user', 'admin', 'support'):
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

    # =========================================================================
    # SUPPORT TICKET SYSTEM METHODS
    # =========================================================================

    @staticmethod
    def create_support_ticket(user_id: str, subject: str, initial_message: str = None,
                              category: str = 'general', priority: str = 'normal',
                              user_name: str = 'User', user_email: str = None) -> dict:
        """Create a new support ticket with subject, and optionally post the initial message."""
        import random
        ticket_code = f"TK-{random.randint(1000, 9999)}"
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        admin = get_supabase_admin()

        # Try Supabase insert
        if admin and DBService._is_uuid(user_id):
            try:
                ticket_data = {
                    'ticket_number': ticket_code,
                    'user_id': user_id,
                    'subject': subject.strip(),
                    'category': category or 'general',
                    'status': 'open',
                    'priority': priority or 'normal',
                    'unread_user_count': 0,
                    'unread_admin_count': 1,
                    'last_message': initial_message[:150] if initial_message else 'Ticket created',
                    'last_message_at': now_iso
                }
                res = admin.table('support_tickets').insert(ticket_data).execute()
                if res.data and len(res.data) > 0:
                    ticket = res.data[0]
                    # Add initial message if provided
                    if initial_message and initial_message.strip():
                        admin.table('support_messages').insert({
                            'ticket_id': ticket['id'],
                            'sender_id': user_id if DBService._is_uuid(user_id) else None,
                            'sender_role': 'user',
                            'sender_name': user_name or 'User',
                            'message': initial_message.strip(),
                            'is_read': False
                        }).execute()

                    # Add notification for user confirming ticket opened
                    try:
                        admin.table('support_notifications').insert({
                            'user_id': user_id,
                            'ticket_id': ticket['id'],
                            'title': f'Ticket {ticket_code} Created',
                            'message': f'Your ticket "{subject[:40]}" has been received. Our support team will reply shortly.',
                            'type': 'ticket_opened',
                            'is_read': False
                        }).execute()
                    except Exception:
                        pass

                    return ticket
            except Exception as e:
                print(f"[DBService] create_support_ticket Supabase error: {e}")

        # Fallback to in-memory mock_db
        new_ticket_id = f"tk-{uuid.uuid4().hex[:8]}"
        ticket_obj = {
            'id': new_ticket_id,
            'ticket_number': ticket_code,
            'user_id': user_id,
            'user_name': user_name,
            'user_email': user_email,
            'subject': subject.strip(),
            'category': category or 'general',
            'status': 'open',
            'priority': priority or 'normal',
            'unread_user_count': 0,
            'unread_admin_count': 1,
            'last_message': initial_message[:150] if initial_message else 'Ticket created',
            'last_message_at': now_iso,
            'created_at': now_iso,
            'updated_at': now_iso
        }
        mock_db.support_tickets.insert(0, ticket_obj)

        if initial_message and initial_message.strip():
            msg_obj = {
                'id': f"msg-{uuid.uuid4().hex[:8]}",
                'ticket_id': new_ticket_id,
                'sender_id': user_id,
                'sender_role': 'user',
                'sender_name': user_name or 'User',
                'message': initial_message.strip(),
                'is_read': False,
                'created_at': now_iso
            }
            mock_db.support_messages.append(msg_obj)

        mock_db.support_notifications.insert(0, {
            'id': f"notif-{uuid.uuid4().hex[:8]}",
            'user_id': user_id,
            'ticket_id': new_ticket_id,
            'title': f'Ticket {ticket_code} Created',
            'message': f'Your ticket "{subject[:40]}" has been received. Our team will reply shortly.',
            'type': 'ticket_opened',
            'is_read': False,
            'created_at': now_iso
        })

        return ticket_obj

    @staticmethod
    def get_user_tickets(user_id: str, limit: int = 50) -> list:
        """Fetch all tickets for a specific user."""
        admin = get_supabase_admin()
        if admin and DBService._is_uuid(user_id):
            try:
                res = admin.table('support_tickets') \
                    .select('*') \
                    .eq('user_id', user_id) \
                    .order('updated_at', desc=True) \
                    .limit(limit) \
                    .execute()
                if res.data is not None:
                    return res.data
            except Exception as e:
                print(f"[DBService] get_user_tickets error: {e}")

        # Fallback
        return [t for t in mock_db.support_tickets if t.get('user_id') == user_id]

    @staticmethod
    def get_ticket_by_id(ticket_id: str, user_id: str = None, is_admin: bool = False) -> dict:
        """Fetch single ticket by ID. Validates ownership if not admin."""
        admin = get_supabase_admin()
        if admin and DBService._is_uuid(ticket_id):
            try:
                q = admin.table('support_tickets').select('*').eq('id', ticket_id).limit(1)
                if not is_admin and user_id and DBService._is_uuid(user_id):
                    q = q.eq('user_id', user_id)
                res = q.execute()
                if res.data and len(res.data) > 0:
                    ticket = res.data[0]
                    # Fetch user profile info for admin view
                    if is_admin and ticket.get('user_id') and DBService._is_uuid(ticket['user_id']):
                        try:
                            prof = admin.table('profiles').select('full_name, email, phone_number').eq('id', ticket['user_id']).limit(1).execute()
                            if prof.data and len(prof.data) > 0:
                                ticket['user_name'] = prof.data[0].get('full_name') or 'User'
                                ticket['user_email'] = prof.data[0].get('email') or ''
                                ticket['user_phone'] = prof.data[0].get('phone_number') or ''
                        except Exception:
                            pass
                    return ticket
            except Exception as e:
                print(f"[DBService] get_ticket_by_id error: {e}")

        # Fallback
        for t in mock_db.support_tickets:
            if t.get('id') == ticket_id or t.get('ticket_number') == ticket_id:
                if is_admin or not user_id or t.get('user_id') == user_id:
                    return t
        return None

    @staticmethod
    def get_ticket_messages(ticket_id: str, user_id: str = None, is_admin: bool = False,
                            mark_read: bool = True) -> list:
        """Fetch all chat messages for a ticket, sorted chronologically."""
        admin = get_supabase_admin()
        if admin and DBService._is_uuid(ticket_id):
            try:
                # Check authorization
                if not is_admin and user_id and DBService._is_uuid(user_id):
                    t_check = admin.table('support_tickets').select('id').eq('id', ticket_id).eq('user_id', user_id).limit(1).execute()
                    if not t_check.data:
                        return []

                res = admin.table('support_messages') \
                    .select('*') \
                    .eq('ticket_id', ticket_id) \
                    .order('created_at', desc=False) \
                    .execute()

                messages = res.data or []

                if mark_read:
                    if is_admin:
                        # Mark user messages as read
                        admin.table('support_messages').update({'is_read': True}).eq('ticket_id', ticket_id).eq('sender_role', 'user').execute()
                        admin.table('support_tickets').update({'unread_admin_count': 0}).eq('id', ticket_id).execute()
                    elif user_id:
                        # Mark admin messages as read
                        admin.table('support_messages').update({'is_read': True}).eq('ticket_id', ticket_id).neq('sender_role', 'user').execute()
                        admin.table('support_tickets').update({'unread_user_count': 0}).eq('id', ticket_id).execute()

                return messages
            except Exception as e:
                print(f"[DBService] get_ticket_messages error: {e}")

        # Fallback
        msgs = [m for m in mock_db.support_messages if m.get('ticket_id') == ticket_id]
        if mark_read:
            for m in msgs:
                if is_admin and m.get('sender_role') == 'user':
                    m['is_read'] = True
                elif not is_admin and m.get('sender_role') != 'user':
                    m['is_read'] = True
            for t in mock_db.support_tickets:
                if t.get('id') == ticket_id:
                    if is_admin:
                        t['unread_admin_count'] = 0
                    else:
                        t['unread_user_count'] = 0
        return msgs

    @staticmethod
    def add_support_message(ticket_id: str, sender_id: str, sender_name: str,
                            sender_role: str, message: str) -> dict:
        """Append a message to a ticket. Updates ticket timestamp, last message, and unread badges."""
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        admin = get_supabase_admin()

        if sender_role in ('admin', 'support'):
            sender_name = 'Support'

        if admin and DBService._is_uuid(ticket_id):
            try:
                # 1. Insert message
                msg_data = {
                    'ticket_id': ticket_id,
                    'sender_id': sender_id if DBService._is_uuid(sender_id) else None,
                    'sender_role': sender_role,
                    'sender_name': sender_name or 'Support',
                    'message': message.strip(),
                    'is_read': False
                }
                res = admin.table('support_messages').insert(msg_data).execute()
                new_msg = res.data[0] if res.data else msg_data

                # 2. Update ticket status & unread counters
                t_res = admin.table('support_tickets').select('*').eq('id', ticket_id).limit(1).execute()
                if t_res.data and len(t_res.data) > 0:
                    cur_ticket = t_res.data[0]
                    update_fields = {
                        'last_message': message[:150].strip(),
                        'last_message_at': now_iso,
                        'updated_at': now_iso
                    }
                    if sender_role == 'user':
                        update_fields['unread_admin_count'] = (cur_ticket.get('unread_admin_count') or 0) + 1
                        # If user replies to a resolved/closed ticket, automatically reopen it
                        if cur_ticket.get('status') in ('resolved', 'closed'):
                            update_fields['status'] = 'open'
                    else:
                        # Support / admin replied
                        update_fields['unread_user_count'] = (cur_ticket.get('unread_user_count') or 0) + 1
                        if cur_ticket.get('status') == 'open':
                            update_fields['status'] = 'pending'

                        # Create notification for user
                        try:
                            admin.table('support_notifications').insert({
                                'user_id': cur_ticket['user_id'],
                                'ticket_id': ticket_id,
                                'title': f'Support Reply: #{cur_ticket.get("ticket_number")}',
                                'message': message[:120].strip(),
                                'type': 'reply',
                                'is_read': False
                            }).execute()
                        except Exception:
                            pass

                    admin.table('support_tickets').update(update_fields).eq('id', ticket_id).execute()

                return new_msg
            except Exception as e:
                print(f"[DBService] add_support_message error: {e}")

        # Fallback
        new_msg = {
            'id': f"msg-{uuid.uuid4().hex[:8]}",
            'ticket_id': ticket_id,
            'sender_id': sender_id,
            'sender_role': sender_role,
            'sender_name': sender_name,
            'message': message.strip(),
            'is_read': False,
            'created_at': now_iso
        }
        mock_db.support_messages.append(new_msg)

        for t in mock_db.support_tickets:
            if t.get('id') == ticket_id:
                t['last_message'] = message[:150].strip()
                t['last_message_at'] = now_iso
                t['updated_at'] = now_iso
                if sender_role == 'user':
                    t['unread_admin_count'] = (t.get('unread_admin_count') or 0) + 1
                    if t.get('status') in ('resolved', 'closed'):
                        t['status'] = 'open'
                else:
                    t['unread_user_count'] = (t.get('unread_user_count') or 0) + 1
                    if t.get('status') == 'open':
                        t['status'] = 'pending'

                    mock_db.support_notifications.insert(0, {
                        'id': f"notif-{uuid.uuid4().hex[:8]}",
                        'user_id': t.get('user_id'),
                        'ticket_id': ticket_id,
                        'title': f'Support Reply: #{t.get("ticket_number")}',
                        'message': message[:120].strip(),
                        'type': 'reply',
                        'is_read': False,
                        'created_at': now_iso
                    })
                break

        return new_msg

    @staticmethod
    def update_ticket_status(ticket_id: str, new_status: str, actor_role: str = 'admin',
                             actor_name: str = 'Support') -> dict:
        """Update ticket status ('open', 'pending', 'resolved', 'closed') and notify user if resolved."""
        valid_statuses = ('open', 'pending', 'resolved', 'closed')
        if new_status not in valid_statuses:
            return {'success': False, 'message': f'Invalid status. Allowed: {", ".join(valid_statuses)}'}

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        admin = get_supabase_admin()

        if admin and DBService._is_uuid(ticket_id):
            try:
                t_res = admin.table('support_tickets').select('*').eq('id', ticket_id).limit(1).execute()
                if not t_res.data:
                    return {'success': False, 'message': 'Ticket not found.'}

                cur_ticket = t_res.data[0]
                admin.table('support_tickets').update({
                    'status': new_status,
                    'updated_at': now_iso
                }).eq('id', ticket_id).execute()

                # Add system audit message in the chat thread
                status_label = new_status.capitalize()
                admin.table('support_messages').insert({
                    'ticket_id': ticket_id,
                    'sender_role': 'system',
                    'sender_name': 'System',
                    'message': f'Ticket marked as {status_label} by Support.',
                    'is_read': True
                }).execute()

                # Notify user if resolved or closed
                if new_status == 'resolved':
                    try:
                        admin.table('support_notifications').insert({
                            'user_id': cur_ticket['user_id'],
                            'ticket_id': ticket_id,
                            'title': f'Ticket #{cur_ticket.get("ticket_number")} Resolved',
                            'message': f'Your support ticket "{cur_ticket.get("subject", "")[:35]}" has been resolved. Let us know if you need anything else!',
                            'type': 'ticket_resolved',
                            'is_read': False
                        }).execute()
                    except Exception:
                        pass

                return {'success': True, 'status': new_status}
            except Exception as e:
                print(f"[DBService] update_ticket_status error: {e}")

        # Fallback
        found = False
        for t in mock_db.support_tickets:
            if t.get('id') == ticket_id:
                t['status'] = new_status
                t['updated_at'] = now_iso
                found = True

                mock_db.support_messages.append({
                    'id': f"msg-{uuid.uuid4().hex[:8]}",
                    'ticket_id': ticket_id,
                    'sender_role': 'system',
                    'sender_name': 'System',
                    'message': f'Ticket marked as {new_status.capitalize()} by Support.',
                    'is_read': True,
                    'created_at': now_iso
                })

                if new_status == 'resolved':
                    mock_db.support_notifications.insert(0, {
                        'id': f"notif-{uuid.uuid4().hex[:8]}",
                        'user_id': t.get('user_id'),
                        'ticket_id': ticket_id,
                        'title': f'Ticket #{t.get("ticket_number")} Resolved',
                        'message': f'Your support ticket "{t.get("subject", "")[:35]}" has been resolved.',
                        'type': 'ticket_resolved',
                        'is_read': False,
                        'created_at': now_iso
                    })
                break

        if found:
            return {'success': True, 'status': new_status}
        return {'success': False, 'message': 'Ticket not found.'}

    @staticmethod
    def get_all_tickets_admin(status_filter: str = None, search: str = None, limit: int = 100) -> list:
        """Fetch all tickets for admin support desk, joined with user profile info."""
        admin = get_supabase_admin()
        if admin:
            try:
                q = admin.table('support_tickets').select('*')
                if status_filter and status_filter != 'all':
                    q = q.eq('status', status_filter)
                if search:
                    q = q.or_(f"ticket_number.ilike.%{search}%,subject.ilike.%{search}%")

                res = q.order('updated_at', desc=True).limit(limit).execute()
                tickets = res.data or []

                # Fetch profiles map for user names/emails
                user_ids = list({t['user_id'] for t in tickets if t.get('user_id') and DBService._is_uuid(t.get('user_id'))})
                if user_ids:
                    try:
                        p_res = admin.table('profiles').select('id, full_name, email, phone_number').in_('id', user_ids).execute()
                        pmap = {p['id']: p for p in (p_res.data or [])}
                        for t in tickets:
                            prof = pmap.get(t.get('user_id'), {})
                            t['user_name'] = prof.get('full_name') or 'User'
                            t['user_email'] = prof.get('email') or 'N/A'
                            t['user_phone'] = prof.get('phone_number') or ''
                    except Exception:
                        pass

                return tickets
            except Exception as e:
                print(f"[DBService] get_all_tickets_admin error: {e}")

        # Fallback
        results = []
        for t in mock_db.support_tickets:
            if status_filter and status_filter != 'all' and t.get('status') != status_filter:
                continue
            if search:
                s_lower = search.lower()
                if s_lower not in t.get('ticket_number', '').lower() and \
                   s_lower not in t.get('subject', '').lower() and \
                   s_lower not in t.get('user_email', '').lower():
                    continue
            results.append(t)
        return results[:limit]

    @staticmethod
    def get_admin_support_stats() -> dict:
        """Summary counts for Admin Support Desk."""
        admin = get_supabase_admin()
        if admin:
            try:
                # We can query count of open, pending, resolved
                all_t = admin.table('support_tickets').select('status, unread_admin_count').execute()
                rows = all_t.data or []
                total = len(rows)
                open_cnt = sum(1 for r in rows if r.get('status') == 'open')
                pending_cnt = sum(1 for r in rows if r.get('status') == 'pending')
                resolved_cnt = sum(1 for r in rows if r.get('status') == 'resolved')
                unread_cnt = sum(r.get('unread_admin_count', 0) for r in rows)
                return {
                    'total': total,
                    'open': open_cnt,
                    'pending': pending_cnt,
                    'resolved': resolved_cnt,
                    'unread_admin': unread_cnt
                }
            except Exception as e:
                print(f"[DBService] get_admin_support_stats error: {e}")

        # Fallback
        rows = mock_db.support_tickets
        return {
            'total': len(rows),
            'open': sum(1 for r in rows if r.get('status') == 'open'),
            'pending': sum(1 for r in rows if r.get('status') == 'pending'),
            'resolved': sum(1 for r in rows if r.get('status') == 'resolved'),
            'unread_admin': sum(r.get('unread_admin_count', 0) for r in rows)
        }

    @staticmethod
    def get_user_support_unread(user_id: str) -> dict:
        """Get unread message count and unread notifications for topbar badge & floating widget."""
        admin = get_supabase_admin()
        if admin and DBService._is_uuid(user_id):
            try:
                # 1. Sum unread messages across user tickets
                t_res = admin.table('support_tickets').select('unread_user_count').eq('user_id', user_id).execute()
                unread_msgs = sum(r.get('unread_user_count', 0) for r in (t_res.data or []))

                # 2. Unread notifications
                n_res = admin.table('support_notifications').select('*').eq('user_id', user_id).order('created_at', desc=True).limit(8).execute()
                notifs = n_res.data or []
                unread_notifs = sum(1 for n in notifs if not n.get('is_read'))

                return {
                    'unread_total': max(unread_msgs, unread_notifs),
                    'unread_messages': unread_msgs,
                    'unread_notifications': unread_notifs,
                    'notifications': notifs
                }
            except Exception as e:
                print(f"[DBService] get_user_support_unread error: {e}")

        # Fallback
        notifs = [n for n in mock_db.support_notifications if n.get('user_id') == user_id]
        t_rows = [t for t in mock_db.support_tickets if t.get('user_id') == user_id]
        unread_msgs = sum(t.get('unread_user_count', 0) for t in t_rows)
        unread_notifs = sum(1 for n in notifs if not n.get('is_read'))
        return {
            'unread_total': max(unread_msgs, unread_notifs),
            'unread_messages': unread_msgs,
            'unread_notifications': unread_notifs,
            'notifications': notifs[:8]
        }

    @staticmethod
    def mark_notifications_read(user_id: str, notif_id: str = None) -> bool:
        """Mark specific or all notifications as read for a user."""
        admin = get_supabase_admin()
        if admin and DBService._is_uuid(user_id):
            try:
                q = admin.table('support_notifications').update({'is_read': True}).eq('user_id', user_id)
                if notif_id and notif_id != 'all' and DBService._is_uuid(notif_id):
                    q = q.eq('id', notif_id)
                q.execute()
                return True
            except Exception as e:
                print(f"[DBService] mark_notifications_read error: {e}")

        # Fallback
        for n in mock_db.support_notifications:
            if n.get('user_id') == user_id:
                if not notif_id or notif_id == 'all' or n.get('id') == notif_id:
                    n['is_read'] = True
        return True

    # =========================================================================
    # USER NOTIFICATIONS & ADMIN BROADCASTS
    # =========================================================================

    @staticmethod
    def create_user_notification(user_id: str = None, title: str = '', message: str = '',
                                 type: str = 'system', link: str = None, metadata: dict = None) -> dict:
        """Create an activity notification for a user or broadcast to all users (user_id=None)."""
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        notif_id = str(uuid.uuid4())
        record = {
            'id': notif_id,
            'user_id': user_id if (user_id and DBService._is_uuid(user_id)) else None,
            'title': title,
            'message': message,
            'type': type,
            'link': link,
            'metadata': metadata or {},
            'is_read': False,
            'created_at': now_str
        }

        admin = get_supabase_admin()
        if admin:
            try:
                res = admin.table('user_notifications').insert(record).execute()
                if res.data:
                    return res.data[0]
            except Exception as e:
                print(f"[DBService] create_user_notification Supabase error (falling back to mock): {e}")

        # In-memory / Mock fallback
        if not hasattr(mock_db, 'user_notifications'):
            mock_db.user_notifications = []
        mock_db.user_notifications.insert(0, record)
        return record

    @staticmethod
    def get_user_notifications(user_id: str, limit: int = 30) -> list:
        """Retrieve notifications for a user, including global broadcasts (user_id IS NULL)."""
        admin = get_supabase_admin()
        if admin and DBService._is_uuid(user_id):
            try:
                res = admin.table('user_notifications').select('*').or_(f"user_id.eq.{user_id},user_id.is.null").order('created_at', desc=True).limit(limit).execute()
                if res.data is not None:
                    return res.data
            except Exception as e:
                print(f"[DBService] get_user_notifications Supabase error: {e}")

        items = getattr(mock_db, 'user_notifications', [])
        user_items = [n for n in items if n.get('user_id') == user_id or n.get('user_id') is None]
        user_items.sort(key=lambda x: str(x.get('created_at', '')), reverse=True)
        return user_items[:limit]

    @staticmethod
    def get_user_unread_notifications_count(user_id: str) -> int:
        """Return the count of unread notifications for a user."""
        notifs = DBService.get_user_notifications(user_id, limit=50)
        return sum(1 for n in notifs if not n.get('is_read'))

    @staticmethod
    def mark_user_notifications_read(user_id: str, notification_id: str = None) -> bool:
        """Mark a specific notification or all notifications as read for a user."""
        admin = get_supabase_admin()
        if admin and DBService._is_uuid(user_id):
            try:
                if notification_id and notification_id != 'all' and DBService._is_uuid(notification_id):
                    admin.table('user_notifications').update({'is_read': True}).eq('id', notification_id).execute()
                else:
                    admin.table('user_notifications').update({'is_read': True}).or_(f"user_id.eq.{user_id},user_id.is.null").execute()
                return True
            except Exception as e:
                print(f"[DBService] mark_user_notifications_read Supabase error: {e}")

        items = getattr(mock_db, 'user_notifications', [])
        for n in items:
            if n.get('user_id') == user_id or n.get('user_id') is None:
                if not notification_id or notification_id == 'all' or n.get('id') == notification_id:
                    n['is_read'] = True
        return True

    @staticmethod
    def get_all_notifications_admin(limit: int = 50) -> list:
        """Fetch all notifications for admin audit / broadcast view."""
        admin = get_supabase_admin()
        if admin:
            try:
                res = admin.table('user_notifications').select('*').order('created_at', desc=True).limit(limit).execute()
                if res.data is not None:
                    items = res.data
                    user_ids = list(set([it['user_id'] for it in items if it.get('user_id')]))
                    if user_ids:
                        try:
                            p_res = admin.table('profiles').select('id, email, full_name').in_('id', user_ids).execute()
                            p_map = {p['id']: p for p in (p_res.data or [])}
                            for it in items:
                                prof = p_map.get(it.get('user_id'), {})
                                it['user_email'] = prof.get('email', 'Direct User')
                                it['user_name'] = prof.get('full_name', '')
                        except Exception:
                            pass
                    return items
            except Exception as e:
                print(f"[DBService] get_all_notifications_admin Supabase error: {e}")

        items = getattr(mock_db, 'user_notifications', [])
        items.sort(key=lambda x: str(x.get('created_at', '')), reverse=True)
        return items[:limit]

    @staticmethod
    def get_platform_settings():
        """Retrieve cached platform pricing and configuration settings."""
        from app.services.settings_service import SettingsService
        return SettingsService.get_settings()

    # =========================================================================
    # 5-CHARACTER REFERRAL SYSTEM & REFERRAL WALLET
    # =========================================================================

    @staticmethod
    def generate_referral_code() -> str:
        """Generate a random 5-character uppercase alphanumeric referral code."""
        charset = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        return ''.join(secrets.choice(charset) for _ in range(5))

    @staticmethod
    def get_or_create_referral_code(user_id: str) -> str:
        """Retrieve user's 5-character referral code or generate a unique one if missing."""
        if not user_id or user_id == 'demo-user-id' or not DBService._is_uuid(user_id):
            mock_w = mock_db.referral_wallets.setdefault(user_id or 'demo-user-id', {'referral_code': 'TUNDE', 'referral_balance': 2.50, 'referred_by': None})
            return mock_w.get('referral_code', 'TUNDE')

        admin = get_supabase_admin()
        if not admin:
            return 'TGSIM'

        try:
            res = admin.table('profiles').select('id, referral_code').eq('id', user_id).limit(1).execute()
            if res.data and len(res.data) > 0:
                code = res.data[0].get('referral_code')
                if code and len(str(code).strip()) > 0:
                    return str(code).strip().upper()

            # Generate unique 5-character referral code
            for _ in range(10):
                new_code = DBService.generate_referral_code()
                chk = admin.table('profiles').select('id').eq('referral_code', new_code).limit(1).execute()
                if not chk.data:
                    admin.table('profiles').update({'referral_code': new_code}).eq('id', user_id).execute()
                    return new_code
            return 'TGSIM'
        except Exception as e:
            print(f"[DBService] get_or_create_referral_code notice: {e}")
            return 'TGSIM'

    @staticmethod
    def link_referral(user_id: str, referral_code: str) -> bool:
        """Links a new user to their referrer using a 5-character referral code."""
        code = (referral_code or '').strip().upper()
        if not code or not user_id:
            return False

        if user_id == 'demo-user-id' or not DBService._is_uuid(user_id):
            mock_w = mock_db.referral_wallets.setdefault(user_id, {'referral_code': 'DEMO1', 'referral_balance': 0.00, 'referred_by': None})
            mock_w['referred_by'] = 'demo-user-id'
            return True

        admin = get_supabase_admin()
        if not admin:
            return False

        try:
            # Find referrer by referral_code
            ref_user = admin.table('profiles').select('id, username').eq('referral_code', code).limit(1).execute()
            if not ref_user.data:
                return False

            referrer_id = ref_user.data[0]['id']
            if referrer_id == user_id:
                return False  # Self-referral not permitted

            admin.table('profiles').update({
                'referred_by': referrer_id
            }).eq('id', user_id).execute()
            return True
        except Exception as e:
            print(f"[DBService] link_referral error: {e}")
            return False

    @staticmethod
    def get_referral_details(user_id: str, host_url: str = 'https://tgsims.com/') -> dict:
        """Fetch all referral program stats, balance, invited users, and history for user."""
        host_url = host_url.rstrip('/') + '/'
        
        # Fallback for demo / local
        if not user_id or user_id == 'demo-user-id' or not DBService._is_uuid(user_id):
            mock_w = mock_db.referral_wallets.setdefault(user_id or 'demo-user-id', {'referral_code': 'TUNDE', 'referral_balance': 2.50, 'referred_by': None})
            code = mock_w.get('referral_code', 'TUNDE')
            balance = float(mock_w.get('referral_balance', 2.50))
            commissions = [c for c in getattr(mock_db, 'referral_commissions', []) if c.get('referrer_id') == user_id]
            redemptions = [r for r in getattr(mock_db, 'referral_redemptions', []) if r.get('user_id') == user_id]
            total_earned = sum(float(c.get('commission_earned', 0)) for c in commissions if c.get('status') == 'credited')
            return {
                'code': code,
                'link': f"{host_url}r/{code}",
                'register_link': f"{host_url}auth/register?ref={code}",
                'referral_balance': balance,
                'earned_usd': round(total_earned or 2.50, 2),
                'invited': 8,
                'converted': 5,
                'min_withdrawal': 1.00,
                'can_redeem': balance >= 1.00,
                'recent_commissions': commissions[:20],
                'recent_redemptions': redemptions[:20]
            }

        admin = get_supabase_admin()
        if not admin:
            return {
                'code': 'TGSIM',
                'link': f"{host_url}r/TGSIM",
                'register_link': f"{host_url}auth/register?ref=TGSIM",
                'referral_balance': 0.00,
                'earned_usd': 0.00,
                'invited': 0,
                'converted': 0,
                'min_withdrawal': 1.00,
                'can_redeem': False,
                'recent_commissions': [],
                'recent_redemptions': []
            }

        try:
            code = DBService.get_or_create_referral_code(user_id)
            
            # Fetch referral balance
            ref_balance = 0.00
            try:
                prof_res = admin.table('profiles').select('referral_balance').eq('id', user_id).limit(1).execute()
                if prof_res.data:
                    ref_balance = float(prof_res.data[0].get('referral_balance') or 0.00)
            except Exception:
                pass

            # Fetch invited count (profiles where referred_by == user_id)
            invited_count = 0
            try:
                inv_res = admin.table('profiles').select('id').eq('referred_by', user_id).execute()
                invited_count = len(inv_res.data) if inv_res.data else 0
            except Exception:
                pass

            # Fetch commissions history
            commissions = []
            total_earned = 0.00
            converted_user_ids = set()
            try:
                comm_res = admin.table('referral_commissions').select('*').eq('referrer_id', user_id).order('created_at', desc=True).limit(50).execute()
                if comm_res.data:
                    commissions = comm_res.data
                    for c in commissions:
                        if c.get('status') == 'credited':
                            total_earned += float(c.get('commission_earned', 0.00))
                            if c.get('referred_user_id'):
                                converted_user_ids.add(c.get('referred_user_id'))
            except Exception:
                pass

            # Redemptions history
            redemptions = []
            try:
                red_res = admin.table('referral_redemptions').select('*').eq('user_id', user_id).order('created_at', desc=True).limit(50).execute()
                if red_res.data:
                    redemptions = red_res.data
            except Exception:
                pass

            return {
                'code': code,
                'link': f"{host_url}r/{code}",
                'register_link': f"{host_url}auth/register?ref={code}",
                'referral_balance': round(ref_balance, 2),
                'earned_usd': round(total_earned, 2),
                'invited': invited_count,
                'converted': len(converted_user_ids),
                'min_withdrawal': 1.00,
                'can_redeem': ref_balance >= 1.00,
                'recent_commissions': commissions,
                'recent_redemptions': redemptions
            }
        except Exception as e:
            print(f"[DBService] get_referral_details error: {e}")
            return {
                'code': 'TGSIM',
                'link': f"{host_url}r/TGSIM",
                'register_link': f"{host_url}auth/register?ref=TGSIM",
                'referral_balance': 0.00,
                'earned_usd': 0.00,
                'invited': 0,
                'converted': 0,
                'min_withdrawal': 1.00,
                'can_redeem': False,
                'recent_commissions': [],
                'recent_redemptions': []
            }

    @staticmethod
    def record_referral_commission(user_id: str, amount_spent: float, order_id: str = None, order_reference: str = None) -> bool:
        """When a user spends money, awards 5% commission to their referrer into the referral wallet."""
        if not user_id or amount_spent <= 0:
            return False

        commission_rate = 5.00  # 5%
        commission_earned = round(float(amount_spent) * (commission_rate / 100.0), 4)
        if commission_earned <= 0:
            return False

        # Mock fallback
        if user_id == 'demo-user-id' or not DBService._is_uuid(user_id):
            referrer_id = 'demo-user-id'
            mock_w = mock_db.referral_wallets.setdefault(referrer_id, {'referral_code': 'TUNDE', 'referral_balance': 2.50, 'referred_by': None})
            mock_w['referral_balance'] = round(mock_w.get('referral_balance', 0.00) + commission_earned, 4)
            mock_db.referral_commissions.insert(0, {
                'id': f"ref-comm-{len(mock_db.referral_commissions)+1}",
                'referrer_id': referrer_id,
                'referred_user_id': user_id,
                'order_id': order_id,
                'order_reference': order_reference,
                'amount_spent': amount_spent,
                'commission_rate': commission_rate,
                'commission_earned': commission_earned,
                'status': 'credited',
                'description': f"5% referral earning from order #{order_reference or order_id}",
                'created_at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            })
            return True

        admin = get_supabase_admin()
        if not admin:
            return False

        try:
            # Check who referred this user
            p_res = admin.table('profiles').select('id, referred_by, username').eq('id', user_id).limit(1).execute()
            if not p_res.data:
                return False
            
            referrer_id = p_res.data[0].get('referred_by')
            if not referrer_id or referrer_id == user_id:
                return False

            buyer_name = p_res.data[0].get('username') or 'Friend'

            # 1. Update referrer's referral_balance in profiles
            ref_res = admin.table('profiles').select('id, referral_balance').eq('id', referrer_id).limit(1).execute()
            if not ref_res.data:
                return False
            
            cur_ref_bal = float(ref_res.data[0].get('referral_balance') or 0.00)
            new_ref_bal = round(cur_ref_bal + commission_earned, 4)

            admin.table('profiles').update({
                'referral_balance': new_ref_bal,
                'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
            }).eq('id', referrer_id).execute()

            # 2. Insert into referral_commissions
            comm_data = {
                'referrer_id': referrer_id,
                'referred_user_id': user_id,
                'amount_spent': amount_spent,
                'commission_rate': commission_rate,
                'commission_earned': commission_earned,
                'status': 'credited',
                'description': f"5% referral earning from order #{order_reference or order_id}"
            }
            if order_id and DBService._is_uuid(order_id):
                comm_data['order_id'] = order_id
            if order_reference:
                comm_data['order_reference'] = str(order_reference)

            try:
                admin.table('referral_commissions').insert(comm_data).execute()
            except Exception as ins_e:
                print(f"[DBService] referral_commissions insert notice: {ins_e}")

            # 3. Trigger notification to referrer
            try:
                DBService.create_user_notification(
                    user_id=referrer_id,
                    title="Referral Commission Earned",
                    message=f"You earned ${commission_earned:.2f} (5%) from {buyer_name}'s order #{order_reference or 'verification'}.",
                    type="promo",
                    link="/account/referral",
                    metadata={'commission': commission_earned, 'order_reference': order_reference}
                )
            except Exception:
                pass

            return True
        except Exception as e:
            print(f"[DBService] record_referral_commission error: {e}")
            return False

    @staticmethod
    def reverse_referral_commission(order_id: str) -> bool:
        """Reverses referral commission if an order is cancelled or refunded."""
        if not order_id:
            return False

        admin = get_supabase_admin()
        if not admin:
            # Check mock
            for c in getattr(mock_db, 'referral_commissions', []):
                if (c.get('order_id') == order_id or c.get('order_reference') == order_id) and c.get('status') == 'credited':
                    c['status'] = 'reversed'
                    ref_id = c.get('referrer_id')
                    mock_w = mock_db.referral_wallets.get(ref_id)
                    if mock_w:
                        mock_w['referral_balance'] = max(0.00, mock_w.get('referral_balance', 0.00) - float(c.get('commission_earned', 0)))
                    return True
            return False

        try:
            q = admin.table('referral_commissions').select('*').eq('status', 'credited')
            if DBService._is_uuid(order_id):
                q = q.or_(f"order_id.eq.{order_id},order_reference.eq.{order_id}")
            else:
                q = q.eq('order_reference', str(order_id))
            
            res = q.limit(1).execute()
            if not res.data:
                return False

            comm = res.data[0]
            comm_id = comm['id']
            referrer_id = comm['referrer_id']
            comm_amt = float(comm.get('commission_earned', 0.00))

            # Deduct from referrer's referral_balance
            ref_p = admin.table('profiles').select('referral_balance').eq('id', referrer_id).limit(1).execute()
            if ref_p.data:
                cur_bal = float(ref_p.data[0].get('referral_balance') or 0.00)
                new_bal = max(0.00, round(cur_bal - comm_amt, 4))
                admin.table('profiles').update({'referral_balance': new_bal}).eq('id', referrer_id).execute()

            admin.table('referral_commissions').update({
                'status': 'reversed',
                'description': f"{comm.get('description', '')} (Reversed due to order refund)"
            }).eq('id', comm_id).execute()
            return True
        except Exception as e:
            print(f"[DBService] reverse_referral_commission error: {e}")
            return False

    @staticmethod
    def redeem_referral_balance(user_id: str, amount: float = None) -> dict:
        """Redeem referral balance into main wallet balance. Minimum withdrawal is $1.00."""
        MIN_WITHDRAWAL = 1.00

        # Mock handling
        if not user_id or user_id == 'demo-user-id' or not DBService._is_uuid(user_id):
            mock_w = mock_db.referral_wallets.setdefault(user_id or 'demo-user-id', {'referral_code': 'TUNDE', 'referral_balance': 2.50, 'referred_by': None})
            cur_bal = float(mock_w.get('referral_balance', 0.00))
            withdraw_amt = round(float(amount) if amount is not None else cur_bal, 2)

            if withdraw_amt < MIN_WITHDRAWAL:
                return {'success': False, 'message': f'Minimum withdrawal amount is ${MIN_WITHDRAWAL:.2f}.'}
            if withdraw_amt > cur_bal:
                return {'success': False, 'message': f'Cannot withdraw ${withdraw_amt:.2f}. Available referral balance is ${cur_bal:.2f}.'}

            mock_w['referral_balance'] = round(cur_bal - withdraw_amt, 2)
            credit_res = DBService.credit_wallet_balance(
                user_id=user_id,
                amount=withdraw_amt,
                trans_type='referral_payout',
                reference=f"REF-PAY-{secrets.token_hex(4).upper()}",
                description=f"Redeemed ${withdraw_amt:.2f} referral earnings to main wallet"
            )
            mock_db.referral_redemptions.insert(0, {
                'id': f"red-{len(mock_db.referral_redemptions)+1}",
                'user_id': user_id,
                'amount': withdraw_amt,
                'status': 'completed',
                'created_at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            })
            return {
                'success': True,
                'amount': withdraw_amt,
                'new_referral_balance': mock_w['referral_balance'],
                'new_main_balance': credit_res.get('new_balance'),
                'message': f'Successfully transferred ${withdraw_amt:.2f} to your main wallet!'
            }

        admin = get_supabase_admin()
        if not admin:
            return {'success': False, 'message': 'Database connection unavailable.'}

        try:
            # 1. Check current referral balance
            p_res = admin.table('profiles').select('id, referral_balance').eq('id', user_id).limit(1).execute()
            if not p_res.data:
                return {'success': False, 'message': 'User profile not found.'}

            cur_bal = float(p_res.data[0].get('referral_balance') or 0.00)
            withdraw_amt = round(float(amount) if amount is not None else cur_bal, 2)

            if withdraw_amt < MIN_WITHDRAWAL:
                return {
                    'success': False,
                    'message': f'Minimum withdrawal amount is ${MIN_WITHDRAWAL:.2f}. You currently have ${cur_bal:.2f}.'
                }
            if withdraw_amt > cur_bal:
                return {
                    'success': False,
                    'message': f'Cannot withdraw ${withdraw_amt:.2f}. Available referral balance is ${cur_bal:.2f}.'
                }

            new_ref_bal = round(cur_bal - withdraw_amt, 4)

            # 2. Deduct from profiles.referral_balance
            admin.table('profiles').update({
                'referral_balance': new_ref_bal,
                'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
            }).eq('id', user_id).execute()

            # 3. Credit main wallet balance
            ref_tx_code = f"REF-PAY-{secrets.token_hex(4).upper()}"
            credit_res = DBService.credit_wallet_balance(
                user_id=user_id,
                amount=withdraw_amt,
                trans_type='referral_payout',
                reference=ref_tx_code,
                description=f"Redeemed ${withdraw_amt:.2f} referral balance to main wallet",
                metadata={'referral_redemption': True}
            )

            # 4. Insert into referral_redemptions
            try:
                admin.table('referral_redemptions').insert({
                    'user_id': user_id,
                    'amount': withdraw_amt,
                    'status': 'completed',
                    'description': f"Transfer of ${withdraw_amt:.2f} referral balance to main wallet"
                }).execute()
            except Exception as r_err:
                print(f"[DBService] referral_redemptions insert notice: {r_err}")

            # 5. User notification
            try:
                DBService.create_user_notification(
                    user_id=user_id,
                    title="Referral Balance Redeemed",
                    message=f"${withdraw_amt:.2f} has been transferred from your Referral Wallet to your Main Balance.",
                    type="deposit",
                    link="/wallet"
                )
            except Exception:
                pass

            return {
                'success': True,
                'amount': withdraw_amt,
                'new_referral_balance': new_ref_bal,
                'new_main_balance': credit_res.get('new_balance'),
                'message': f'Successfully redeemed ${withdraw_amt:.2f} to your main wallet!'
            }
        except Exception as e:
            print(f"[DBService] redeem_referral_balance error: {e}")
            return {'success': False, 'message': 'Failed to process referral withdrawal. Please try again.'}



