"""Authenticated dashboard overview."""
from flask import Blueprint, render_template, session, redirect, url_for, request
from app.services.db_service import DBService
from app.services.sim_provider import SIMProviderService
import datetime

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.before_request
def require_login():
    """Ensure user is authenticated before accessing the dashboard."""
    user = session.get('user')
    if not user or not isinstance(user, dict):
        return redirect(url_for('auth.login', next=request.path))


@dashboard_bp.route('/dashboard')
def index():
    user = session.get('user')
    if not user or not isinstance(user, dict):
        return redirect(url_for('auth.login', next=request.path))

    user_id = user['id']

    wallet = DBService.get_wallet(user_id)
    orders = DBService.get_orders(user_id)
    recent = orders[:5]

    today_str = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
    today_orders = [o for o in orders if str(o.get('created_at', '')).startswith(today_str)]
    today_spending = sum(float(o.get('price', o.get('user_cost', 0.0))) for o in today_orders)

    stats = {
        'wallet_balance_usd': wallet.get('balance', 0.00),
        'today_spending_usd': round(today_spending, 2),
        'numbers_today': len(today_orders),
        'total_numbers': len(orders),
        'wallet_delta_usd': round(wallet.get('balance', 0.00), 2),
        'total_delta_pct': 100 if len(orders) > 0 else 0,
    }

    return render_template(
        'dashboard/index.html',
        stats=stats,
        recent=recent,
        catalog=SIMProviderService.get_catalog(),
        user=user,
    )
