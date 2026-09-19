"""Admin Panel routes for Tgsims.
Provides platform management:
- Overview KPIs & Live Provider API balances
- Dynamic Pricing & Margin Control Center (USD/NGN FX rate, 5sim markup %, TextVerified markup %, Reactivation fee)
- Multi-Channel Deposit Verification (Squad, Crypto, Bank Transfer) with atomic wallet credit & audit trail
- SIM Order monitoring & manual refund trigger
- User Account inspection, role promotion, and wallet adjustments
Protected strictly by session['user']['role'] == 'admin'.
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from app.services.db_service import DBService
from app.services.settings_service import SettingsService
from app.services.sim_provider import FiveSimClient, SIMProviderService
import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.before_request
def require_admin():
    """Ensure user is logged in and possesses administrator or support privileges."""
    user = session.get('user')
    if not user or not isinstance(user, dict):
        flash('Please sign in with administrator credentials.', 'error')
        return redirect(url_for('auth.login', next=request.path))

    role = user.get('role')
    if role not in ('admin', 'support'):
        flash('Access restricted. Administrator privileges required.', 'error')
        return redirect(url_for('dashboard.index'))

    # Role-based restriction for 'support' staff:
    # Support staff are strictly limited to Support, Notifications, Orders, and Deposits.
    if role == 'support':
        endpoint = request.endpoint or ''
        if endpoint in ('admin.index', ''):
            return redirect(url_for('admin.support'))

        admin_only_endpoints = (
            'admin.pricing',
            'admin.users',
            'admin.update_user_role',
            'admin.adjust_user_balance',
        )
        if any(endpoint.startswith(ep) for ep in admin_only_endpoints):
            flash('Access restricted. Support staff permissions are limited to Support, Notifications, Orders, and Deposits.', 'error')
            return redirect(url_for('admin.support'))



@admin_bp.route('')
@admin_bp.route('/')
def index():
    """Admin Overview dashboard with KPI cards and live provider balance check."""
    stats = DBService.get_admin_overview_stats()
    settings = SettingsService.get_settings()

    # Query live 5sim balance
    fivesim_balance = None
    fivesim_err = None
    try:
        fsc = FiveSimClient()
        if fsc.is_configured:
            bal_res = fsc.get_balance()
            if bal_res.get('success'):
                fivesim_balance = {
                    'balance': bal_res.get('balance'),
                    'currency': bal_res.get('currency', 'RUB'),
                    'usd_estimate': bal_res.get('usd_estimate', 0.0)
                }
            else:
                fivesim_err = bal_res.get('message')
        else:
            fivesim_err = "API Key not configured in .env"
    except Exception as e:
        fivesim_err = str(e)

    # Query TextVerified client status & live balance
    tv_balance = None
    tv_status = {'configured': False, 'status': 'Unknown'}
    try:
        tv_client = SIMProviderService.get_textverified_client()
        if tv_client:
            tv_status['configured'] = True
            tv_status['status'] = 'Active & Connected'
            try:
                acc = tv_client.account
                acc_bal = getattr(acc, 'balance', None)
                if callable(acc_bal):
                    acc_bal = acc_bal()
                if acc_bal is not None:
                    tv_balance = {
                        'balance': float(acc_bal),
                        'currency': 'USD',
                        'username': getattr(acc, 'username', '')
                    }
            except Exception as tv_e:
                print(f"[Admin] Error fetching TextVerified balance: {tv_e}")
        else:
            tv_status['configured'] = False
            tv_status['status'] = 'Not Configured (Missing TEXTVERIFIED_API_KEY)'
    except Exception as e:
        tv_status['status'] = f"Error: {e}"

    # Recent pending deposits
    pending_deposits = DBService.get_all_deposits_admin(status_filter='pending', limit=5)
    recent_orders = DBService.get_all_orders_admin(limit=6)

    return render_template(
        'admin/index.html',
        stats=stats,
        settings=settings,
        fivesim_balance=fivesim_balance,
        fivesim_err=fivesim_err,
        tv_status=tv_status,
        tv_balance=tv_balance,
        pending_deposits=pending_deposits,
        recent_orders=recent_orders,
        active_page='overview'
    )


# =============================================================================
# PRICING & MARGIN CONTROL CENTER
# =============================================================================

@admin_bp.route('/pricing', methods=['GET', 'POST'])
def pricing():
    """Manage USD/NGN exchange rate, 5sim markup %, TextVerified markup %, and Reactivation fee."""
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_settings':
            try:
                ngn_rate = float(request.form.get('ngn_per_usd_rate', 1600.00))
                fivesim_pct = float(request.form.get('fivesim_markup_percent', 30.00))
                fivesim_floor = float(request.form.get('fivesim_min_profit_usd', 0.30))
                tv_pct = float(request.form.get('textverified_markup_percent', 25.00))
                tv_floor = float(request.form.get('textverified_min_profit_usd', 0.50))
                react_fee = float(request.form.get('reactivation_fee_usd', 1.00))
                crypto_addr = request.form.get('crypto_deposit_address', '').strip()
                squad_on = 'squad_enabled' in request.form
                crypto_on = 'crypto_enabled' in request.form
                bank_details = request.form.get('manual_bank_details', '').strip()

                SettingsService.update_settings({
                    'ngn_per_usd_rate': ngn_rate,
                    'fivesim_markup_percent': fivesim_pct,
                    'fivesim_min_profit_usd': fivesim_floor,
                    'textverified_markup_percent': tv_pct,
                    'textverified_min_profit_usd': tv_floor,
                    'reactivation_fee_usd': react_fee,
                    'crypto_deposit_address': crypto_addr,
                    'squad_enabled': squad_on,
                    'crypto_enabled': crypto_on,
                    'manual_bank_details': bank_details
                })
                flash('Pricing settings and profit margins updated successfully! Changes take effect immediately.', 'success')
            except Exception as e:
                flash(f'Failed to update settings: {e}', 'error')

        elif action == 'add_override':
            svc_code = request.form.get('service_code', '').strip().lower()
            svc_name = request.form.get('service_name', '').strip()
            prov_type = request.form.get('provider_type', '5sim').strip().lower()
            try:
                override_price = float(request.form.get('override_price_usd', 0.00))
                notes = request.form.get('notes', '').strip()
                if svc_code and override_price > 0:
                    SettingsService.set_price_override(svc_code, svc_name or svc_code.capitalize(), prov_type, override_price, notes)
                    flash(f'Price override saved for {svc_name or svc_code} (${override_price:.2f}).', 'success')
                else:
                    flash('Please enter a valid service code and override price.', 'error')
            except Exception as e:
                flash(f'Error saving price override: {e}', 'error')

        elif action == 'delete_override':
            override_id = request.form.get('override_id')
            if override_id:
                SettingsService.delete_price_override(override_id)
                flash('Price override removed.', 'info')

        return redirect(url_for('admin.pricing'))

    settings = SettingsService.get_settings(force_refresh=True)
    overrides = SettingsService.get_price_overrides()

    # Precalculated examples for admin visualization
    rate = float(settings.get('ngn_per_usd_rate', 1600.00))
    f5_pct = float(settings.get('fivesim_markup_percent', 30.00))
    f5_floor = float(settings.get('fivesim_min_profit_usd', 0.30))
    tv_pct = float(settings.get('textverified_markup_percent', 25.00))
    react_fee = float(settings.get('reactivation_fee_usd', 1.00))

    # Example 5sim cost: $0.50 -> retail price calculation
    f5_ex_cost = 0.50
    f5_ex_price = round(max(f5_ex_cost * (1 + f5_pct / 100), f5_ex_cost + f5_floor), 2)
    f5_ex_profit = round(f5_ex_price - f5_ex_cost, 2)

    # Example TextVerified cost: $2.00 -> retail price calculation
    tv_ex_cost = 2.00
    tv_ex_price = round(tv_ex_cost * (1 + tv_pct / 100), 2)
    tv_ex_profit = round(tv_ex_price - tv_ex_cost, 2)

    examples = {
        'fivesim': {'cost': f5_ex_cost, 'price': f5_ex_price, 'profit': f5_ex_profit, 'ngn': round(f5_ex_price * rate, 2)},
        'textverified': {'cost': tv_ex_cost, 'price': tv_ex_price, 'profit': tv_ex_profit, 'ngn': round(tv_ex_price * rate, 2)},
        'reactivation': {'price': react_fee, 'ngn': round(react_fee * rate, 2)}
    }

    f5_raw = SIMProviderService.get_5sim_us_services(apply_markup=False)
    seen_f5 = set()
    f5_catalog = []
    for s in f5_raw:
        sc = s.get('service_code')
        if sc and sc not in seen_f5:
            seen_f5.add(sc)
            f5_catalog.append({
                'service_code': sc,
                'service_name': s.get('service_name', sc.capitalize()),
                'base_cost': float(s.get('price_usd', 0.50))
            })

    tv_raw = SIMProviderService.get_textverified_us_services(apply_markup=False)
    seen_tv = set()
    tv_catalog = []
    for s in tv_raw:
        sc = s.get('service_code')
        if sc and sc not in seen_tv:
            seen_tv.add(sc)
            tv_catalog.append({
                'service_code': sc,
                'service_name': s.get('service_name', sc.capitalize()),
                'base_cost': float(s.get('price_usd', 0.50))
            })

    services_catalog = {
        '5sim': f5_catalog,
        'textverified': tv_catalog
    }

    return render_template(
        'admin/pricing.html',
        settings=settings,
        overrides=overrides,
        examples=examples,
        services_catalog=services_catalog,
        active_page='pricing'
    )


# =============================================================================
# MANUAL DEPOSIT VERIFICATION & AUDIT
# =============================================================================

@admin_bp.route('/deposits')
def deposits():
    """List deposit transactions with filtering by status."""
    status_filter = request.args.get('status', 'pending')
    all_deposits = DBService.get_all_deposits_admin(status_filter=status_filter, limit=100)
    settings = SettingsService.get_settings()

    return render_template(
        'admin/deposits.html',
        deposits=all_deposits,
        status_filter=status_filter,
        settings=settings,
        active_page='deposits'
    )


@admin_bp.route('/deposits/<tx_id>/verify', methods=['POST'])
def verify_deposit(tx_id):
    """Admin manually approves and credits a pending deposit."""
    admin_user = session.get('user', {})
    admin_id = admin_user.get('id', 'admin')
    admin_notes = request.form.get('admin_notes', f"Verified by {admin_user.get('full_name', 'Admin')}")

    res = DBService.verify_deposit_admin(tx_id, admin_user_id=admin_id, admin_notes=admin_notes)
    if res.get('success'):
        # Dispatch notification to user
        u_id = res.get('user_id')
        amt = float(res.get('amount', 0.00))
        rate = float(SettingsService.get_settings().get('ngn_per_usd_rate', 1600.00))
        if u_id:
            DBService.create_user_notification(
                user_id=u_id,
                title="Deposit Verified & Credited! 💳",
                message=f"Your deposit of ${amt:.2f} (≈ ₦{amt * rate:,.2f}) has been verified and added to your wallet balance.",
                type="deposit",
                link="/wallet"
            )
        flash(res.get('message', 'Deposit verified and wallet credited!'), 'success')
    else:
        flash(res.get('message', 'Failed to verify deposit.'), 'error')

    return redirect(url_for('admin.deposits', status=request.form.get('return_status', 'pending')))


@admin_bp.route('/deposits/<tx_id>/reject', methods=['POST'])
def reject_deposit(tx_id):
    """Admin rejects a pending deposit."""
    admin_user = session.get('user', {})
    admin_id = admin_user.get('id', 'admin')
    reason = request.form.get('reason', 'Payment not received or invalid reference')

    res = DBService.reject_deposit_admin(tx_id, admin_user_id=admin_id, reason=reason)
    if res.get('success'):
        flash('Deposit marked as rejected.', 'info')
    else:
        flash(res.get('message', 'Failed to reject deposit.'), 'error')

    return redirect(url_for('admin.deposits', status=request.form.get('return_status', 'pending')))


# =============================================================================
# ORDER MONITORING & REFUND MANAGEMENT
# =============================================================================

@admin_bp.route('/orders')
def orders():
    """All user verification orders across the platform."""
    status_filter = request.args.get('status', 'all')
    all_orders = DBService.get_all_orders_admin(status_filter=status_filter, limit=100)

    return render_template(
        'admin/orders.html',
        orders=all_orders,
        status_filter=status_filter,
        active_page='orders'
    )


@admin_bp.route('/orders/<order_id>/refund', methods=['POST'])
def manual_refund_order(order_id):
    """Admin triggers a manual refund for an order back to the user's wallet."""
    user_id = request.form.get('user_id')
    reason = request.form.get('reason', 'Manual admin refund')

    res = DBService.refund_order(order_id, user_id=user_id, reason=reason)
    if res.get('success'):
        flash(res.get('message', 'Order refunded and funds credited to user wallet!'), 'success')
    else:
        flash(res.get('message', 'Failed to refund order.'), 'error')

    return redirect(url_for('admin.orders'))


