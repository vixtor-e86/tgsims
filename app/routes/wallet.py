"""Wallet & billing routes."""
from flask import Blueprint, render_template, session, redirect, url_for
from app.services.db_service import DBService
from app.services.oxapay_service import OXAPayService
from app.services.squad_service import SquadService
from app.services.korapay_service import KorapayService

wallet_bp = Blueprint('wallet', __name__, url_prefix='/wallet')


def _require_user():
    return session.get('user')


@wallet_bp.route('/')
def index():
    """Wallet overview  -  balance, virtual account, recent activity."""
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    wallet = DBService.get_wallet(user['id'])
    transactions = DBService.get_transactions(user['id'])

    # Dedicated visual accounts hidden until Korapay merchant approval is finalized
    methods = [
        {'id': 'card', 'label': 'Bank Transfer / Card', 'note': 'Instant Bank Transfer & Card', 'icon': 'card'},
        {'id': 'crypto', 'label': 'Cryptocurrency', 'note': 'USDT, BTC, ETH & more', 'icon': 'crypto'},
    ]

    return render_template('wallet/index.html', wallet=wallet,
                           transactions=transactions, methods=methods,
                           user=user,
                           virtual_account=None,
                           squad_account=None,
                           korapay_active=False,
                           squad_active=SquadService.is_configured())


@wallet_bp.route('/fund')
def fund():
    """Fund Your Wallet  -  add cash flow."""
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    wallet = DBService.get_wallet(user['id'])
    presets_ngn = [1000, 5000, 10000, 25000]

    # Dedicated visual accounts hidden until Korapay merchant approval is finalized
    # Users only have access to Bank Transfer / Card (Squad) and Cryptocurrency (OXAPay)
    methods = [
        {'id': 'card', 'label': 'Bank Transfer / Card', 'note': 'Squad Checkout (Instant Bank Transfer, Card & USSD)', 'icon': 'card'},
        {'id': 'crypto', 'label': 'Cryptocurrency', 'note': 'Instant crypto deposit via OXAPay ($1 min)', 'icon': 'crypto'},
    ]

    fee_rate = 0.015  # 1.5% processing fee for card
    from app.services.settings_service import SettingsService
    settings = SettingsService.get_settings()

    # Crypto gateway info (OXAPay)
    crypto_currencies = OXAPayService.SUPPORTED_CURRENCIES
    crypto_active     = OXAPayService.is_configured()
    crypto_min        = OXAPayService.MIN_DEPOSIT_USD

    # Squad info
    squad_active     = SquadService.is_configured()
    squad_public_key = SquadService.get_public_key() if squad_active else ''

    return render_template('wallet/fund.html', wallet=wallet,
                           presets_ngn=presets_ngn, methods=methods,
                           fee_rate=fee_rate, user=user,
                           settings=settings,
                           crypto_currencies=crypto_currencies,
                           crypto_active=crypto_active,
                           crypto_min=crypto_min,
                           squad_active=squad_active,
                           squad_public_key=squad_public_key,
                           korapay_active=False,
                           supported_banks=[],
                           virtual_account=None,
                           squad_account=None,
                           has_virtual_account=False,
                           nowpayments_active=crypto_active)

