from flask import Blueprint, render_template, send_from_directory, current_app, request, redirect, url_for, session
import os

public_bp = Blueprint('public', __name__)


@public_bp.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(current_app.root_path, 'static', 'img'),
                               'logo.png', mimetype='image/png')


@public_bp.route('/site-unlock', methods=['GET', 'POST'])
def site_unlock():
    """Private development gate  -  requires authentication password to access the live site."""
    next_url = request.args.get('next') or url_for('public.landing')
    if not next_url.startswith('/') or next_url.startswith('//'):
        next_url = url_for('public.landing')

    if session.get('site_unlocked'):
        return redirect(next_url)

    error = None
    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        expected = current_app.config.get('DEV_PASSWORD', 'Icui4cu')
        if password == expected:
            session['site_unlocked'] = True
            session.permanent = False
            return redirect(next_url)
        else:
            error = "Invalid access password. Please try again."

    return render_template('public/site_unlock.html', error=error, next_url=next_url)


@public_bp.route('/')
def landing():
    """Marketing landing page  -  the first thing visitors see."""
    stats = [
        {'value': '500+', 'label': 'Active Users'},
        {'value': '200+', 'label': 'Platforms'},
        {'value': '50+', 'label': 'Countries'},
        {'value': '24/7', 'label': 'Uptime'},
    ]

    features = [
        {
            'icon': 'sim',
            'title': 'Real Non-VoIP Numbers',
            'text': 'Genuine cellular numbers that bypass even the strictest platform filters. '
                    'Say goodbye to "Invalid Number" errors.',
        },
        {
            'icon': 'bolt',
            'title': 'Instant Code Delivery',
            'text': 'Our auto-polling tech catches your verification codes in milliseconds. '
                    'The code lands in your dashboard immediately.',
        },
        {
            'icon': 'globe',
            'title': 'eSIM Marketplace',
            'text': 'Stay connected while travelling or get a secondary data line. '
                    'Instantly activate local data plans via QR code.',
        },
        {
            'icon': 'flag',
            'title': 'Multiple Countries',
            'text': 'Pick numbers from the USA, UK, Canada, Nigeria, and dozens of other '
                    'nations. Global coverage at your fingertips.',
        },
        {
            'icon': 'shield',
            'title': 'Privacy First',
            'text': 'Use disposable numbers for temporary accounts. Keep your personal data '
                    'safe from trackers and data brokers.',
        },
        {
            'icon': 'wallet',
            'title': 'Naira-Transparent Pricing',
            'text': 'Fund your wallet in Naira via bank transfer. No worrying about '
                    'fluctuating FX rates or black market dollar prices.',
        },
    ]

    steps = [
        {'num': 1, 'title': 'Fund Wallet',
         'text': 'Instant funding via bank transfer or card. Your balance is ready in seconds.'},
        {'num': 2, 'title': 'Pick Service',
         'text': 'Select the platform (e.g. WhatsApp) and the country you need a number from.'},
        {'num': 3, 'title': 'Get Verified',
         'text': 'Receive your code directly on your dashboard. Use it and you are good to go!'},
    ]

    platforms = ['WhatsApp', 'Telegram', 'Instagram', 'Facebook', 'Google',
                 'TikTok', 'PayPal', 'Twitter/X', 'Signal']

    use_cases = [
        {'icon': 'privacy', 'title': 'Personal Privacy',
         'text': 'Keep your real number off public databases.'},
        {'icon': 'briefcase', 'title': 'Business Accounts',
         'text': 'Separate professional WhatsApp lines easily.'},
        {'icon': 'plane', 'title': 'Traveller / eSIM',
         'text': 'Stay online with affordable international data.'},
    ]

    # Canonical amounts are stored in USD; the frontend converts/formats live.
    # USD values chosen so the NGN display (×1600) lands on the exact wallet
    # tiers from the design: ₦1,500 / ₦5,000 / ₦20,000.
    tiers = [
        {'name': 'Starter Pack', 'note': 'Ideal for single verification', 'usd': 0.9375},
        {'name': 'Popular Refill', 'note': 'Best for multiple services', 'usd': 3.125, 'featured': True},
        {'name': 'Power User', 'note': 'Volume discount applied', 'usd': 12.50},
    ]

    price_perks = [
        'Wallet funds never expire',
        "Free cancellations if code isn't sent",
        'Multi-currency support (NGN/USD)',
    ]

    faqs = [
        {'q': 'Are these real numbers?',
         'a': 'Yes. We provide genuine non-VoIP cellular numbers sourced from real carriers, '
              'so they pass verification on strict platforms like WhatsApp and Telegram.'},
        {'q': "What if I don't receive a code?",
         'a': 'If a code never arrives within the active window, the order is automatically '
              'cancelled and your wallet is refunded in full. You are never charged for a miss.'},
        {'q': 'How do I fund my wallet?',
         'a': 'You can top up instantly via bank transfer, debit/credit card, or USDT/crypto. '
              'Funds appear in your balance immediately.'},
        {'q': 'Can I use the number again later?',
         'a': 'Numbers are issued per verification. You can re-order the same service any time, '
              'and long-term rentals are available for select countries.'},
        {'q': 'Is it legal?',
         'a': 'Using a virtual number for account verification and privacy is legal in most '
              'regions. You are responsible for complying with the terms of the platforms you use.'},
    ]

    communities = [
        {'variant': 'telegram', 'icon': 'send', 'title': 'Telegram Channel',
         'text': 'Join 2,000+ users for instant service updates and restock alerts.',
         'cta': 'Join Channel'},
        {'variant': 'whatsapp', 'icon': 'chat', 'title': 'WhatsApp Group',
         'text': 'Connect with our community and get tips on the best services.',
         'cta': 'Join Group'},
        {'variant': 'support', 'icon': 'headset', 'title': 'Direct Support',
         'text': 'Need help with a specific issue? Our team is available 24/7.',
         'cta': 'Chat with Us'},
    ]

    return render_template(
        'public/landing.html',
        stats=stats, features=features, steps=steps, platforms=platforms,
        use_cases=use_cases, tiers=tiers, price_perks=price_perks,
        faqs=faqs, communities=communities,
    )
