"""Authentication routes (demo/session-based)."""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '')
        name = email.split('@')[0].capitalize() if '@' in email else 'Demo User'
        session['user'] = {
            'id': 'demo-user-id',
            'email': email,
            'full_name': name,
            'first_name': name.split(' ')[0],
            'role': 'user',
            'avatar': None,
        }
        flash('Welcome back to Tgsims!', 'success')
        return redirect(url_for('dashboard.index'))
    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username') or 'New User'
        email = request.form.get('email', '')
        session['user'] = {
            'id': 'demo-user-id',
            'email': email,
            'full_name': username,
            'first_name': username.split(' ')[0],
            'role': 'user',
            'avatar': None,
        }
        flash('Account created successfully! Your wallet has been initialized.', 'success')
        return redirect(url_for('dashboard.index'))
    return render_template('auth/register.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('public.landing'))
