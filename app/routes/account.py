"""Account-area routes: settings, support, referral."""
from flask import Blueprint, render_template, session, redirect, url_for

account_bp = Blueprint('account', __name__)


def _require_user():
    return session.get('user')


@account_bp.route('/settings')
def settings():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    profile = {
        'full_name': user.get('full_name', 'Tunde Komolafe'),
        'email': user.get('email', 'tgconceptt@gmail.com'),
        'phone': '07047886371',
        'country': 'Nigeria',
    }
    return render_template('account/settings.html', profile=profile, user=user)


@account_bp.route('/support')
def support():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    topics = [
        {'icon': 'rocket', 'title': 'Getting Started', 'text': 'Account creation, basics, and platform overview.'},
        {'icon': 'sim', 'title': 'eSIM Setup', 'text': 'Installation guides for iOS, Android, and specific carriers.'},
        {'icon': 'chat', 'title': 'Virtual SMS', 'text': 'Troubleshooting reception issues and sender IDs.'},
        {'icon': 'wallet', 'title': 'Billing & Wallet', 'text': 'Invoices, payment methods, and balance top-ups.'},
        {'icon': 'wrench', 'title': 'Troubleshooting', 'text': 'Resolve common errors, connectivity drops, and delivery delays swiftly.'},
    ]
    tickets = [
        {'id': 'TK-8821', 'subject': 'SMS activation issue', 'status': 'resolved', 'updated': 'Oct 24, 2026'},
        {'id': 'TK-8845', 'subject': 'Wallet refund request', 'status': 'open', 'updated': 'Oct 26, 2026'},
        {'id': 'TK-8902', 'subject': 'eSIM activation help', 'status': 'pending', 'updated': 'Oct 27, 2026'},
    ]
    channels = [
        {'icon': 'chat', 'title': 'Live Chat', 'text': 'Talk to our support team directly. Available 24/7.', 'cta': 'Start Chat'},
        {'icon': 'mail', 'title': 'Email Support', 'text': 'Detailed inquiries and technical escalations.', 'cta': 'Send Email'},
        {'icon': 'users', 'title': 'Telegram Community', 'text': 'Join fellow users for tips, updates, and community help.', 'cta': 'Join Telegram'},
    ]
    return render_template('account/support.html', topics=topics, tickets=tickets,
                           channels=channels, user=user)


@account_bp.route('/referral')
def referral():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))
    referral = {
        'code': 'TUNDE500',
        'link': 'https://tgsims.com/r/TUNDE500',
        'earned_usd': 12.50,
        'invited': 8,
        'converted': 5,
    }
    return render_template('account/referral.html', referral=referral, user=user)
