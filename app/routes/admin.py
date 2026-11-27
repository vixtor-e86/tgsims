"""Admin Panel routes for Tgsims.
Provides platform management:
- Overview KPIs & Live Provider API balances
- Dynamic Pricing & Margin Control Center (USD/NGN FX rate, 5sim markup %, TextVerified markup %, Reactivation fee)
- Multi-Channel Deposit Verification (Squad, Crypto, Bank Transfer) with atomic wallet credit & audit trail
- SIM Order monitoring & manual refund trigger
- User Account inspection, role promotion, and wallet adjustments
Protected strictly by session['user']['role'] == 'admin'.
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from app.services.db_service import DBService
from app.services.settings_service import SettingsService
from app.services.sim_provider import FiveSimClient, VirtualSMSClient, SIMProviderService
import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.before_request
def require_admin():
    """Ensure user is logged in and possesses administrator or support privileges."""
    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
        'application/json' in request.headers.get('Accept', '') or
        request.is_json
    )
    user = session.get('user')
    if not user or not isinstance(user, dict):
        if is_ajax:
            return jsonify({'success': False, 'message': 'Admin session expired. Please refresh and log in.'}), 401
        flash('Please sign in with administrator credentials.', 'error')
        return redirect(url_for('auth.login', next=request.path))

    role = user.get('role')
    if role not in ('admin', 'support'):
        if is_ajax:
            return jsonify({'success': False, 'message': 'Access restricted. Administrator privileges required.'}), 403
        flash('Access restricted. Administrator privileges required.', 'error')
        return redirect(url_for('dashboard.index'))

    # Role-based restriction for 'support' staff:
    # Support staff are strictly limited to Support, Notifications, Orders, and Deposits.
    if role == 'support':
        endpoint = request.endpoint or ''
        if endpoint in ('admin.index', ''):
            return redirect(url_for('admin.support'))

        admin_only_endpoints = (
            'admin.pricing',
            'admin.users',
            'admin.update_user_role',
            'admin.adjust_user_balance',
            'admin.verify_deposit',
            'admin.reject_deposit',
        )
        if any(endpoint.startswith(ep) for ep in admin_only_endpoints):
            if is_ajax:
                return jsonify({'success': False, 'message': 'Access restricted. Administrator privileges required.'}), 403
            flash('Access restricted. Support staff permissions are limited to Support, Notifications, Orders, and Deposits.', 'error')
            return redirect(url_for('admin.support'))



@admin_bp.route('')
@admin_bp.route('/')
def index():
    """Admin Overview dashboard with KPI cards and live provider balance check."""
    stats = DBService.get_admin_overview_stats()
    settings = SettingsService.get_settings()

    # Query live SMS Code balance
    smscode_balance = None
    smscode_err = None
    try:
        sc_client = SIMProviderService.get_smscode_client()
        if sc_client.is_configured:
            bal_res = sc_client.get_balance()
            if bal_res.get('success'):
                smscode_balance = {
                    'balance': bal_res.get('balance'),
                    'currency': bal_res.get('currency', 'USD'),
                    'usd_estimate': bal_res.get('usd_estimate', 0.0)
                }
            else:
                smscode_err = bal_res.get('message')
        else:
            smscode_err = "API Key not configured in .env"
    except Exception as e:
        smscode_err = str(e)

    # Legacy aliases
    virtualsms_balance = smscode_balance
    virtualsms_err = smscode_err
    fivesim_balance = smscode_balance
    fivesim_err = smscode_err

    # Query TextVerified client status & live balance
    tv_balance = None
    tv_status = {'configured': False, 'status': 'Unknown'}
    try:
        tv_client = SIMProviderService.get_textverified_client()
        if tv_client:
            tv_status['configured'] = True
            tv_status['status'] = 'Active & Connected'
            try:
                acc = tv_client.account
                acc_bal = getattr(acc, 'balance', None)
                if callable(acc_bal):
                    acc_bal = acc_bal()
                if acc_bal is not None:
                    tv_balance = {
                        'balance': float(acc_bal),
                        'currency': 'USD',
                        'username': getattr(acc, 'username', '')
                    }
            except Exception as tv_e:
                print(f"[Admin] Error fetching TextVerified balance: {tv_e}")
        else:
            tv_status['configured'] = False
            tv_status['status'] = 'Not Configured (Missing TEXTVERIFIED_API_KEY)'
    except Exception as e:
        tv_status['status'] = f"Error: {e}"

    # Recent pending deposits
    pending_deposits = DBService.get_all_deposits_admin(status_filter='pending', limit=5)
    recent_orders = DBService.get_all_orders_admin(limit=6)

    return render_template(
        'admin/index.html',
        stats=stats,
        settings=settings,
        smscode_balance=smscode_balance,
        smscode_err=smscode_err,
        fivesim_balance=fivesim_balance,
        fivesim_err=fivesim_err,
        virtualsms_balance=virtualsms_balance,
        virtualsms_err=virtualsms_err,
        tv_status=tv_status,
        tv_balance=tv_balance,
        pending_deposits=pending_deposits,
        recent_orders=recent_orders,
        active_page='overview'
    )


# =============================================================================
# PRICING & MARGIN CONTROL CENTER
# =============================================================================

@admin_bp.route('/pricing', methods=['GET', 'POST'])
def pricing():
    """Manage USD/NGN exchange rate, SMS Code markup %, TextVerified markup %, and Reactivation fee."""
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_settings':
            try:
                def _safe_float(val, default):
                    if val is None or str(val).strip() == '':
                        return default
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        return default

                ngn_rate = _safe_float(request.form.get('ngn_per_usd_rate'), 1600.00)
                smscode_val = request.form.get('smscode_markup_percent')
                if smscode_val is None or str(smscode_val).strip() == '':
                    smscode_val = request.form.get('fivesim_markup_percent')
                smscode_pct = _safe_float(smscode_val, 25.00)

                smscode_floor_val = request.form.get('smscode_min_profit_usd')
                if smscode_floor_val is None or str(smscode_floor_val).strip() == '':
                    smscode_floor_val = request.form.get('fivesim_min_profit_usd')
                smscode_floor = round(_safe_float(smscode_floor_val, 0.25), 4)

                tv_pct = _safe_float(request.form.get('textverified_markup_percent'), 25.00)
                tv_floor = round(_safe_float(request.form.get('textverified_min_profit_usd'), 0.50), 4)
                react_fee = round(_safe_float(request.form.get('reactivation_fee_usd'), 1.00), 4)
                crypto_addr = request.form.get('crypto_deposit_address', '').strip()
                squad_on = 'squad_enabled' in request.form
                crypto_on = 'crypto_enabled' in request.form
                bank_details = request.form.get('manual_bank_details', '').strip()

                SettingsService.update_settings({
                    'ngn_per_usd_rate': ngn_rate,
                    'smscode_markup_percent': smscode_pct,
                    'smscode_min_profit_usd': smscode_floor,
                    'virtualsms_markup_percent': smscode_pct,
                    'virtualsms_min_profit_usd': smscode_floor,
                    'fivesim_markup_percent': smscode_pct,
                    'fivesim_min_profit_usd': smscode_floor,
                    'textverified_markup_percent': tv_pct,
                    'textverified_min_profit_usd': tv_floor,
                    'reactivation_fee_usd': react_fee,
                    'crypto_deposit_address': crypto_addr,
                    'squad_enabled': squad_on,
                    'crypto_enabled': crypto_on,
                    'manual_bank_details': bank_details
                })
                SIMProviderService.clear_all_caches()
                flash('Platform settings and profit margins updated successfully! Changes take effect immediately.', 'success')
            except Exception as e:
                flash(f'Failed to update settings: {e}', 'error')

        elif action in ('add_override', 'add_smscode_override', 'add_tv_override'):
            svc_code = request.form.get('service_code', '').strip().lower()
            svc_name = request.form.get('service_name', '').strip()
            prov_type = request.form.get('provider_type', 'smscode').strip().lower()
            if action == 'add_tv_override':
                prov_type = 'textverified'
            elif action == 'add_smscode_override':
                prov_type = 'smscode'
            norm_prov = 'textverified' if prov_type == 'textverified' else '5sim'
            try:
                rate = SettingsService.get_usd_ngn_rate()
                raw_usd = (request.form.get('override_price_usd') or '').replace('$', '').replace(',', '').strip()
                raw_ngn = (request.form.get('override_price_ngn') or '').replace('₦', '').replace(',', '').strip()
                override_usd = round(float(raw_usd), 4) if raw_usd else 0.0
                override_ngn = round(float(raw_ngn), 2) if raw_ngn else None

                if override_usd <= 0 and override_ngn and override_ngn > 0:
                    override_usd = round(override_ngn / rate, 4)
                elif override_usd > 0 and (override_ngn is None or override_ngn <= 0):
                    override_ngn = round(override_usd * rate, 2)

                notes = request.form.get('notes', '').strip()

                if norm_prov == 'textverified':
                    target_code = svc_code
                    target_name = svc_name or svc_code.capitalize()
                else:
                    country_code = (request.form.get('country_code') or 'ALL').strip().upper()
                    country_name = (request.form.get('country_name') or country_code).strip()
                    route_scope = (request.form.get('route_scope') or 'all').strip().lower()
                    cc_key = country_code.lower()
                    if route_scope in ('primary', 'secondary'):
                        target_code = f"{cc_key}:{svc_code}:{route_scope}"
                        route_label = 'Route 1 Primary' if route_scope == 'primary' else 'Route 2 Secondary'
                        target_name = f"{country_name} — {svc_name or svc_code.capitalize()} ({route_label})"
                    else:
                        target_code = f"{cc_key}:{svc_code}"
                        target_name = f"{country_name} — {svc_name or svc_code.capitalize()}"

                if svc_code and override_usd > 0:
                    ok = SettingsService.set_price_override(
                        target_code,
                        target_name,
                        norm_prov,
                        override_usd,
                        notes,
                        override_price_ngn=override_ngn
                    )
                    if ok:
                        SIMProviderService.clear_all_caches()
                        flash(f'Price override saved for {target_name} at ${override_usd:.2f} (₦{override_ngn:,.2f}).', 'success')
                    else:
                        flash(f'Failed to save price override for {target_name}. Please check system logs.', 'error')
                else:
                    flash('Please select a valid service and enter an override price.', 'error')
            except Exception as e:
                flash(f'Error saving price override: {e}', 'error')

        elif action == 'delete_override':
            override_id = request.form.get('override_id')
            if override_id:
                SettingsService.delete_price_override(override_id)
                SIMProviderService.clear_all_caches()
                flash('Price override removed.', 'info')

        elif action in ('sync_smscode_prices', 'sync_5sim_prices', 'sync_virtualsms_prices'):
            try:
                from scripts.sync_smscode_prices import sync_all
                ok = sync_all()
                SIMProviderService.clear_all_caches()
                if ok:
                    flash('Successfully updated live SMS Code wholesale prices across all countries and services! Prices are now 100% current.', 'success')
                else:
                    flash('Failed to reach SMS Code pricing server. Please check connection and try again.', 'error')
            except Exception as e:
                flash(f'Error syncing SMS Code wholesale prices: {e}', 'error')

        elif action == 'update_us_operator_price':
            operator_code = request.form.get('operator_code', '').strip().lower()
            operator_name = request.form.get('operator_name', '').strip()
            raw_usd = request.form.get('custom_price_usd', '').strip()
            raw_ngn = request.form.get('custom_price_ngn', '').strip()
            usd_val = raw_usd.replace('$', '').replace(',', '').strip() if raw_usd else ''
            ngn_val = raw_ngn.replace('₦', '').replace(',', '').strip() if raw_ngn else ''

            is_ajax = (
                request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
                request.args.get('format') == 'json' or
                'application/json' in request.headers.get('Accept', '') or
                request.is_json
            )
            try:
                rate = SettingsService.get_usd_ngn_rate()
                custom_usd = float(usd_val) if usd_val else None
                custom_ngn = float(ngn_val) if ngn_val else None

                # Convert if one was supplied and not the other
                if custom_usd is None and custom_ngn is not None and custom_ngn > 0:
                    custom_usd = round(custom_ngn / rate, 4)
                elif custom_ngn is None and custom_usd is not None and custom_usd > 0:
                    custom_ngn = round(custom_usd * rate, 2)

                if operator_code:
                    ok = SettingsService.set_us_whatsapp_operator_price(
                        operator_code=operator_code,
                        custom_price_usd=custom_usd,
                        custom_price_ngn=custom_ngn,
                        operator_name=operator_name
                    )
                    if ok:
                        SIMProviderService.clear_all_caches()
                        ops = SettingsService.get_us_whatsapp_operators_pricing()
                        matched = next((o for o in ops if o['operator_code'] == operator_code), None)
                        retail_usd = matched['retail_usd'] if matched else (custom_usd or 0.0)
                        retail_ngn = matched['retail_ngn'] if matched else round(retail_usd * rate, 2)
                        is_custom = matched['is_custom'] if matched else (custom_usd is not None and custom_usd > 0)

                        msg = f'Custom selling price saved for WhatsApp ({operator_name or operator_code}) at ${retail_usd:.2f} (₦{retail_ngn:,.2f}).' if is_custom else f'Custom price cleared for WhatsApp ({operator_name or operator_code}). Reverted to auto-markup.'
                        if is_ajax:
                            return jsonify({
                                'success': True,
                                'message': msg,
                                'operator_code': operator_code,
                                'retail_usd': retail_usd,
                                'retail_ngn': retail_ngn,
                                'retail_usd_str': f"${retail_usd:.2f}",
                                'retail_ngn_str': f"₦{retail_ngn:,.2f}",
                                'is_custom': is_custom,
                                'custom_price_usd': custom_usd,
                                'custom_price_ngn': custom_ngn
                            })
                        flash(msg, 'success' if is_custom else 'info')
                    else:
                        if is_ajax:
                            return jsonify({'success': False, 'message': 'Failed to save operator price. Please check database connection.'}), 200
                        flash('Failed to save operator price.', 'error')
                else:
                    if is_ajax:
                        return jsonify({'success': False, 'message': 'Missing operator code.'}), 200
                    flash('Missing operator code.', 'error')
            except Exception as e:
                if is_ajax:
                    return jsonify({'success': False, 'message': f'Error saving operator price: {e}'}), 200
                flash(f'Error saving operator price: {e}', 'error')

        elif action == 'reset_us_operator_price':
            operator_code = request.form.get('operator_code', '').strip().lower()
            is_ajax = (
                request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
                request.args.get('format') == 'json' or
                'application/json' in request.headers.get('Accept', '') or
                request.is_json
            )
            try:
                ok = SettingsService.set_us_whatsapp_operator_price(operator_code=operator_code, custom_price_usd=None)
                if ok:
                    SIMProviderService.clear_all_caches()
                    rate = SettingsService.get_usd_ngn_rate()
                    ops = SettingsService.get_us_whatsapp_operators_pricing()
                    matched = next((o for o in ops if o['operator_code'] == operator_code), None)
                    retail_usd = matched['retail_usd'] if matched else 0.0
                    retail_ngn = matched['retail_ngn'] if matched else round(retail_usd * rate, 2)
                    msg = f'Operator price reset to auto-markup.'
                    if is_ajax:
                        return jsonify({
                            'success': True,
                            'message': msg,
                            'operator_code': operator_code,
                            'retail_usd': retail_usd,
                            'retail_ngn': retail_ngn,
                            'retail_usd_str': f"${retail_usd:.2f}",
                            'retail_ngn_str': f"₦{retail_ngn:,.2f}",
                            'is_custom': False,
                            'custom_price_usd': None
                        })
                    flash(msg, 'info')
                else:
                    if is_ajax:
                        return jsonify({'success': False, 'message': 'Failed to reset operator price.'}), 200
                    flash('Failed to reset operator price.', 'error')
            except Exception as e:
                if is_ajax:
                    return jsonify({'success': False, 'message': str(e)}), 200
                flash(f'Error resetting operator price: {e}', 'error')

        elif action == 'update_rental_price':
            service_code = request.form.get('service_code', '').strip().lower()
            service_name = request.form.get('service_name', '').strip()
            duration_days = request.form.get('duration_days', 3)
            raw_price = request.form.get('custom_price_usd', '').strip()
            price_val = raw_price.replace('$', '').replace(',', '').strip() if raw_price else ''
            is_ajax = (
                request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
                request.args.get('format') == 'json' or
                'application/json' in request.headers.get('Accept', '') or
                request.is_json
            )
            try:
                custom_price = float(price_val) if price_val else None
                if service_code and duration_days:
                    ok = SettingsService.update_rental_price(
                        service_code=service_code,
                        duration_days=int(duration_days),
                        custom_price_usd=custom_price,
                        service_name=service_name
                    )
                    if ok:
                        SIMProviderService.clear_all_caches()
                        # Recalculate latest active pricing for instant UI update
                        ngn_rate = SettingsService.get_usd_ngn_rate()
                        pct, floor = SettingsService.get_textverified_markup()
                        mult = 1.0 + (pct / 100.0)
                        pmap = SettingsService.get_rental_pricing_map()
                        db_item = pmap.get((service_code, int(duration_days)), {})
                        base_cost = float(db_item.get('wholesale_price_usd') or 0.0)
                        if custom_price is not None and custom_price > 0:
                            retail_usd = round(float(custom_price), 2)
                            is_custom = True
                        else:
                            retail_usd = round(max(base_cost * mult, base_cost + floor), 2)
                            is_custom = False
                        retail_ngn = round(retail_usd * ngn_rate, 2)

                        msg = f'Custom selling price saved for {service_name or service_code} ({duration_days} Days) at ${retail_usd:.2f}.' if is_custom else f'Custom price cleared for {service_name or service_code} ({duration_days} Days). Reverted to auto-markup.'
                        if is_ajax:
                            return jsonify({
                                'success': True,
                                'message': msg,
                                'service_code': service_code,
                                'duration_days': int(duration_days),
                                'retail_usd': retail_usd,
                                'retail_ngn': retail_ngn,
                                'retail_usd_str': f"${retail_usd:.2f}",
                                'retail_ngn_str': f"₦{retail_ngn:,.2f}",
                                'is_custom': is_custom,
                                'custom_price_usd': custom_price
                            })
                        flash(msg, 'success' if is_custom else 'info')
                    else:
                        if is_ajax:
                            return jsonify({'success': False, 'message': 'Failed to save rental price to database. Please try again.'}), 200
                        flash('Failed to save rental price. Please ensure database connection is active.', 'error')
                else:
                    if is_ajax:
                        return jsonify({'success': False, 'message': 'Missing service code or duration.'}), 200
                    flash('Missing service code or duration.', 'error')
            except Exception as e:
                if is_ajax:
                    return jsonify({'success': False, 'message': f'Error saving rental price: {e}'}), 200
                flash(f'Error saving rental price: {e}', 'error')

        elif action == 'reset_rental_price':
            service_code = request.form.get('service_code', '').strip().lower()
            duration_days = request.form.get('duration_days', 3)
            is_ajax = (
                request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
                request.args.get('format') == 'json' or
                'application/json' in request.headers.get('Accept', '') or
                request.is_json
            )
            try:
                if service_code and duration_days:
                    ok = SettingsService.reset_rental_price(service_code, int(duration_days))
                    if ok:
                        SIMProviderService.clear_all_caches()
                        # Recalculate auto markup
                        ngn_rate = SettingsService.get_usd_ngn_rate()
                        pct, floor = SettingsService.get_textverified_markup()
                        mult = 1.0 + (pct / 100.0)
                        pmap = SettingsService.get_rental_pricing_map()
                        db_item = pmap.get((service_code, int(duration_days)), {})
                        base_cost = float(db_item.get('wholesale_price_usd') or 0.0)
                        retail_usd = round(max(base_cost * mult, base_cost + floor), 2)
                        retail_ngn = round(retail_usd * ngn_rate, 2)
                        msg = f'Custom price removed for {service_code} ({duration_days} Days). Standard dynamic markup restored.'
                        if is_ajax:
                            return jsonify({
                                'success': True,
                                'message': msg,
                                'service_code': service_code,
                                'duration_days': int(duration_days),
                                'retail_usd': retail_usd,
                                'retail_ngn': retail_ngn,
                                'retail_usd_str': f"${retail_usd:.2f}",
                                'retail_ngn_str': f"₦{retail_ngn:,.2f}",
                                'is_custom': False,
                                'custom_price_usd': None
                            })
                        flash(msg, 'info')
                    else:
                        if is_ajax:
                            return jsonify({'success': False, 'message': 'Failed to reset rental price. Please try again.'}), 200
                        flash('Failed to reset rental price.', 'error')
                else:
                    if is_ajax:
                        return jsonify({'success': False, 'message': 'Missing service code or duration.'}), 200
                    flash('Missing service code or duration.', 'error')
            except Exception as e:
                if is_ajax:
                    return jsonify({'success': False, 'message': f'Error resetting rental price: {e}'}), 200
                flash(f'Error resetting rental price: {e}', 'error')

        elif action == 'sync_rental_prices':
            try:
                ok, msg, count = SettingsService.sync_rental_wholesale_prices()
                if ok:
                    flash(msg, 'success')
                else:
                    flash(msg, 'error')
            except Exception as e:
                flash(f'Error syncing rental wholesale prices from TextVerified: {e}', 'error')

        return redirect(url_for('admin.pricing'))

    settings = SettingsService.get_settings(force_refresh=True)
    all_overrides = SettingsService.get_price_overrides()
    us_whatsapp_operators = SettingsService.get_us_whatsapp_operators_pricing()

    # Precalculated examples for admin visualization
    rate = SettingsService.get_usd_ngn_rate()
    f5_pct, f5_floor = SettingsService.get_smscode_markup()
    tv_pct, tv_floor = SettingsService.get_textverified_markup()
    react_fee = SettingsService.get_reactivation_fee()

    # Load full global SMSCode catalog (countries + services)
    global_cat = SIMProviderService.get_catalog()
    raw_countries = global_cat.get('countries', []) if isinstance(global_cat, dict) else []
    raw_global_services = global_cat.get('services', []) if isinstance(global_cat, dict) else []

    smscode_countries = [
        {
            'country_code': 'ALL',
            'country_name': 'All Countries (Global Default)',
            'flag': '🌍',
            'dial': 'Global',
            'is_popular': True
        },
        {
            'country_code': 'US',
            'country_name': 'United States (US Basic Package)',
            'flag': '🇺🇸',
            'dial': '+1',
            'is_popular': True
        }
    ]
    POPULAR_CC = {'GB', 'NG', 'CA', 'DE', 'ID', 'PH', 'NL', 'FR', 'IN', 'ZA', 'AU', 'BR', 'ES', 'IT', 'MX', 'KE', 'GH', 'AE'}
    country_lookup = {
        'ALL': {'country_code': 'ALL', 'country_name': 'All Countries (Global)', 'flag': '🌍', 'dial': 'Global'},
        'US': {'country_code': 'US', 'country_name': 'United States (US Basic)', 'flag': '🇺🇸', 'dial': '+1'}
    }
    for c in raw_countries:
        cc = (c.get('country_code') or '').strip().upper()
        if not cc or cc == 'US':
            continue
        c_entry = {
            'country_code': cc,
            'country_name': c.get('country_name', cc),
            'flag': c.get('flag', '🌐'),
            'dial': c.get('dial', ''),
            'is_popular': cc in POPULAR_CC
        }
        smscode_countries.append(c_entry)
        country_lookup[cc] = c_entry

    # Build SMSCode services list (1,236 services from catalog.json, falling back to US list if empty)
    # Include 'all' at the top so admin can override ALL services under a selected country in one click
    smscode_services_catalog = [
        {
            'service_code': 'all',
            'service_name': 'All Services (Every Service in Selected Country)',
            'is_core': True,
            'is_all_services': True,
            'base_cost': 0.50
        }
    ]
    seen_smscode_svc = {'all'}
    service_lookup = {
        'all': 'All Services (Entire Country)'
    }
    for s in raw_global_services:
        sc = (s.get('code') or '').strip().lower()
        if sc and sc not in seen_smscode_svc:
            seen_smscode_svc.add(sc)
            s_name = s.get('name', sc.capitalize())
            entry = {
                'service_code': sc,
                'service_name': s_name,
                'is_core': bool(s.get('is_core')),
                'base_cost': float(s.get('base_cost') or 0.50)
            }
            smscode_services_catalog.append(entry)
            service_lookup[sc] = s_name

    f5_raw = SIMProviderService.get_5sim_us_services(apply_markup=False)
    seen_f5 = set()
    f5_catalog = []
    for s in f5_raw:
        sc = (s.get('service_code') or '').strip().lower()
        if sc and sc not in seen_f5:
            seen_f5.add(sc)
            s_name = s.get('service_name', sc.capitalize())
            f5_catalog.append({
                'service_code': sc,
                'service_name': s_name,
                'is_core': bool(s.get('is_core')),
                'base_cost': float(s.get('price_usd', 0.50))
            })
            if sc not in service_lookup:
                service_lookup[sc] = s_name
            if sc not in seen_smscode_svc:
                seen_smscode_svc.add(sc)
                smscode_services_catalog.append({
                    'service_code': sc,
                    'service_name': s_name,
                    'is_core': bool(s.get('is_core')),
                    'base_cost': float(s.get('price_usd', 0.50))
                })

    tv_raw = SIMProviderService.get_textverified_us_services(apply_markup=False)
    seen_tv = set()
    tv_catalog = []
    for s in tv_raw:
        sc = s.get('service_code')
        if sc and sc not in seen_tv:
            seen_tv.add(sc)
            tv_catalog.append({
                'service_code': sc,
                'service_name': s.get('service_name', sc.capitalize()),
                'base_cost': float(s.get('price_usd', 0.50))
            })

    # Separate overrides into:
    # 1. tv_overrides (TextVerified US Reliable)
    # 2. smscode_overrides (SMSCode Country + Service + Route overrides)
    # (Excluding US WhatsApp operator-specific overrides which have their own dedicated table)
    US_WA_OP_CODES = {'tmobile', 'at_t', 'verizon', 'mint_mobile', 'us_mobile', 'any', 'basic', '125', '111', '119', '128', '127', '0'}
    tv_overrides = []
    smscode_overrides = []
    for ov in all_overrides:
        raw_sc = (ov.get('service_code') or '').strip().lower()
        if not raw_sc:
            continue
        if raw_sc.startswith('whatsapp:') and raw_sc.split(':', 1)[1] in US_WA_OP_CODES:
            continue

        ov_copy = dict(ov)
        ov_usd = float(ov.get('override_price_usd') or 0.0)
        ov_ngn = float(ov.get('override_price_ngn') or round(ov_usd * rate, 2))
        ov_copy['override_price_usd'] = ov_usd
        ov_copy['override_price_ngn'] = ov_ngn

        if ov.get('provider_type') == 'textverified':
            tv_overrides.append(ov_copy)
        else:
            parts = raw_sc.split(':')
            if len(parts) == 3 and parts[2] in ('primary', 'secondary'):
                cc_part = parts[0].upper()
                svc_part = parts[1]
                route_scope = parts[2]
            elif len(parts) == 2:
                cc_part = parts[0].upper()
                svc_part = parts[1]
                route_scope = 'all'
            else:
                cc_part = 'US'
                svc_part = raw_sc
                route_scope = 'all'

            c_meta = country_lookup.get(cc_part, {
                'country_code': cc_part,
                'country_name': cc_part,
                'flag': '🌐',
                'dial': ''
            })
            clean_svc_name = service_lookup.get(svc_part)
            if not clean_svc_name:
                raw_sname = ov.get('service_name') or svc_part.capitalize()
                if '—' in raw_sname:
                    clean_svc_name = raw_sname.split('—', 1)[1].split(' (Route')[0].strip()
                else:
                    clean_svc_name = raw_sname

            ov_copy['country_code'] = cc_part
            ov_copy['country_name'] = c_meta['country_name']
            ov_copy['country_flag'] = c_meta['flag']
            ov_copy['clean_service_code'] = svc_part
            ov_copy['clean_service_name'] = clean_svc_name
            ov_copy['route_scope'] = route_scope
            if route_scope == 'primary':
                ov_copy['route_label'] = 'Route 1 (Primary)'
            elif route_scope == 'secondary':
                ov_copy['route_label'] = 'Route 2 (Secondary)'
            else:
                ov_copy['route_label'] = 'All Routes (Primary & Secondary)'
            smscode_overrides.append(ov_copy)

    # Example SMSCode cost: $0.50 -> retail price calculation
    f5_ex_cost = 0.50
    f5_profit = max(f5_ex_cost * (f5_pct / 100.0), f5_floor) if (f5_pct > 0 or f5_floor > 0) else 0.0
    f5_ex_price = round(f5_ex_cost + f5_profit, 2)
    f5_ex_profit = round(f5_ex_price - f5_ex_cost, 2)

    # Example TextVerified cost: $1.50 (e.g. WhatsApp) -> retail price calculation
    tv_ex_cost = 1.50
    tv_profit = max(tv_ex_cost * (tv_pct / 100.0), tv_floor) if (tv_pct > 0 or tv_floor > 0) else 0.0
    tv_ex_price = round(tv_ex_cost + tv_profit, 2)
    tv_ex_profit = round(tv_ex_price - tv_ex_cost, 2)

    examples = {
        'smscode': {'cost': f5_ex_cost, 'price': f5_ex_price, 'profit': f5_ex_profit, 'ngn': round(f5_ex_price * rate, 2)},
        'virtualsms': {'cost': f5_ex_cost, 'price': f5_ex_price, 'profit': f5_ex_profit, 'ngn': round(f5_ex_price * rate, 2)},
        'fivesim': {'cost': f5_ex_cost, 'price': f5_ex_price, 'profit': f5_ex_profit, 'ngn': round(f5_ex_price * rate, 2)},
        'textverified': {'cost': tv_ex_cost, 'price': tv_ex_price, 'profit': tv_ex_profit, 'ngn': round(tv_ex_price * rate, 2)},
        'reactivation': {'price': react_fee, 'ngn': round(react_fee * rate, 2)}
    }

    services_catalog = {
        'smscode': smscode_services_catalog,
        'smscode_countries': smscode_countries,
        'virtualsms': smscode_services_catalog,
        '5sim': f5_catalog,
        'textverified': tv_catalog
    }

    # Dedicated long-term rental catalog (10 core services across 3, 7, 14, 30 days)
    rental_catalog = SIMProviderService.get_rental_catalog()

    return render_template(
        'admin/pricing.html',
        settings=settings,
        overrides=tv_overrides + smscode_overrides,
        tv_overrides=tv_overrides,
        smscode_overrides=smscode_overrides,
        smscode_countries=smscode_countries,
        us_whatsapp_operators=us_whatsapp_operators,
        examples=examples,
        services_catalog=services_catalog,
        rental_catalog=rental_catalog,
        active_page='pricing'
    )


# =============================================================================
# MANUAL DEPOSIT VERIFICATION & AUDIT
# =============================================================================

@admin_bp.route('/deposits')
def deposits():
    """List deposit transactions with filtering by status."""
    status_filter = request.args.get('status', 'all')
    all_deposits = DBService.get_all_deposits_admin(status_filter=status_filter, limit=100)
    settings = SettingsService.get_settings()

    return render_template(
        'admin/deposits.html',
        deposits=all_deposits,
        status_filter=status_filter,
        settings=settings,
        active_page='deposits'
    )


@admin_bp.route('/deposits/<tx_id>/verify', methods=['POST'])
def verify_deposit(tx_id):
    """Admin manually approves and credits a pending or failed deposit."""
    admin_user = session.get('user', {})
    if admin_user.get('role') != 'admin':
        flash('Permission denied. Only administrators can verify and credit deposits.', 'error')
        return redirect(url_for('admin.deposits'))

    admin_id = admin_user.get('id', 'admin')
    admin_notes = request.form.get('admin_notes', f"Verified by {admin_user.get('full_name', 'Admin')}")

    res = DBService.verify_deposit_admin(tx_id, admin_user_id=admin_id, admin_notes=admin_notes)
    if res.get('success'):
        # Dispatch notification to user
        u_id = res.get('user_id')
        amt = float(res.get('amount', 0.00))
        rate = float(SettingsService.get_settings().get('ngn_per_usd_rate', 1600.00))
        from app.services.currency_service import format_ngn
        if u_id:
            DBService.create_user_notification(
                user_id=u_id,
                title="Deposit Verified & Credited",
                message=f"Your deposit of ${amt:.2f} (≈ {format_ngn(amt, rate)}) has been verified and added to your wallet balance.",
                type="deposit",
                link="/wallet"
            )
        flash(res.get('message', 'Deposit verified and wallet credited!'), 'success')
    else:
        flash(res.get('message', 'Failed to verify deposit.'), 'error')

    return redirect(url_for('admin.deposits', status=request.form.get('return_status', 'all')))


@admin_bp.route('/deposits/<tx_id>/reject', methods=['POST'])
def reject_deposit(tx_id):
    """Admin rejects a pending deposit."""
    admin_user = session.get('user', {})
    if admin_user.get('role') != 'admin':
        flash('Permission denied. Only administrators can reject deposits.', 'error')
        return redirect(url_for('admin.deposits'))

    admin_id = admin_user.get('id', 'admin')
    reason = request.form.get('reason', 'Payment not received or invalid reference')

    res = DBService.reject_deposit_admin(tx_id, admin_user_id=admin_id, reason=reason)
    if res.get('success'):
        flash('Deposit marked as rejected.', 'info')
    else:
        flash(res.get('message', 'Failed to reject deposit.'), 'error')

    return redirect(url_for('admin.deposits', status=request.form.get('return_status', 'all')))


# =============================================================================
# ORDER MONITORING & REFUND MANAGEMENT
# =============================================================================

@admin_bp.route('/orders')
def orders():
    """All user verification orders & dedicated number rentals across the platform."""
    tab = request.args.get('tab', 'sims')
    status_filter = request.args.get('status', 'all')

    if tab == 'rentals':
        all_rentals = DBService.get_all_rentals_admin(status_filter=status_filter, limit=100)
        return render_template(
            'admin/orders.html',
            rentals=all_rentals,
            tab='rentals',
            status_filter=status_filter,
            active_page='orders'
        )
    else:
        all_orders = DBService.get_all_orders_admin(status_filter=status_filter, limit=100)
        return render_template(
            'admin/orders.html',
            orders=all_orders,
            tab='sims',
            status_filter=status_filter,
            active_page='orders'
        )


@admin_bp.route('/orders/<order_id>/refund', methods=['POST'])
def manual_refund_order(order_id):
    """Admin triggers a manual refund for an order back to the user's wallet and cancels line on provider."""
    user_id = request.form.get('user_id')
    reason = request.form.get('reason', 'Manual admin refund')

    # Look up order to ensure provider cancellation is called
    order = DBService.get_order_by_id(user_id=None, order_id=order_id)
    if order:
        prov_id = order.get('provider_order_id')
        if prov_id and not str(prov_id).startswith('SIM-') and not str(prov_id).startswith('USCA-'):
            try:
                SIMProviderService.cancel_order(str(prov_id))
            except Exception as pe:
                print(f"[manual_refund_order] provider cancel note: {pe}")

    res = DBService.refund_order(order_id, user_id=user_id, reason=reason)
    if res.get('success'):
        flash(res.get('message', 'Order refunded and funds credited to user wallet! Provider line cancelled.'), 'success')
    else:
        flash(res.get('message', 'Failed to refund order.'), 'error')

    tab = request.form.get('tab', 'sims')
    return redirect(url_for('admin.orders', tab=tab))