# =============================================================================
# USER MANAGEMENT & BALANCE ADJUSTMENTS
# =============================================================================

@admin_bp.route('/users')
def users():
    """User account directory with wallet balances and role controls."""
    search_q = request.args.get('q', '').strip()
    user_list = DBService.get_all_users_admin(search=search_q, limit=100)

    return render_template(
        'admin/users.html',
        users=user_list,
        search_q=search_q,
        active_page='users'
    )


@admin_bp.route('/users/<user_id>/role', methods=['POST'])
@admin_bp.route('/users/<user_id>/update-role', methods=['POST'])
def update_user_role(user_id):
    """Promote or demote a user role ('user', 'support', 'admin')."""
    new_role = request.form.get('role', 'user')
    current_admin = session.get('user', {})
    if user_id == current_admin.get('id') and new_role != 'admin':
        flash('You cannot demote yourself from administrator.', 'error')
        return redirect(url_for('admin.users'))

    ok = DBService.update_user_role_admin(user_id, new_role)
    if ok:
        role_label = 'SUPPORT AGENT' if new_role == 'support' else ('ADMINISTRATOR' if new_role == 'admin' else 'STANDARD USER')
        flash(f'User role successfully updated to {role_label}.', 'success')
    else:
        flash(f'Failed to update user role to {new_role}. Please ensure database constraint allows support role.', 'error')

    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<user_id>/adjust-balance', methods=['POST'])
