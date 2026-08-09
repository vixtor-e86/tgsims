"""Wallet & billing routes."""
from flask import Blueprint, render_template, session, redirect, url_for
from app.services.supabase_client import mock_db

wallet_bp = Blueprint('wallet', __name__, url_prefix='/wallet')


def _require_user():
    return session.get('user')


@wallet_bp.route('/')
def index():
    """Wallet overview  -  balance, payment methods, recent activity."""
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    wallet = mock_db.wallets.get(user['id'], {'balance': 45.50, 'currency': 'USD'})
    transactions = [t for t in mock_db.transactions if t['user_id'] == user['id']]

    methods = [
        {'id': 'card', 'label': 'Visa/Mastercard', 'note': 'Instant processing', 'icon': 'card'},
        {'id': 'crypto', 'label': 'USDT / Crypto', 'note': 'TRC20, ERC20', 'icon': 'crypto'},
        {'id': 'bank', 'label': 'Bank Transfer', 'note': 'Immediately', 'icon': 'bank'},
    ]

    return render_template('wallet/index.html', wallet=wallet,
                           transactions=transactions, methods=methods, user=user)


@wallet_bp.route('/fund')
def fund():
    """Fund Your Wallet  -  add cash flow."""
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    wallet = mock_db.wallets.get(user['id'], {'balance': 45.50, 'currency': 'USD'})
    # Presets are round Naira amounts (canonical USD derived in the template).
    presets_ngn = [1000, 5000, 10000, 25000]

    methods = [
        {'id': 'card', 'label': 'Credit / Debit Card', 'note': 'Visa, Mastercard', 'icon': 'card'},
        {'id': 'crypto', 'label': 'Cryptocurrency', 'note': 'BTC, USDT, ETH', 'icon': 'crypto'},
        {'id': 'bank', 'label': 'Bank Transfer', 'note': 'Local / Wire', 'icon': 'bank'},
    ]
    fee_rate = 0.015  # 1.5% processing fee

    return render_template('wallet/fund.html', wallet=wallet,
                           presets_ngn=presets_ngn, methods=methods,
                           fee_rate=fee_rate, user=user)