@admin_bp.route('/rentals/<rental_id>/refund', methods=['POST'])
def manual_refund_rental(rental_id):
    """Admin triggers a manual refund for a rental back to the user's wallet and returns the carrier line."""
    reason = request.form.get('reason', 'Admin manual rental refund')
    res = SIMProviderService.cancel_rental(rental_id=rental_id, user_id=None, reason=reason)
    if res.get('success'):
        flash(res.get('message', 'Dedicated rental refunded and line returned to carrier!'), 'success')
    else:
        flash(res.get('message', res.get('message', 'Failed to refund rental.')), 'error')

    return redirect(url_for('admin.orders', tab='rentals'))


# =============================================================================
# USER MANAGEMENT & BALANCE ADJUSTMENTS
# =============================================================================

@admin_bp.route('/users')
def users():
    """User account directory with wallet balances and role controls."""
    search_q = request.args.get('q', '').strip()
    user_list = DBService.get_all_users_admin(search=search_q, limit=100)

    return render_template(
        'admin/users.html',
        users=user_list,
        search_q=search_q,
        active_page='users'
    )


@admin_bp.route('/users/<user_id>/role', methods=['POST'])
@admin_bp.route('/users/<user_id>/update-role', methods=['POST'])
def update_user_role(user_id):
    """Promote or demote a user role ('user', 'support', 'admin')."""
    new_role = request.form.get('role', 'user')
    current_admin = session.get('user', {})
    if user_id == current_admin.get('id') and new_role != 'admin':
        flash('You cannot demote yourself from administrator.', 'error')
        return redirect(url_for('admin.users'))

    ok = DBService.update_user_role_admin(user_id, new_role)
    if ok:
        role_label = 'SUPPORT AGENT' if new_role == 'support' else ('ADMINISTRATOR' if new_role == 'admin' else 'STANDARD USER')
        flash(f'User role successfully updated to {role_label}.', 'success')
    else:
        flash(f'Failed to update user role to {new_role}. Please ensure database constraint allows support role.', 'error')

    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<user_id>/adjust-balance', methods=['POST'])
