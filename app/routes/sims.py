"""Virtual number routes: buy a number, view orders, and OTP history."""
from flask import Blueprint, render_template, session, redirect, url_for
from app.services.sim_provider import SIMProviderService
from app.services.supabase_client import mock_db

sims_bp = Blueprint('sims', __name__, url_prefix='/sims')


def _require_user():
    return session.get('user')


@sims_bp.route('/store')
def store():
    """Buy a Virtual Number  -  country + service selection."""
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    catalog = SIMProviderService.get_catalog()
    wallet = mock_db.wallets.get(user['id'], {'balance': 45.50, 'currency': 'USD'})

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
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    orders = [o for o in mock_db.sim_orders if o['user_id'] == user['id']]
    return render_template('sims/orders.html', orders=orders, user=user)


@sims_bp.route('/otp-history')
def otp_history():
    """OTP History  -  every verification code received across numbers."""
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    # Build an OTP feed from orders that have received codes.
    history = [o for o in mock_db.sim_orders if o['user_id'] == user['id']]
    return render_template('sims/otp_history.html', history=history, user=user)