def adjust_user_balance(user_id):
    """Admin credits or debits a user wallet balance with audit note."""
    admin_user = session.get('user', {})
    admin_id = admin_user.get('id', 'admin')

    try:
        amount = float(request.form.get('amount', 0.00))
        reason = request.form.get('reason', 'Administrative adjustment').strip()
        adjustment_type = request.form.get('adjustment_type', 'credit')

        if amount <= 0:
            flash('Amount must be greater than zero.', 'error')
            return redirect(url_for('admin.users'))

        signed_amount = amount if adjustment_type == 'credit' else -amount
        res = DBService.adjust_user_balance_admin(
            user_id=user_id,
            amount=signed_amount,
            reason=reason,
            admin_user_id=admin_id
        )

        if res.get('success'):
            rate = float(SettingsService.get_settings().get('ngn_per_usd_rate', 1600.00))
            if adjustment_type == 'credit':
                DBService.create_user_notification(
                    user_id=user_id,
                    title="Funds Added to Wallet 💰",
                    message=f"An administrator credited ${amount:.2f} (≈ ₦{amount * rate:,.2f}) to your wallet. Reason: {reason}",
                    type="admin_credit",
                    link="/wallet"
                )
            else:
                DBService.create_user_notification(
                    user_id=user_id,
                    title="Funds Deducted from Wallet ⚠️",
                    message=f"An administrator deducted ${amount:.2f} (≈ ₦{amount * rate:,.2f}) from your wallet. Reason: {reason}",
                    type="admin_debit",
                    link="/wallet"
                )
            flash(f"Wallet successfully adjusted by ${signed_amount:+.2f}. New balance: ${res.get('new_balance', 0):.2f}", 'success')
        else:
            flash(res.get('message', 'Failed to adjust balance.'), 'error')
    except Exception as e:
        flash(f'Error adjusting balance: {e}', 'error')

    return redirect(url_for('admin.users'))