def adjust_user_balance(user_id):
    """Admin credits or debits a user wallet balance with audit note."""
    admin_user = session.get('user', {})
    admin_id = admin_user.get('id', 'admin')
    try:
        raw_val = str(request.form.get('amount', '0')).replace(',', '').replace('₦', '').replace('$', '').strip()
        try:
            raw_amount = float(raw_val)
        except (ValueError, TypeError):
            raw_amount = 0.0

        currency = request.form.get('currency', 'USD').strip().upper()
        reason = request.form.get('reason', 'Administrative adjustment').strip()
        adjustment_type = request.form.get('adjustment_type', 'credit')

        if raw_amount <= 0:
            flash('Amount must be greater than zero.', 'error')
            return redirect(url_for('admin.users'))

        rate = float(SettingsService.get_settings().get('ngn_per_usd_rate', 1600.00))
        if rate <= 0:
            rate = 1600.00

        from app.services.currency_service import reconcile_ngn_amount, ngn_to_usd

        # Convert to canonical USD if input was in NGN
        if currency == 'NGN':
            amount_usd = max(0.01, ngn_to_usd(raw_amount, rate, decimals=4))
            ngn_display = raw_amount
            usd_display = round(amount_usd, 2)
        else:
            amount_usd = round(raw_amount, 2)
            ngn_display = reconcile_ngn_amount(raw_amount, rate)
            usd_display = amount_usd

        signed_amount_usd = amount_usd if adjustment_type == 'credit' else -amount_usd
        res = DBService.adjust_user_balance_admin(
            user_id=user_id,
            amount=signed_amount_usd,
            reason=reason,
            admin_user_id=admin_id,
            extra_metadata={
                'adjusted_currency': currency,
                'amount_ngn': ngn_display,
                'rate': rate
            }
        )

        if res.get('success'):
            new_bal_usd = float(res.get('new_balance', 0.0))
            new_bal_ngn = reconcile_ngn_amount(new_bal_usd, rate)

            if adjustment_type == 'credit':
                if currency == 'NGN':
                    cust_msg = f"An administrator credited ₦{ngn_display:,.2f} (≈ ${usd_display:.2f}) to your wallet. Reason: {reason}"
                    flash_msg = f"Wallet successfully credited by ₦{ngn_display:,.2f} (${usd_display:.2f} USD). New balance: ₦{new_bal_ngn:,.2f} (${new_bal_usd:.2f} USD)."
                else:
                    cust_msg = f"An administrator credited ${usd_display:.2f} (≈ ₦{ngn_display:,.2f}) to your wallet. Reason: {reason}"
                    flash_msg = f"Wallet successfully credited by ${usd_display:.2f} (≈ ₦{ngn_display:,.2f}). New balance: ${new_bal_usd:.2f} (≈ ₦{new_bal_ngn:,.2f})."

                DBService.create_user_notification(
                    user_id=user_id,
                    title="Funds Added to Wallet",
                    message=cust_msg,
                    type="admin_credit",
                    link="/wallet"
                )
            else:
                if currency == 'NGN':
                    cust_msg = f"An administrator deducted ₦{ngn_display:,.2f} (≈ ${usd_display:.2f}) from your wallet. Reason: {reason}"
                    flash_msg = f"Wallet successfully debited by ₦{ngn_display:,.2f} (${usd_display:.2f} USD). New balance: ₦{new_bal_ngn:,.2f} (${new_bal_usd:.2f} USD)."
                else:
                    cust_msg = f"An administrator deducted ${usd_display:.2f} (≈ ₦{ngn_display:,.2f}) from your wallet. Reason: {reason}"
                    flash_msg = f"Wallet successfully debited by ${usd_display:.2f} (≈ ₦{ngn_display:,.2f}). New balance: ${new_bal_usd:.2f} (≈ ₦{new_bal_ngn:,.2f})."

                DBService.create_user_notification(
                    user_id=user_id,
                    title="Funds Deducted from Wallet",
                    message=cust_msg,
                    type="admin_debit",
                    link="/wallet"
                )
            flash(flash_msg, 'success')
        else:
            flash(res.get('message', 'Failed to adjust balance.'), 'error')
    except Exception as e:
        flash(f'Error adjusting balance: {e}', 'error')

    return redirect(url_for('admin.users'))


