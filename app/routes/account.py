"""Account-area routes: settings, support, referral."""
from flask import Blueprint, render_template, session, redirect, url_for, request, flash, jsonify


account_bp = Blueprint('account', __name__)


def _require_user():
    return session.get('user')


@account_bp.route('/settings', methods=['GET', 'POST'])
@account_bp.route('/account/settings', methods=['GET', 'POST'])
def settings():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login', next=url_for('account.settings')))

    from app.services.supabase_client import get_supabase_admin, create_supabase_client
    import datetime
    admin = get_supabase_admin()
    user_id = user.get('id')

    # Load fresh profile from database if available
    db_profile = {}
    if admin and user_id and user_id != 'demo-user-id':
        try:
            p_res = admin.table('profiles').select('*').eq('id', user_id).limit(1).execute()
            if p_res.data:
                db_profile = p_res.data[0]
        except Exception as e:
            print(f"[Settings] Profile fetch error: {e}")

    active_tab = request.args.get('tab', 'profile')

    if request.method == 'POST':
        action = request.form.get('action', 'update_profile')

        if action == 'update_profile':
            active_tab = 'profile'
            new_username = (request.form.get('username') or '').strip().lower()
            if not new_username:
                flash('Username cannot be empty.', 'error')
            elif len(new_username) < 3 or len(new_username) > 30:
                flash('Username must be between 3 and 30 characters.', 'error')
            elif not new_username.replace('_', '').isalnum():
                flash('Username can only contain letters, numbers, and underscores.', 'error')
            else:
                # Check uniqueness if username changed
                cur_username = (db_profile.get('username') or user.get('username') or '').lower()
                is_taken = False
                if new_username != cur_username and admin and user_id != 'demo-user-id':
                    try:
                        chk = admin.table('profiles').select('id').eq('username', new_username).neq('id', user_id).limit(1).execute()
                        if chk.data and len(chk.data) > 0:
                            is_taken = True
                    except Exception:
                        pass

                if is_taken:
                    flash(f'The username "@{new_username}" is already taken. Please choose another.', 'error')
                else:
                    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    if admin and user_id and user_id != 'demo-user-id':
                        try:
                            admin.table('profiles').update({
                                'username': new_username,
                                'full_name': new_username,
                                'updated_at': now_iso
                            }).eq('id', user_id).execute()
                        except Exception as e:
                            print(f"[Settings] Update profile error: {e}")

                    # Update session data
                    user['username'] = new_username
                    user['full_name'] = new_username
                    user['first_name'] = new_username
                    session['user'] = user
                    session.modified = True
                    flash('Profile updated successfully!', 'success')
                    return redirect(url_for('account.settings', tab='profile'))

        elif action == 'update_password':
            active_tab = 'security'
            current_pass = request.form.get('current_password', '').strip()
            new_pass = request.form.get('new_password', '').strip()
            conf_pass = request.form.get('confirm_password', '').strip()

            if not current_pass or not new_pass or not conf_pass:
                flash('Please fill in all password fields.', 'error')
            elif new_pass != conf_pass:
                flash('New passwords do not match. Please re-enter them carefully.', 'error')
            elif len(new_pass) < 6:
                flash('New password must be at least 6 characters long.', 'error')
            else:
                user_email = user.get('email')
                password_verified = False
                if user_id == 'demo-user-id':
                    password_verified = True
                else:
                    supabase = create_supabase_client()
                    if supabase and user_email:
                        try:
                            chk_auth = supabase.auth.sign_in_with_password({
                                'email': user_email,
                                'password': current_pass
                            })
                            if chk_auth.user:
                                password_verified = True
                        except Exception as auth_err:
                            print(f"[Settings] Password verification error: {auth_err}")
                            password_verified = False

                if not password_verified:
                    flash("Current password is incorrect. If you don't know your current password, please reset it from the login page.", 'error')
                else:
                    updated_ok = False
                    if user_id == 'demo-user-id':
                        updated_ok = True
                    elif admin:
                        try:
                            admin.auth.admin.update_user_by_id(user_id, {'password': new_pass})
                            updated_ok = True
                        except Exception as e:
                            print(f"[Settings] Supabase password update error: {e}")
                            flash(f'Failed to update password: {e}', 'error')

                    if updated_ok:
                        flash('Your password has been changed successfully!', 'success')
                        return redirect(url_for('account.settings', tab='security'))

    profile = {
        'username': db_profile.get('username') or user.get('username', 'user'),
        'email': db_profile.get('email') or user.get('email', ''),
    }
    return render_template('account/settings.html', profile=profile, user=user, active_tab=active_tab)


