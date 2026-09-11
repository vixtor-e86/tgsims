
from flask import Flask, session, request, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from app.config import Config

# Single source of truth for USD->NGN display conversion (frontend mirrors this).
NGN_PER_USD = 1600


def create_app(config_class=Config):
    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)
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
    def dev_gate_protect():
        """Ensure visitor has entered access password before viewing any page."""
        # Whitelist static assets, favicon, and the unlock page
        if request.path.startswith('/static') or request.path == '/favicon.ico' or request.endpoint == 'static':
            return None
        if request.endpoint == 'public.site_unlock':
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
            return {
                'NGN_PER_USD': ngn_rate,
                'BRAND': 'Tgsims',
                'current_user': user if isinstance(user, dict) else None,
                'wallet_balance_usd': wallet_balance_usd,
            }
        except Exception:
            return {
                'NGN_PER_USD': 1600.00,
                'BRAND': 'Tgsims',
                'current_user': None,
                'wallet_balance_usd': 0.00,
            }

    @app.errorhandler(500)
    def handle_500(e):
        return f"<h3>Internal Server Error</h3><p>{e}</p>", 500

    return app