# =============================================================================
# SUPPORT TICKETS & COMPLAINTS DESK
# =============================================================================

@admin_bp.route('/support')
@admin_bp.route('/support/<ticket_id>')
def support(ticket_id=None):
    """Customer Support & Complaints Desk.
    Provides realtime ticket management, message history, instant reply, and status updates.
    """
    status_filter = request.args.get('status', 'all')
    search_q = request.args.get('q', '').strip()
    selected_id = ticket_id or request.args.get('ticket_id', '').strip()

    tickets = DBService.get_all_tickets_admin(status_filter=status_filter, search=search_q)
    stats = DBService.get_admin_support_stats()

    selected_ticket = None
    messages = []
    has_explicit_selection = bool(selected_id)

    if selected_id:
        selected_ticket = DBService.get_ticket_by_id(selected_id, is_admin=True)
        if selected_ticket:
            messages = DBService.get_ticket_messages(selected_ticket['id'], is_admin=True, mark_read=True)
    elif tickets:
        selected_ticket = tickets[0]
        messages = DBService.get_ticket_messages(selected_ticket['id'], is_admin=True, mark_read=False)

    return render_template(
        'admin/support.html',
        tickets=tickets,
        selected_ticket=selected_ticket,
        messages=messages,
        stats=stats,
        status_filter=status_filter,
        search_q=search_q,
        has_explicit_selection=has_explicit_selection,
        active_page='support'
    )


