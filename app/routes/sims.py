"""Virtual number routes: buy a number, view orders, and OTP history."""
from flask import Blueprint, render_template, session, redirect, url_for
from app.services.sim_provider import SIMProviderService
from app.services.db_service import DBService

sims_bp = Blueprint('sims', __name__, url_prefix='/sims')


def _require_user():
    return session.get('user')


@sims_bp.route('/us-canada', endpoint='us_canada')
@sims_bp.route('/order-us-canada', endpoint='order_us_canada')
def us_canada():
    """Order US & Canada Virtual Numbers  -  high-reliability cellular lines."""
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    config = SIMProviderService.get_us_canada_config()
    wallet = DBService.get_wallet(user['id'])

    why = [
        {'icon': 'shield', 'title': 'Real Cellular SIMs', 'text': 'Direct AT&T, Verizon, T-Mobile & Rogers lines.'},
        {'icon': 'check', 'title': 'WhatsApp Guaranteed', 'text': '100% pre-checked unbanned phone numbers.'},
        {'icon': 'bolt', 'title': 'Instant SMS Delivery', 'text': 'High-priority direct cellular routing.'},
        {'icon': 'refresh', 'title': 'Auto-Refund Protection', 'text': 'Full wallet refund if no SMS is received.'},
    ]

    return render_template(
        'sims/us_canada.html',
        config=config,
        wallet=wallet,
        why=why,
        user=user
    )


@sims_bp.route('/store', endpoint='store')
@sims_bp.route('/buy', endpoint='buy')
@sims_bp.route('/order-numbers', endpoint='order_numbers')
def store():
    """Order Numbers  -  worldwide country + service selection."""
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    catalog = SIMProviderService.get_catalog()
    wallet = DBService.get_wallet(user['id'])

    why = [
        {'icon': 'bolt', 'title': 'Instant Activation', 'text': 'Numbers ready immediately.'},
        {'icon': 'trend', 'title': 'High Success Rate', 'text': '99% SMS delivery rate.'},
        {'icon': 'globe', 'title': 'Global Coverage', 'text': 'Numbers from 150+ countries.'},
        {'icon': 'shield', 'title': 'Secure Payments', 'text': 'Encrypted transactions.'},
    ]

    return render_template('sims/buy.html', catalog=catalog, wallet=wallet, why=why, user=user)


@sims_bp.route('/my-sims')
def my_sims():
    """My Orders  -  track and manage virtual number orders."""
    import datetime
    from app.services.settings_service import SettingsService
    from app.services.supabase_client import get_supabase_admin
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    orders = DBService.get_orders(user['id'])
    now_utc = datetime.datetime.now(datetime.timezone.utc)

    # Check which orders have previously received an SMS message in history
    orders_with_sms = set()
    admin = get_supabase_admin()
    if admin and orders and user['id'] != 'demo-user-id':
        order_ids = [str(o['id']) for o in orders if o.get('id')]
        if order_ids:
            try:
                sms_res = admin.table('sim_sms_messages').select('order_id').in_('order_id', order_ids).execute()
                if sms_res.data:
                    orders_with_sms = {str(row['order_id']) for row in sms_res.data}
            except Exception as e:
                print(f"[my_sims] error querying sim_sms_messages: {e}")

    for o in orders:
        status = str(o.get('status', '')).lower()
        has_code = bool(o.get('sms_code'))
        is_active = status in ('active', 'pending') and not has_code
        o['is_active_sim'] = is_active

        # An order has received an OTP if it currently has sms_code, received status, or an archived SMS entry
        has_received_otp = has_code or (str(o.get('id')) in orders_with_sms) or status in ('received', 'completed')
        o['has_received_otp'] = has_received_otp

        try:
            o['price'] = float(o.get('price') or o.get('user_cost') or 0.00)
        except (ValueError, TypeError):
            o['price'] = 0.00

        is_react = (o.get('order_type') == 'reactivation') or ('reactivat' in str(o.get('full_sms_text', '')).lower()) or ('reactivat' in str(o.get('notes', '')).lower())
        o['is_react'] = is_react

        remaining = 300
        elapsed = 0
        if is_react and o.get('expires_at'):
            # Only reactivation orders use TextVerified's dynamic carrier window (e.g. 20m, 60m, 120m)
            try:
                exp_str = str(o['expires_at']).replace('Z', '+00:00')
                try:
                    exp_dt = datetime.datetime.fromisoformat(exp_str)
                except ValueError:
                    exp_dt = datetime.datetime.strptime(exp_str, '%Y-%m-%d %H:%M:%S')
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=datetime.timezone.utc)
                remaining = max(0, int((exp_dt - now_utc).total_seconds()))

                if o.get('created_at'):
                    cat_str = str(o['created_at']).replace('Z', '+00:00')
                    try:
                        c_dt = datetime.datetime.fromisoformat(cat_str)
                    except ValueError:
                        c_dt = datetime.datetime.strptime(cat_str, '%Y-%m-%d %H:%M:%S')
                    if c_dt.tzinfo is None:
                        c_dt = c_dt.replace(tzinfo=datetime.timezone.utc)
                    elapsed = max(0, int((now_utc - c_dt).total_seconds()))
            except Exception as e:
                print(f"[my_sims] error calculating expires_at countdown: {e}")
                remaining = 0
                elapsed = 300
        elif o.get('created_at'):
            # Normal number purchases: strictly 5 minutes (300 seconds) wait time!
            try:
                cat_str = str(o['created_at']).replace('Z', '+00:00')
                try:
                    c_dt = datetime.datetime.fromisoformat(cat_str)
                except ValueError:
                    c_dt = datetime.datetime.strptime(cat_str, '%Y-%m-%d %H:%M:%S')
                if c_dt.tzinfo is None:
                    c_dt = c_dt.replace(tzinfo=datetime.timezone.utc)
                elapsed = max(0, int((now_utc - c_dt).total_seconds()))
                remaining = max(0, int(300 - elapsed))
            except Exception:
                remaining = 0
                elapsed = 300

        o['countdown_seconds'] = remaining
        o['elapsed_seconds'] = elapsed
        # Reactivation rule: Reactivations CANNOT be cancelled manually. User must wait until time exhausts or OTP arrives.
        o['can_cancel'] = (not is_react) and (elapsed >= 180)

        # Reactivation availability: Reactivation is available unless carrier rejected reactivation
        react_closed = bool(o.get('reactivation_expired'))
        o['reactivation_closed'] = react_closed
        o['can_reactivate'] = (not react_closed) and has_received_otp

        # If active order exceeded time window, trigger automatic refund immediately
        if is_active and remaining <= 0:
            try:
                prov_id = o.get('provider_order_id')
                if not is_react and prov_id and not str(prov_id).startswith('SIM-') and not str(prov_id).startswith('USCA-'):
                    SIMProviderService.cancel_order(str(prov_id))
                timeout_reason = "Auto-refunded: Reactivation timeout" if is_react else "Auto-refunded: SMS timeout"
                DBService.refund_order(o.get('id') or o.get('order_reference'), user['id'], reason=timeout_reason)
                if is_react:
                    o['status'] = 'received'
                else:
                    o['status'] = 'refunded'
                o['is_active_sim'] = False
            except Exception as e:
                print(f"[my_sims] Auto-refund on page load error: {e}")

    react_fee = SettingsService.get_reactivation_fee()
    return render_template('sims/orders.html', orders=orders, user=user, reactivation_fee_usd=react_fee)