@account_bp.route('/support')
@account_bp.route('/account/support')
def support():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login', next=url_for('account.support')))

    from app.services.db_service import DBService
    user_id = user.get('id', 'demo-user-id')
    tickets = DBService.get_user_tickets(user_id)

    faqs = [
        {
            'category': 'Wallet & Deposits',
            'q': 'Can I withdraw or cash out money deposited into my Tgsims wallet?',
            'a': 'No. In accordance with our platform terms, all funds deposited into your account (via Bank Transfer, Card, or Crypto) are digital prepaid service credits designated exclusively for purchasing virtual numbers and SMS verifications. Money deposited into your account cannot be withdrawn, refunded to a bank account, or cashed out. Funds remain safely stored in your balance with no expiration date until spent.'
        },
        {
            'category': 'Refund Policy',
            'q': "What happens if my number doesn't receive a verification SMS code?",
            'a': 'You are never charged for a missed code. If an SMS does not arrive within the active countdown window, or if you cancel an active order after 3 minutes without receiving a code, 100% of the purchase price is automatically and immediately refunded back to your internal Tgsims wallet balance so you can try another number.'
        },
        {
            'category': 'Referral Program',
            'q': 'How does the 5% Referral Program and Referral Wallet work?',
            'a': 'Every user has a unique 5-character referral code (found on your Referral Program page). When friends sign up with your code or link, you earn a 5% commission on all their spendings. Your earnings accumulate in your Referral Wallet. Once your accumulated referral earnings reach $1.00 USD, you can withdraw them directly into your main wallet balance to spend on verifications!'
        },
        {
            'category': 'Numbers & Carrier Routing',
            'q': 'Are these real cellular numbers? Will they work on WhatsApp and Telegram?',
            'a': 'Yes. We supply genuine Non-VoIP carrier lines that bypass strict VoIP filters. For WhatsApp, Telegram, Google, and banking services, we recommend selecting our "Buy US Number" dedicated cellular lines for guaranteed unbanned status.'
        },
        {
            'category': 'Activation Lifespan',
            'q': 'How long does a verification number stay active?',
            'a': 'Single-use verification sessions stay active for 15 to 20 minutes from the time of order. Once your SMS verification code is received or the session expires, the line is closed. For US numbers, you can also request re-activations or extra codes on the same line if needed.'
        },
        {
            'category': 'Wallet & Deposits',
            'q': 'How quickly do wallet top-ups reflect?',
            'a': 'Bank transfers via dedicated virtual accounts, card payments, and cryptocurrency deposits (USDT, BTC) are automated and credited to your wallet balance within seconds of transaction confirmation.'
        },
        {
            'category': 'Support Desk',
            'q': 'How do I speak to a real human agent?',
            'a': 'Click "Create New Ticket" or "Start Chat" below for our 24/7 in-app ticket desk, or message us directly on WhatsApp at +234 805 809 8494 or Telegram at t.me/tgsimss.'
        }
    ]
    channels = [
        {'icon': 'chat', 'title': 'Live Chat', 'text': 'Talk to our support team directly. Available 24/7.', 'cta': 'Start Chat', 'action': 'chat'},
        {'icon': 'phone', 'title': 'WhatsApp Support', 'text': 'Direct WhatsApp assistance at 08058098494 for instant response.', 'cta': 'Chat on WhatsApp', 'href': 'https://wa.me/2348058098494'},
        {'icon': 'send', 'title': 'Telegram Support', 'text': 'Chat with our official Telegram support at t.me/tgsimss.', 'cta': 'Open Telegram', 'href': 'https://t.me/tgsimss'},
        {'icon': 'mail', 'title': 'Email Support', 'text': 'Detailed inquiries and escalations: tgsimsverify@gmail.com', 'cta': 'Send Email', 'href': 'mailto:tgsimsverify@gmail.com'},
    ]
    return render_template('account/support.html', faqs=faqs, tickets=tickets,
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

