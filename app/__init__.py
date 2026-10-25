
import os
from flask import Flask, session, request, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from app.config import Config

# Single source of truth for USD->NGN display conversion (frontend mirrors this).
NGN_PER_USD = 1600


def create_app(config_class=Config):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, 'templates'),
        static_folder=os.path.join(base_dir, 'static')
    )
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
    app.config.from_object(config_class)
    app.config['SESSION_PERMANENT'] = False

    # Register Blueprints
    from app.routes.public import public_bp
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.sims import sims_bp
    from app.routes.wallet import wallet_bp
    from app.routes.account import account_bp
    from app.routes.api import api_bp
    from app.routes.admin import admin_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(sims_bp)
    app.register_blueprint(wallet_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)

    @app.before_request
    def capture_referral_code():
        """Capture incoming referral code from query param and preserve in session."""
        ref = request.args.get('ref')
        if ref and len(ref.strip()) <= 15:
            session['referral_code'] = ref.strip().upper()

    @app.before_request
    def dev_gate_protect():
        """Optional development gate  -  disabled by default so visitors land directly on landing page."""
        if not app.config.get('SITE_LOCK_ENABLED', False):
            return None

        # Whitelist static assets, favicon, the unlock page, and payment webhooks
        if request.path.startswith('/static') or request.path == '/favicon.ico' or request.endpoint == 'static':
            return None
        if request.endpoint == 'public.site_unlock':
            return None
        if request.path.startswith('/api/payments/crypto/webhook') or request.path.startswith('/api/payments/nowpayments'):
            return None

        # Check if site is unlocked in this browser session
        if not session.get('site_unlocked'):
            next_url = request.full_path if request.query_string else request.path
            return redirect(url_for('public.site_unlock', next=next_url))

    @app.before_request
    def sync_user_role():
        """Ensure logged-in user's role is always fresh from Supabase on every page refresh."""
        if request.path.startswith('/static') or request.path == '/favicon.ico':
            return None

        user = session.get('user')
        if isinstance(user, dict) and user.get('id'):
            from app.services.supabase_client import get_supabase_admin
            admin = get_supabase_admin()
            if admin:
                try:
                    res = admin.table('profiles').select('role').eq('id', user['id']).limit(1).execute()
                    if res.data and len(res.data) > 0:
                        fresh_role = res.data[0].get('role', 'user')
                        if user.get('role') != fresh_role:
                            session['user']['role'] = fresh_role
                            session.modified = True
                except Exception:
                    pass

    # Universal Currency Reconciliation Filters
    from app.services.currency_service import reconcile_ngn_amount, format_ngn, clean_ngn

    @app.template_filter('clean_ngn')
    def filter_clean_ngn(usd, rate=None):
        return clean_ngn(usd, rate)

    @app.template_filter('format_ngn')
    def filter_format_ngn(usd, rate=None):
        return format_ngn(usd, rate)

    @app.template_filter('clean_decimal')
    def filter_clean_decimal(val, min_decimals=2, max_decimals=4):
        if val is None:
            return ""
        try:
            f = float(val)
        except (ValueError, TypeError):
            return str(val)
        if abs(round(f, min_decimals) - round(f, max_decimals)) > 1e-5:
            return f"{f:.{max_decimals}f}".rstrip('0').rstrip('.')
        return f"{f:.{min_decimals}f}"

    @app.template_filter('format_usd')
    def filter_format_usd(val, min_decimals=2, max_decimals=4):
        formatted = filter_clean_decimal(val, min_decimals, max_decimals)
        return f"${formatted}" if formatted else "$0.00"

    @app.context_processor
    def inject_globals():
        """Expose shared values to every template (drives the app-shell topbar)."""
        try:
            from app.services.db_service import DBService
            from app.services.settings_service import SettingsService
            user = session.get('user')
            wallet_balance_usd = 0.00
            if isinstance(user, dict) and 'id' in user:
                wallet = DBService.get_wallet(user['id'])
                wallet_balance_usd = float(wallet.get('balance', 0.00))
            ngn_rate = SettingsService.get_usd_ngn_rate()
            react_fee = SettingsService.get_reactivation_fee()
            admin_support_badge = None
            if isinstance(user, dict) and user.get('role') in ('admin', 'support'):
                try:
                    admin_support_badge = DBService.get_admin_support_stats()
                except Exception:
                    admin_support_badge = None

            return {
                'NGN_PER_USD': ngn_rate,
                'REACTIVATION_FEE_USD': react_fee,
                'BRAND': 'Tgsims',
                'current_user': user if isinstance(user, dict) else None,
                'wallet_balance_usd': wallet_balance_usd,
                'clean_ngn': clean_ngn,
                'format_ngn': format_ngn,
                'clean_decimal': filter_clean_decimal,
                'format_usd': filter_format_usd,
                'admin_support_badge': admin_support_badge,
            }
        except Exception:
            return {
                'NGN_PER_USD': 1600.00,
                'REACTIVATION_FEE_USD': 1.00,
                'BRAND': 'Tgsims',
                'current_user': None,
                'wallet_balance_usd': 0.00,
                'clean_ngn': clean_ngn,
                'format_ngn': format_ngn,
                'clean_decimal': filter_clean_decimal,
                'format_usd': filter_format_usd,
            }

    @app.errorhandler(404)
    def handle_404(e):
        from app.routes.public import landing
        if request.path in ('/api/index', '/api/index.py', '/api', '/api/'):
            return landing()
        return "<h3>404 Not Found</h3><p>The page you requested does not exist.</p>", 404

    @app.errorhandler(500)
    def handle_500(e):
        return "<h3>500 Internal Server Error</h3><p>An unexpected error occurred. Please try again later.</p>", 500

    return app