@admin_bp.route('/support/<ticket_id>/reply', methods=['POST'])
def support_reply(ticket_id):
    """Standard form POST fallback for replying to a ticket."""
    user = session.get('user', {})
    reply_text = request.form.get('message', '').strip()
    new_status = request.form.get('status')

    if not reply_text:
        flash('Reply message cannot be empty.', 'error')
        return redirect(url_for('admin.support', ticket_id=ticket_id))

    admin_name = 'Support'
    sender_role = 'support'

    DBService.add_support_message(
        ticket_id=ticket_id,
        sender_id=user.get('id'),
        sender_name='Support',
        sender_role=sender_role,
        message=reply_text
    )

    if new_status:
        DBService.update_ticket_status(ticket_id, new_status, actor_role=sender_role, actor_name='Support')

    flash('Reply sent successfully.', 'success')
    return redirect(url_for('admin.support', ticket_id=ticket_id))


@admin_bp.route('/support/<ticket_id>/status', methods=['POST'])
def support_status(ticket_id):
    """Update ticket status via form POST."""
    user = session.get('user', {})
    new_status = request.form.get('status', '').strip()

    res = DBService.update_ticket_status(
        ticket_id=ticket_id,
        new_status=new_status,
        actor_role='admin',
        actor_name='Support'
    )
    if res.get('success'):
        flash(f'Ticket status changed to {new_status.capitalize()}.', 'success')
    else:
        flash(res.get('message', 'Failed to update ticket status.'), 'error')

    return redirect(url_for('admin.support', ticket_id=ticket_id))