@sims_bp.route('/rentals', endpoint='rentals')
@sims_bp.route('/rent-number', endpoint='rent_number')
@sims_bp.route('/rent', endpoint='rent')
def rentals():
    """Rent a Number - dedicated long-term virtual numbers (3, 7, 14, 30 days)."""
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    catalog = SIMProviderService.get_rental_catalog()
    rentals_list = DBService.get_rentals(user['id'])
    wallet = DBService.get_wallet(user['id'])

    import datetime
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    for r in rentals_list:
        status = str(r.get('status', 'active')).lower()
        exp = r.get('expires_at')
        rem = 0
        if exp:
            try:
                exp_str = str(exp).replace('Z', '+00:00')
                try:
                    exp_dt = datetime.datetime.fromisoformat(exp_str)
                except ValueError:
                    exp_dt = datetime.datetime.strptime(exp_str, '%Y-%m-%d %H:%M:%S')
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=datetime.timezone.utc)
                rem = max(0, int((exp_dt - now_utc).total_seconds()))
            except Exception:
                rem = 0
        r['remaining_seconds'] = rem
        r['is_active'] = (status == 'active' and rem > 0)
        if rem <= 0 and status == 'active':
            r['status'] = 'expired'
            r['is_active'] = False

    why = [
        {'icon': 'shield', 'title': '100% Dedicated Line', 'text': 'Guaranteed ownership of the phone number for the entire rental window.'},
        {'icon': 'refresh', 'title': 'Unlimited OTP Codes', 'text': 'Receive multiple SMS verification codes anytime without paying per SMS.'},
        {'icon': 'globe', 'title': 'All-in-One Route', 'text': 'Universal Number option supports all 2,000+ services on the same line.'},
        {'icon': 'clock', 'title': 'Flexible Periods', 'text': 'Choose 3, 7, 14, or 30 days based on your project requirements.'},
    ]

    return render_template(
        'sims/rentals.html',
        catalog=catalog,
        rentals=rentals_list,
        wallet=wallet,
        why=why,
        user=user
    )


@sims_bp.route('/otp-history')
def otp_history():
    """OTP History  -  every verification code received across numbers."""
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    # Build an OTP feed from orders that have received codes.
    history = DBService.get_orders(user['id'])
    services = sorted(list({h.get('service_name') for h in history if h.get('service_name')}))
    return render_template('sims/otp_history.html', history=history, services=services, user=user)


