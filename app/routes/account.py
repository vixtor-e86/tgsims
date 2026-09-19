"""Account-area routes: settings, support, referral."""
from flask import Blueprint, render_template, session, redirect, url_for, request, flash, jsonify


account_bp = Blueprint('account', __name__)


def _require_user():
    return session.get('user')


@account_bp.route('/settings')
@account_bp.route('/account/settings')
def settings():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    profile = {
        'full_name': user.get('full_name', 'Tunde Komolafe'),
        'email': user.get('email', 'tgconceptt@gmail.com'),
        'phone': '08058098494',
        'country': 'Nigeria',
    }
    return render_template('account/settings.html', profile=profile, user=user)


@account_bp.route('/support')
@account_bp.route('/account/support')
def support():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login', next=url_for('account.support')))

    from app.services.db_service import DBService
    user_id = user.get('id', 'demo-user-id')
    tickets = DBService.get_user_tickets(user_id)

    topics = [
        {'icon': 'rocket', 'title': 'Getting Started', 'text': 'Account creation, basics, and platform overview.'},
        {'icon': 'sim', 'title': 'eSIM Setup', 'text': 'Installation guides for iOS, Android, and specific carriers.'},
        {'icon': 'chat', 'title': 'Virtual SMS', 'text': 'Troubleshooting reception issues and sender IDs.'},
        {'icon': 'wallet', 'title': 'Billing & Wallet', 'text': 'Invoices, payment methods, and balance top-ups.'},
        {'icon': 'wrench', 'title': 'Troubleshooting', 'text': 'Resolve common errors, connectivity drops, and delivery delays swiftly.'},
    ]
    channels = [
        {'icon': 'chat', 'title': 'Live Chat', 'text': 'Talk to our support team directly. Available 24/7.', 'cta': 'Start Chat', 'action': 'chat'},
        {'icon': 'phone', 'title': 'WhatsApp Support', 'text': 'Direct WhatsApp assistance at 08058098494 for instant response.', 'cta': 'Chat on WhatsApp', 'href': 'https://wa.me/2348058098494'},
        {'icon': 'send', 'title': 'Telegram Support', 'text': 'Chat with our official Telegram support at t.me/tgsimss.', 'cta': 'Open Telegram', 'href': 'https://t.me/tgsimss'},
        {'icon': 'mail', 'title': 'Email Support', 'text': 'Detailed inquiries and escalations: tgsimsverify@gmail.com', 'cta': 'Send Email', 'href': 'mailto:tgsimsverify@gmail.com'},
    ]
    return render_template('account/support.html', topics=topics, tickets=tickets,
                           channels=channels, user=user)


@account_bp.route('/referral')
@account_bp.route('/account/referral')
def referral():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login', next=url_for('account.referral')))

    from app.services.db_service import DBService
    user_id = user.get('id', 'demo-user-id')
    referral_data = DBService.get_referral_details(user_id, host_url=request.host_url)
    wallet = DBService.get_wallet(user_id)

    return render_template('account/referral.html', referral=referral_data, wallet=wallet, user=user)


@account_bp.route('/referral/redeem', methods=['POST'])
@account_bp.route('/account/referral/redeem', methods=['POST'])
def redeem_referral():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    from app.services.db_service import DBService
    user_id = user.get('id', 'demo-user-id')

    amount_raw = request.form.get('amount', '').strip()
    amount = None
    if amount_raw:
        try:
            amount = float(amount_raw)
        except ValueError:
            flash('Please enter a valid numeric amount to redeem.', 'error')
            return redirect(url_for('account.referral'))

    res = DBService.redeem_referral_balance(user_id, amount=amount)
    if res.get('success'):
        flash(f"Success! ${res.get('amount', 0):.2f} has been transferred to your main wallet balance.", 'success')
    else:
        flash(res.get('message', 'Failed to redeem referral balance.'), 'error')

    return redirect(url_for('account.referral'))