# =============================================================================
# ADMIN PUSH NOTIFICATIONS & BROADCASTS
# =============================================================================

@admin_bp.route('/notifications', methods=['GET', 'POST'])
def notifications():
    """Admin Push Notification Console: broadcast to all users or target a specific user."""
    if request.method == 'POST':
        target = request.form.get('target', 'all')
        target_user_id = request.form.get('target_user_id', '').strip() or None
        title = request.form.get('title', '').strip()
        message = request.form.get('message', '').strip()
        notif_type = request.form.get('type', 'promo')
        link = request.form.get('link', '').strip() or None

        if not title or not message:
            flash('Title and message are required to broadcast a notification.', 'error')
            return redirect(url_for('admin.notifications'))

        recipient_id = target_user_id if target == 'single' else None
        notif = DBService.create_user_notification(
            user_id=recipient_id,
            title=title,
            message=message,
            type=notif_type,
            link=link
        )
        if notif:
            target_desc = f"user ({recipient_id})" if recipient_id else "all registered users"
            flash(f"Notification successfully pushed to {target_desc}!", 'success')
        else:
            flash('Failed to dispatch notification.', 'error')
        return redirect(url_for('admin.notifications'))

    all_notifs = DBService.get_all_notifications_admin(limit=50)
    all_users = DBService.get_all_users_admin()
    return render_template(
        'admin/notifications.html',
        notifications=all_notifs,
        users=all_users,
        active_page='notifications'
    )


