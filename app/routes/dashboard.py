"""Authenticated dashboard overview."""
from flask import Blueprint, render_template, session
from app.services.supabase_client import mock_db
from app.services.sim_provider import SIMProviderService

dashboard_bp = Blueprint('dashboard', __name__)


def _ensure_demo_user():
    """Seed a demo session so the dashboard is previewable without a real login."""
    if 'user' not in session:
        session['user'] = {
            'id': 'demo-user-id',
            'email': 'tunde@tgsims.com',
            'full_name': 'Tunde Komolafe',
            'first_name': 'Tunde',
            'role': 'user',
            'avatar': None,
        }
    return session['user']


@dashboard_bp.route('/dashboard')
def index():
    user = _ensure_demo_user()
    user_id = user['id']

    wallet = mock_db.wallets.get(user_id, {'balance': 45.50, 'currency': 'USD'})

    # Recent verifications feed for the dashboard table.
    recent = mock_db.sim_orders[:5]

    stats = {
        'wallet_balance_usd': wallet['balance'],
        'today_spending_usd': 0.28,
        'numbers_today': 3,
        'total_numbers': 1204,
        'wallet_delta_usd': 1.56,
        'total_delta_pct': 12,
    }

    # Activity series for the Activity Overview chart. Each point carries a
    # total height (0-100) and the completed portion (<= total) so the bars
    # render two-tone (purchased vs completed), matching the Figma.
    activity = {
        '7d': [
            {'label': 'Mon', 'total': 42, 'done': 30},
            {'label': 'Tue', 'total': 58, 'done': 44},
            {'label': 'Wed', 'total': 35, 'done': 22},
            {'label': 'Thu', 'total': 74, 'done': 60},
            {'label': 'Fri', 'total': 61, 'done': 40},
            {'label': 'Sat', 'total': 88, 'done': 71},
            {'label': 'Sun', 'total': 52, 'done': 38},
        ],
        '30d': [
            {'label': 'W1', 'total': 48, 'done': 33},
            {'label': 'W2', 'total': 63, 'done': 47},
            {'label': 'W3', 'total': 41, 'done': 28},
            {'label': 'W4', 'total': 78, 'done': 62},
            {'label': 'W5', 'total': 55, 'done': 39},
            {'label': 'W6', 'total': 90, 'done': 72},
            {'label': 'W7', 'total': 67, 'done': 50},
            {'label': 'W8', 'total': 72, 'done': 58},
        ],
    }

    return render_template(
        'dashboard/index.html',
        stats=stats,
        recent=recent,
        activity=activity,
        catalog=SIMProviderService.get_catalog(),
        user=user,
    )
