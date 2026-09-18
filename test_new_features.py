import unittest
from app import create_app
from app.services.db_service import DBService

class TestNewFeatures(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_account_alias_routes_no_404(self):
        # Site unlocked, unauthenticated user
        with self.client.session_transaction() as sess:
            sess['site_unlocked'] = True

        r_support = self.client.get('/account/support')
        self.assertEqual(r_support.status_code, 302, "/account/support must redirect to login, not 404")
        self.assertTrue('/login' in r_support.headers.get('Location', ''))

        r_settings = self.client.get('/account/settings')
        self.assertEqual(r_settings.status_code, 302, "/account/settings must redirect to login, not 404")

        r_referral = self.client.get('/account/referral')
        self.assertEqual(r_referral.status_code, 302, "/account/referral must redirect to login, not 404")

    def test_user_notification_system_and_api(self):
        test_uid = "00000000-0000-0000-0000-000000000001"
        
        # 1. Create notification via DBService
        notif = DBService.create_user_notification(
            user_id=test_uid,
            title="Deposit Confirmed",
            message="Your deposit of $25.00 has been credited.",
            type="deposit",
            link="/wallet"
        )
        self.assertIsNotNone(notif)
        self.assertEqual(notif['title'], "Deposit Confirmed")

        # 2. Get user notifications
        notifs = DBService.get_user_notifications(test_uid)
        self.assertTrue(any(n['title'] == "Deposit Confirmed" for n in notifs))

        # 3. Simulate authenticated user session
        with self.client.session_transaction() as sess:
            sess['site_unlocked'] = True
            sess['user'] = {'id': test_uid, 'email': 'user@example.com', 'role': 'user'}

        resp = self.client.get('/api/notifications/unread')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))
        self.assertGreaterEqual(data.get('unread_count', 0), 1)

        # 4. Mark read
        resp_read = self.client.post('/api/notifications/read', json={'notification_id': notif['id']})
        self.assertEqual(resp_read.status_code, 200)
        self.assertTrue(resp_read.get_json().get('success'))

    def test_admin_push_notifications(self):
        admin_uid = "00000000-0000-0000-0000-000000000002"
        with self.client.session_transaction() as sess:
            sess['site_unlocked'] = True
            sess['user'] = {'id': admin_uid, 'email': 'admin@example.com', 'role': 'admin'}

        # GET notifications page
        get_res = self.client.get('/admin/notifications')
        self.assertEqual(get_res.status_code, 200)
        self.assertIn(b'Push Notifications &amp; Broadcasts', get_res.data)

        # POST broadcast notification
        post_res = self.client.post('/admin/notifications', data={
            'target_audience': 'all',
            'type': 'promo',
            'title': 'Weekend 20% Bonus Promo',
            'message': 'Enjoy 20% extra credits on all deposits this weekend!',
            'link': '/wallet'
        }, follow_redirects=True)
        self.assertEqual(post_res.status_code, 200)
        self.assertIn(b'Weekend 20% Bonus Promo', post_res.data)

if __name__ == '__main__':
    unittest.main()
