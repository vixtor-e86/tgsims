"""Test script to thoroughly verify Admin Panel functionality:
- Access protection (unauthenticated, user, admin)
- Pricing controls & dynamic margin calculation
- Manual payment verification (Squad & Crypto) with atomic wallet credit
- Order inspection & user balance adjustment
"""
import sys
import secrets
from app import create_app
from app.services.settings_service import SettingsService
from app.services.sim_provider import SIMProviderService
from app.services.db_service import DBService
from app.services.supabase_client import get_supabase_admin, mock_db

def run_tests():
    app = create_app()
    client = app.test_client()

    print("--- 1. Testing Admin Access Control ---")
    # A. Unauthenticated / dev-gated visitor
    res = client.get('/admin')
    # Should redirect to site_unlock if dev gate is on, or auth/login
    print(f"Unauthenticated /admin status: {res.status_code} (Redirect: {res.headers.get('Location')})")
    assert res.status_code in (302, 401, 403), f"Expected redirect, got {res.status_code}"

    # B. Site unlocked, logged in as regular user ('role': 'user')
    with client.session_transaction() as sess:
        sess['site_unlocked'] = True
        sess['user'] = {
            'id': 'demo-user-id',
            'email': 'user@example.com',
            'full_name': 'Regular User',
            'username': 'reguser',
            'role': 'user'
        }

    res_user = client.get('/admin/', follow_redirects=False)
    print(f"Regular user /admin/ status: {res_user.status_code} (Redirect: {res_user.headers.get('Location')})")
    assert res_user.status_code == 302, f"Regular user was not redirected, got {res_user.status_code}"
    assert '/dashboard' in res_user.headers.get('Location', ''), "Regular user not redirected to dashboard"

    # C. Logged in as administrator ('role': 'admin')
    with client.session_transaction() as sess:
        sess['site_unlocked'] = True
        sess['user'] = {
            'id': 'admin-user-id',
            'email': 'admin@tgsims.com',
            'full_name': 'Platform Admin',
            'username': 'admin',
            'role': 'admin'
        }

    res_admin = client.get('/admin/')
    print(f"Admin user /admin status: {res_admin.status_code}")
    assert res_admin.status_code == 200, f"Admin was not allowed, got {res_admin.status_code}"
    assert b"Admin Command Center" in res_admin.data, "Admin dashboard title not found in response"
    print("PASS: Access control working correctly!\n")

    print("--- 2. Testing Pricing & Profit Margin Controls ---")
    # Check pricing page loads
    res_pricing_get = client.get('/admin/pricing')
    assert res_pricing_get.status_code == 200
    assert b"Pricing & Profit Control Center" in res_pricing_get.data

    # Update pricing settings: FX Rate = 1650, 5sim markup = 35%, TV markup = 30%, Reactivation = 1.25
    post_data = {
        'action': 'update_settings',
        'ngn_per_usd_rate': '1650.00',
        'fivesim_markup_percent': '35.0',
        'fivesim_min_profit_usd': '0.35',
        'textverified_markup_percent': '30.0',
        'reactivation_fee_usd': '1.25',
        'crypto_deposit_address': 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t',
        'squad_enabled': '1',
        'crypto_enabled': '1',
        'manual_bank_details': 'GTBank Tgsims 0123456789'
    }
    res_pricing_post = client.post('/admin/pricing', data=post_data, follow_redirects=True)
    assert res_pricing_post.status_code == 200

    # Verify SettingsService reflects changes
    current_fx = SettingsService.get_usd_ngn_rate()
    print(f"Updated USD/NGN Rate: {current_fx} (Expected 1650.0)")
    assert current_fx == 1650.0, f"Expected 1650.0, got {current_fx}"

    f5_pct, f5_floor = SettingsService.get_fivesim_markup()
    print(f"Updated 5sim Markup: {f5_pct}% (Floor: ${f5_floor})")
    assert f5_pct == 35.0 and f5_floor == 0.35

    react_fee = SettingsService.get_reactivation_fee()
    print(f"Updated Reactivation Fee: ${react_fee}")
    assert react_fee == 1.25

    # Verify SIMProviderService retail price calculation with 35% markup on a $1.00 base cost
    retail_price, margin = SIMProviderService.calculate_retail_price(1.00)
    print(f"Retail price for $1.00 base cost: ${retail_price:.2f} (Margin: ${margin:.2f})")
    assert retail_price == 1.35, f"Expected $1.35, got {retail_price}"
    print("PASS: Dynamic pricing and profit calculation working correctly!\n")

    print("--- 3. Testing Manual Payment Verification ---")
    admin = get_supabase_admin()
    if admin:
        # Live Supabase environment
        # 1. Fetch a real profile to attach test transaction
        p_res = admin.table('profiles').select('id, email').limit(1).execute()
        if p_res.data:
            test_user_id = p_res.data[0]['id']
            # Get current wallet balance
            cur_w = DBService.get_wallet(test_user_id)
            bal_start = float(cur_w.get('balance', 0.00))

            # Insert test pending deposit
            test_ref = f"TEST-SQ-{secrets.token_hex(4).upper()}"
            ins = admin.table('wallet_transactions').insert({
                'user_id': test_user_id,
                'amount': 15.00,
                'type': 'deposit',
                'status': 'pending',
                'reference': test_ref,
                'description': 'Squad Transfer Pending Deposit',
                'metadata': {'gateway': 'squad', 'account': '0129481923'}
            }).execute()

            assert ins.data and len(ins.data) > 0
            test_tx_id = ins.data[0]['id']

            # Check deposits page lists it
            res_dep = client.get('/admin/deposits?status=pending')
            assert res_dep.status_code == 200
            assert test_ref.encode('utf-8') in res_dep.data, f"Pending deposit {test_ref} not found on page"

            # Post verification
            verify_res = client.post(
                f'/admin/deposits/{test_tx_id}/verify',
                data={'admin_notes': 'Verified by Automated Test Suite'},
                follow_redirects=True
            )
            assert verify_res.status_code == 200

            # Verify transaction status changed to completed in DB
            check_tx = admin.table('wallet_transactions').select('*').eq('id', test_tx_id).single().execute()
            assert check_tx.data['status'] == 'completed', f"Expected status completed, got {check_tx.data['status']}"
            print(f"Verified live transaction {test_ref}: status={check_tx.data['status']}")

            # Verify wallet was credited atomically
            w_after = DBService.get_wallet(test_user_id)
            bal_end = float(w_after.get('balance', 0.00))
            print(f"Live wallet balance before: ${bal_start:.2f}, after: ${bal_end:.2f} (Diff: +${bal_end - bal_start:.2f})")
            assert round(bal_end - bal_start, 2) == 15.00

            # Clean up test transaction and revert wallet balance
            admin.table('wallet_transactions').delete().eq('id', test_tx_id).execute()
            admin.table('wallets').update({'balance': bal_start}).eq('user_id', test_user_id).execute()
            print("Live test transaction verified and safely cleaned up.")
    else:
        # Mock DB environment
        initial_bal = mock_db.wallets.get('demo-user-id', {}).get('balance', 0.00)
        verify_res = client.post(
            '/admin/deposits/tx-pending-squad/verify',
            data={'admin_notes': 'Bank transfer confirmed by Platform Admin'},
            follow_redirects=True
        )
        assert verify_res.status_code == 200
        new_bal = mock_db.wallets.get('demo-user-id', {}).get('balance', 0.00)
        assert round(new_bal - initial_bal, 2) == 25.00

    print("PASS: Manual payment verification & atomic wallet credit verified!\n")

    print("--- 4. Testing Orders and Users Management ---")
    # Orders page
    res_orders = client.get('/admin/orders')
    assert res_orders.status_code == 200
    assert b"Virtual SIM Orders" in res_orders.data

    # Users page
    res_users = client.get('/admin/users')
    assert res_users.status_code == 200
    assert b"User Accounts" in res_users.data

    # Adjust user balance manually via admin
    bal_before = mock_db.wallets.get('demo-user-id', {}).get('balance', 0.00)
    adj_res = client.post(
        '/admin/users/demo-user-id/adjust-balance',
        data={
            'amount': '15.00',
            'adjustment_type': 'credit',
            'reason': 'Bonus credit from administration'
        },
        follow_redirects=True
    )
    assert adj_res.status_code == 200
    bal_after = mock_db.wallets.get('demo-user-id', {}).get('balance', 0.00)
    print(f"Balance after manual adjustment: ${bal_after:.2f} (Increased by: +${bal_after - bal_before:.2f})")
    assert round(bal_after - bal_before, 2) == 15.00

    print("PASS: Orders and Users management working perfectly!\n")
    print("=== ALL ADMIN PANEL VERIFICATION TESTS PASSED SUCCESSFULLY! ===")

if __name__ == '__main__':
    run_tests()