# =============================================================================
# SUPPORT TICKETS & COMPLAINTS DESK
# =============================================================================

@admin_bp.route('/support')
@admin_bp.route('/support/<ticket_id>')
def support(ticket_id=None):
    """Customer Support & Complaints Desk.
    Provides realtime ticket management, message history, instant reply, and status updates.
    """
    status_filter = request.args.get('status', 'all')
    search_q = request.args.get('q', '').strip()
    selected_id = ticket_id or request.args.get('ticket_id', '').strip()

    tickets = DBService.get_all_tickets_admin(status_filter=status_filter, search=search_q)
    stats = DBService.get_admin_support_stats()

    selected_ticket = None
    messages = []
    has_explicit_selection = bool(selected_id)

    if selected_id:
        selected_ticket = DBService.get_ticket_by_id(selected_id, is_admin=True)
        if selected_ticket:
            messages = DBService.get_ticket_messages(selected_ticket['id'], is_admin=True, mark_read=True)
    elif tickets:
        selected_ticket = tickets[0]
        messages = DBService.get_ticket_messages(selected_ticket['id'], is_admin=True, mark_read=True)

    return render_template(
        'admin/support.html',
        tickets=tickets,
        selected_ticket=selected_ticket,
        messages=messages,
        stats=stats,
        status_filter=status_filter,
        search_q=search_q,
        has_explicit_selection=has_explicit_selection,
        active_page='support'
    )


