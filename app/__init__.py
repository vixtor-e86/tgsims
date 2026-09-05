
from flask import Flask, session, request, redirect, url_for
from app.config import Config

# Single source of truth for USD->NGN display conversion (frontend mirrors this).
NGN_PER_USD = 1600


def create_app(config_class=Config):
    app = Flask(__name__)
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

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(sims_bp)
    app.register_blueprint(wallet_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(api_bp)

    @app.before_request
    def dev_gate_protect():
        """Ensure visitor has entered access password before viewing any page."""
        # Whitelist static assets, favicon, and the unlock page
        if request.path.startswith('/static') or request.path == '/favicon.ico':
            return None
        if request.endpoint == 'public.site_unlock':
            return None

        # Check if site is unlocked in this browser session
        if not session.get('site_unlocked'):
            next_url = request.full_path if request.query_string else request.path
            return redirect(url_for('public.site_unlock', next=next_url))

    @app.context_processor
    def inject_globals():
        """Expose shared values to every template (drives the app-shell topbar)."""
        try:
            from app.services.supabase_client import mock_db
            user = session.get('user')
            wallet_balance_usd = 45.50
            if isinstance(user, dict) and 'id' in user:
                wallet_data = mock_db.wallets.get(user['id'], {'balance': 45.50})
                if isinstance(wallet_data, dict):
                    wallet_balance_usd = wallet_data.get('balance', 45.50)
            return {
                'NGN_PER_USD': NGN_PER_USD,
                'BRAND': 'Tgsims',
                'current_user': user if isinstance(user, dict) else None,
                'wallet_balance_usd': wallet_balance_usd,
            }
        except Exception:
            return {
                'NGN_PER_USD': NGN_PER_USD,
                'BRAND': 'Tgsims',
                'current_user': None,
                'wallet_balance_usd': 45.50,
            }

    @app.errorhandler(500)
    def handle_500(e):
        return f"<h3>Internal Server Error</h3><p>{e}</p>", 500

    return app
