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
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    orders = DBService.get_orders(user['id'])
    now_utc = datetime.datetime.now(datetime.timezone.utc)

    for o in orders:
        status = str(o.get('status', '')).lower()
        has_code = bool(o.get('sms_code'))
        is_active = status in ('active', 'pending') and not has_code
        o['is_active_sim'] = is_active

        remaining = 300
        if o.get('created_at'):
            try:
                cat_str = str(o['created_at']).replace('Z', '+00:00')
                try:
                    c_dt = datetime.datetime.fromisoformat(cat_str)
                except ValueError:
                    c_dt = datetime.datetime.strptime(cat_str, '%Y-%m-%d %H:%M:%S')
                if c_dt.tzinfo is None:
                    c_dt = c_dt.replace(tzinfo=datetime.timezone.utc)
                elapsed = (now_utc - c_dt).total_seconds()
                remaining = max(0, int(300 - elapsed))
            except Exception:
                remaining = 0

        o['countdown_seconds'] = remaining

        # If active order exceeded 5 minutes, trigger automatic refund immediately
        if is_active and remaining <= 0:
            try:
                prov_id = o.get('provider_order_id')
                if prov_id and not str(prov_id).startswith('SIM-') and not str(prov_id).startswith('USCA-'):
                    SIMProviderService.cancel_order(str(prov_id))
                DBService.refund_order(o.get('id') or o.get('order_reference'), user['id'], reason="Auto-refunded: SMS timeout (5 mins)")
                o['status'] = 'refunded'
                o['is_active_sim'] = False
            except Exception as e:
                print(f"[my_sims] Auto-refund on page load error: {e}")

    return render_template('sims/orders.html', orders=orders, user=user)


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