@admin_bp.route('/support/<ticket_id>/reply', methods=['POST'])
def support_reply(ticket_id):
    """Standard form POST fallback for replying to a ticket."""
    user = session.get('user', {})
    reply_text = request.form.get('message', '').strip()
    new_status = request.form.get('status')

    if not reply_text:
        flash('Reply message cannot be empty.', 'error')
        return redirect(url_for('admin.support', ticket_id=ticket_id))

    admin_name = 'Support'
    sender_role = 'support'

    DBService.add_support_message(
        ticket_id=ticket_id,
        sender_id=user.get('id'),
        sender_name='Support',
        sender_role=sender_role,
        message=reply_text
    )

    if new_status:
        DBService.update_ticket_status(ticket_id, new_status, actor_role=sender_role, actor_name='Support')

    flash('Reply sent successfully.', 'success')
    return redirect(url_for('admin.support', ticket_id=ticket_id))


@admin_bp.route('/support/<ticket_id>/status', methods=['POST'])
def support_status(ticket_id):
    """Update ticket status via form POST."""
    user = session.get('user', {})
    new_status = request.form.get('status', '').strip()

    res = DBService.update_ticket_status(
        ticket_id=ticket_id,
        new_status=new_status,
        actor_role='admin',
        actor_name='Support'
    )
    if res.get('success'):
        flash(f'Ticket status changed to {new_status.capitalize()}.', 'success')
    else:
        flash(res.get('message', 'Failed to update ticket status.'), 'error')

    return redirect(url_for('admin.support', ticket_id=ticket_id))


# =============================================================================
# ADMIN PUSH NOTIFICATIONS & BROADCASTS
# =============================================================================

@admin_bp.route('/notifications', methods=['GET', 'POST'])
def notifications():
    """Admin Push Notification Console: broadcast to all users or target a specific user."""
    if request.method == 'POST':
        target = request.form.get('target', 'all')
        target_user_id = request.form.get('target_user_id', '').strip() or None
        title = request.form.get('title', '').strip()
        message = request.form.get('message', '').strip()
        notif_type = request.form.get('type', 'promo')
        link = request.form.get('link', '').strip() or None

        if not title or not message:
            flash('Title and message are required to broadcast a notification.', 'error')
            return redirect(url_for('admin.notifications'))

        recipient_id = target_user_id if target == 'single' else None
        notif = DBService.create_user_notification(
            user_id=recipient_id,
            title=title,
            message=message,
            type=notif_type,
            link=link
        )
        if notif:
            target_desc = f"user ({recipient_id})" if recipient_id else "all registered users"
            flash(f"Notification successfully pushed to {target_desc}!", 'success')
        else:
            flash('Failed to dispatch notification.', 'error')
        return redirect(url_for('admin.notifications'))

    all_notifs = DBService.get_all_notifications_admin(limit=50)
    all_users = DBService.get_all_users_admin()
    return render_template(
        'admin/notifications.html',
        notifications=all_notifs,
        users=all_users,
        active_page='notifications'
    )


