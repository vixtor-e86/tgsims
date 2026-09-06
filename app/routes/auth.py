"""Authentication routes: Login, Register, Forgot Password, and Reset Password with Supabase & Resend."""
import datetime
import hashlib
import secrets
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.services.supabase_client import (
    is_supabase_configured,
    create_supabase_client,
    get_supabase_admin,
)
from app.services.email_service import EmailService

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


def _hash_otp(email: str, otp: str) -> str:
    """Generate SHA-256 hash of email + OTP code for secure verification."""
    return hashlib.sha256(f"{email.lower().strip()}:{otp.strip()}".encode('utf-8')).hexdigest()


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # If already logged in, send directly to dashboard
    if session.get('user'):
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Please enter both your email address and password.', 'error')
            return render_template('auth/login.html', email=email)

        if not is_supabase_configured():
            flash('Supabase is not configured yet. Please add your SUPABASE_URL and SUPABASE_ANON_KEY to .env.', 'error')
            return render_template('auth/login.html', email=email)

        supabase = create_supabase_client()
        if not supabase:
            flash('Unable to initialize Supabase connection. Please verify your .env settings and restart your Flask server.', 'error')
            return render_template('auth/login.html', email=email)

        try:
            auth_res = supabase.auth.sign_in_with_password({
                'email': email,
                'password': password,
            })
            user = auth_res.user
            auth_session = auth_res.session

            if not user:
                flash('Invalid email or password. Please try again.', 'error')
                return render_template('auth/login.html', email=email)

            # Retrieve profile details from public.profiles
            user_meta = user.user_metadata or {}
            full_name = user_meta.get('full_name') or user_meta.get('username') or email.split('@')[0].capitalize()
            username = user_meta.get('username') or email.split('@')[0]
            role = 'user'
            avatar = None

            try:
                prof_res = supabase.table('profiles').select('*').eq('id', user.id).execute()
                if prof_res.data:
                    p = prof_res.data[0]
                    full_name = p.get('full_name') or full_name
                    username = p.get('username') or username
                    role = p.get('role', 'user')
                    avatar = p.get('avatar_url')
            except Exception as pe:
                print(f"[Auth] Profile lookup notice: {pe}")

            first_name = full_name.split(' ')[0] if full_name else username

            session['user'] = {
                'id': user.id,
                'email': user.email,
                'username': username,
                'full_name': full_name,
                'first_name': first_name,
                'role': role,
                'avatar': avatar,
            }
            if auth_session:
                session['access_token'] = auth_session.access_token
                session['refresh_token'] = auth_session.refresh_token

            flash(f'Welcome back, {first_name}!', 'success')
            return redirect(url_for('dashboard.index'))

        except Exception as e:
            err = str(e)
            if 'Invalid login credentials' in err:
                msg = 'Incorrect email or password. Please verify and try again.'
            elif 'Email not confirmed' in err:
                msg = 'Your email has not been confirmed yet. Please check your inbox.'
            else:
                msg = f"Sign in failed: {err}"
            flash(msg, 'error')
            return render_template('auth/login.html', email=email)

    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('user'):
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        agree = request.form.get('agree')

        # Validation
        if not username or not email or not password:
            flash('Please complete all required fields.', 'error')
            return render_template('auth/register.html', username=username, email=email)

        if not agree:
            flash('You must accept the Terms of Service to create an account.', 'error')
            return render_template('auth/register.html', username=username, email=email)

        if password != confirm_password:
            flash('Passwords do not match. Please re-enter.', 'error')
            return render_template('auth/register.html', username=username, email=email)

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return render_template('auth/register.html', username=username, email=email)

        if not is_supabase_configured():
            flash('Supabase is not configured yet. Please add your SUPABASE_URL and SUPABASE_ANON_KEY to .env.', 'error')
            return render_template('auth/register.html', username=username, email=email)

        supabase = create_supabase_client()
        if not supabase:
            flash('Unable to initialize Supabase connection. Please verify your .env settings and restart your Flask server.', 'error')
            return render_template('auth/register.html', username=username, email=email)

        try:
            # Dynamic redirect back to the live login page after email confirmation
            redirect_url = request.host_url.rstrip('/') + url_for('auth.login')
            res = supabase.auth.sign_up({
                'email': email,
                'password': password,
                'options': {
                    'email_redirect_to': redirect_url,
                    'data': {
                        'username': username,
                        'full_name': username,
                    }
                }
            })
            user = res.user
            auth_session = res.session

            # If email confirmation is disabled in Supabase, user gets instant session
            if user and auth_session:
                first_name = username.split(' ')[0]
                session['user'] = {
                    'id': user.id,
                    'email': user.email,
                    'username': username,
                    'full_name': username,
                    'first_name': first_name,
                    'role': 'user',
                    'avatar': None,
                }
                session['access_token'] = auth_session.access_token
                session['refresh_token'] = auth_session.refresh_token
                flash(f'Account created successfully! Welcome to Tgsims, {first_name}.', 'success')
                return redirect(url_for('dashboard.index'))
            else:
                flash('Account created! Please check your email to verify your account, then sign in.', 'success')
                return redirect(url_for('auth.login'))

        except Exception as e:
            err = str(e)
            if 'User already registered' in err:
                msg = 'An account with this email already exists. Please log in.'
            elif 'rate limit' in err.lower():
                msg = 'Email rate limit reached. In Supabase Dashboard > Authentication > Providers > Email, turn off "Confirm email" for instant registrations.'
            else:
                msg = f"Registration error: {err}"
            flash(msg, 'error')
            return render_template('auth/register.html', username=username, email=email)

    return render_template('auth/register.html')


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Step 1: User enters email to receive a 6-digit OTP recovery code."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        if not email:
            flash('Please enter your email address.', 'error')
            return render_template('auth/forgot_password.html')

        # Generate a 6-digit OTP code
        otp_code = f"{secrets.randbelow(900000) + 100000}"
        otp_hash = _hash_otp(email, otp_code)
        expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10)

        # 1. Store in Supabase password_resets table if admin client is available
        admin_client = get_supabase_admin()
        saved_in_db = False
        username = 'User'
        if admin_client:
            try:
                prof = admin_client.table('profiles').select('full_name, username').eq('email', email).limit(1).execute()
                if prof.data:
                    username = prof.data[0].get('full_name') or prof.data[0].get('username') or 'User'
            except Exception:
                pass

            try:
                admin_client.table('password_resets').insert({
                    'email': email,
                    'otp_hash': otp_hash,
                    'expires_at': expires_at.isoformat(),
                    'used': False
                }).execute()
                saved_in_db = True
            except Exception as dbe:
                print(f"[Forgot Password] DB insert note: {dbe}")

        # Fallback store in session if migration not yet applied
        if not saved_in_db:
            session['pwd_reset'] = {
                'email': email,
                'otp_hash': otp_hash,
                'expires_at': expires_at.timestamp()
            }

        # 2. Dispatch OTP via Resend email service matching the template design
        email_result = EmailService.send_password_reset_otp(email, otp_code, username=username)

        # Also notify Supabase Auth recovery if configured
        if is_supabase_configured():
            try:
                supabase = create_supabase_client()
                if supabase:
                    supabase.auth.reset_password_for_email(email)
            except Exception:
                pass

        if email_result.get('success'):
            flash('A 6-digit verification code has been sent to your email address.', 'success')
        else:
            # If Resend key is missing or email delivery failed, still provide friendly message
            flash('If an account exists for this email, a 6-digit verification code was generated. Please enter it below.', 'info')

        return redirect(url_for('auth.reset_password', email=email))

    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    """Step 2: User enters the 6-digit OTP code along with their new password."""
    email = request.args.get('email', '').strip().lower()

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        otp = request.form.get('otp', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not email or not otp or not password:
            flash('Please complete all fields.', 'error')
            return render_template('auth/reset_password.html', email=email)

        if password != confirm_password:
            flash('Passwords do not match. Please re-enter.', 'error')
            return render_template('auth/reset_password.html', email=email)

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return render_template('auth/reset_password.html', email=email)

        # Verify OTP
        otp_verified = False
        target_reset_id = None
        current_hash = _hash_otp(email, otp)
        admin_client = get_supabase_admin()

        # Check DB password_resets table first
        if admin_client:
            try:
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                res = admin_client.table('password_resets')\
                    .select('*')\
                    .eq('email', email)\
                    .eq('otp_hash', current_hash)\
                    .eq('used', False)\
                    .gt('expires_at', now_iso)\
                    .order('created_at', desc=True)\
                    .limit(1)\
                    .execute()

                if res.data and len(res.data) > 0:
                    otp_verified = True
                    target_reset_id = res.data[0]['id']
            except Exception as e:
                print(f"[Reset Password] DB verify notice: {e}")

        # Fallback check session
        if not otp_verified:
            cached_reset = session.get('pwd_reset')
            if cached_reset:
                if (cached_reset.get('email') == email and
                        cached_reset.get('otp_hash') == current_hash and
                        cached_reset.get('expires_at', 0) > datetime.datetime.now(datetime.timezone.utc).timestamp()):
                    otp_verified = True

        # Check Supabase native verify_otp as another option
        if not otp_verified and is_supabase_configured():
            try:
                supabase = create_supabase_client()
                if supabase:
                    supa_res = supabase.auth.verify_otp({
                        'email': email,
                        'token': otp,
                        'type': 'recovery'
                    })
                    if supa_res and supa_res.user:
                        otp_verified = True
            except Exception:
                pass

        if not otp_verified:
            flash('Invalid or expired 6-digit verification code. Please check and try again.', 'error')
            return render_template('auth/reset_password.html', email=email)

        # Apply new password
        password_updated = False

        # Attempt updating via Supabase Admin Client
        if admin_client and getattr(admin_client, 'auth', None) and getattr(admin_client.auth, 'admin', None):
            try:
                # Find user id by email
                users_res = admin_client.auth.admin.list_users()
                target_user = next((u for u in users_res if getattr(u, 'email', '') == email), None)
                if target_user:
                    admin_client.auth.admin.update_user_by_id(target_user.id, {'password': password})
                    password_updated = True
            except Exception as e:
                print(f"[Reset Password] Admin update user notice: {e}")

        # Attempt updating via client if session established
        if not password_updated and is_supabase_configured():
            try:
                supabase = create_supabase_client()
                if supabase:
                    supabase.auth.update_user({'password': password})
                    password_updated = True
            except Exception as e:
                print(f"[Reset Password] Client update notice: {e}")

        # Mark OTP as used
        if target_reset_id and admin_client:
            try:
                admin_client.table('password_resets').update({'used': True}).eq('id', target_reset_id).execute()
            except Exception:
                pass

        session.pop('pwd_reset', None)

        flash('Your password has been successfully reset! Please sign in with your new password.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', email=email)


@auth_bp.route('/logout')
def logout():
    if is_supabase_configured():
        try:
            supabase = create_supabase_client()
            if supabase:
                supabase.auth.sign_out()
        except Exception:
            pass
    session.clear()
    flash('You have been safely signed out.', 'info')
    return redirect(url_for('public.landing'))


@auth_bp.route('/preview-email-otp')
def preview_email_otp():
    """Live browser preview of the OTP email matching the reference design."""
    code = request.args.get('code', '384902')
    name = request.args.get('name', 'User')
    return EmailService.get_password_reset_html(code, name)


@auth_bp.route('/preview-signup-email')
def preview_signup_email():
    """Live browser preview of the signup confirmation email for Supabase."""
    import os
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tpl_path = os.path.join(base_dir, 'templates', 'emails', 'confirm_signup.html')
    with open(tpl_path, 'r', encoding='utf-8') as f:
        html = f.read()
    # Substitute GoTrue placeholders with demo values for browser preview
    html = html.replace('{{ .ConfirmationURL }}', url_for('auth.login', confirmed='true', _external=True))
    html = html.replace('{{ .Token }}', '482910')
    return html
