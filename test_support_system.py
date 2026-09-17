"""Automated verification test suite for Support Ticket System in Tgsims."""
import unittest
from app import create_app
from app.services.db_service import DBService
from app.services.supabase_client import mock_db

class TestSupportSystem(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_01_db_create_ticket_and_messages(self):
        """Verify DBService creates support tickets, messages, and notifications correctly."""
        user_id = "test-user-123"
        subject = "Issue receiving Telegram SMS code"
        msg = "I ordered a UK number but have not gotten any OTP."
        
        ticket = DBService.create_support_ticket(
            user_id=user_id,
            subject=subject,
            initial_message=msg,
            category="virtual_sim",
            user_name="John Doe",
            user_email="john@example.com"
        )

        self.assertIsNotNone(ticket)
        self.assertTrue(ticket['ticket_number'].startswith('TK-'))
        self.assertEqual(ticket['subject'], subject)
        self.assertEqual(ticket['status'], 'open')

        # Check messages
        messages = DBService.get_ticket_messages(ticket['id'], user_id=user_id, is_admin=False)
        self.assertTrue(len(messages) >= 1)
        self.assertEqual(messages[0]['message'], msg)

        # Admin replies
        reply = DBService.add_support_message(
            ticket_id=ticket['id'],
            sender_id="admin-1",
            sender_name="Admin Tunde",
            sender_role="admin",
            message="We are checking with the carrier. One moment please."
        )
        self.assertIsNotNone(reply)

        # Check unread counts for user
        unread = DBService.get_user_support_unread(user_id)
        self.assertTrue(unread['unread_total'] >= 1)

        # User reads messages
        messages_after = DBService.get_ticket_messages(ticket['id'], user_id=user_id, is_admin=False, mark_read=True)
        self.assertEqual(len(messages_after), 2)

        # Update status to resolved
        status_res = DBService.update_ticket_status(ticket['id'], 'resolved', actor_role='admin', actor_name='Admin Tunde')
        self.assertTrue(status_res['success'])

        ticket_refreshed = DBService.get_ticket_by_id(ticket['id'], is_admin=True)
        self.assertEqual(ticket_refreshed['status'], 'resolved')

    def test_02_api_support_endpoints(self):
        """Verify API endpoints for user tickets, messaging, unread polling, and admin actions."""
        with self.client.session_transaction() as sess:
            sess['site_unlocked'] = True
            sess['user'] = {
                'id': 'api-test-user',
                'email': 'apitest@example.com',
                'full_name': 'API Tester',
                'role': 'user'
            }

        # 1. Unread count endpoint
        res = self.client.get('/api/support/unread')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('unread_total', data)

        # 2. Create ticket without subject should fail
        fail_res = self.client.post('/api/support/tickets', json={'subject': '', 'message': 'hello'})
        self.assertEqual(fail_res.status_code, 400)

        # 3. Create ticket with subject
        create_res = self.client.post('/api/support/tickets', json={
            'subject': 'Wallet payment confirmation delay',
            'message': 'I completed a bank transfer 15 minutes ago.',
            'category': 'deposit'
        })
        self.assertEqual(create_res.status_code, 201)
        ticket_data = create_res.get_json()
        self.assertTrue(ticket_data['success'])
        ticket_id = ticket_data['ticket']['id']

        # 4. User sends message
        msg_res = self.client.post(f'/api/support/tickets/{ticket_id}/messages', json={
            'message': 'Here is the transaction reference: SQ-12345'
        })
        self.assertEqual(msg_res.status_code, 200)

        # 5. Admin access test: login as admin
        with self.client.session_transaction() as sess:
            sess['site_unlocked'] = True
            sess['user'] = {
                'id': 'admin-tester-id',
                'email': 'admin@tgsims.com',
                'full_name': 'Chief Admin',
                'role': 'admin'
            }

        admin_tickets_res = self.client.get('/api/admin/support/tickets')
        self.assertEqual(admin_tickets_res.status_code, 200)

        # Admin replies
        admin_reply_res = self.client.post(f'/api/admin/support/tickets/{ticket_id}/messages', json={
            'message': 'Payment verified and credited to your wallet!'
        })
        self.assertEqual(admin_reply_res.status_code, 200)

        # Admin updates status to resolved
        status_res = self.client.post(f'/api/admin/support/tickets/{ticket_id}/status', json={
            'status': 'resolved'
        })
        self.assertEqual(status_res.status_code, 200)
        self.assertTrue(status_res.get_json()['success'])

        # Check admin support page renders
        page_res = self.client.get('/admin/support')
        self.assertEqual(page_res.status_code, 200)
        self.assertIn(b'Support Desk', page_res.data)


if __name__ == '__main__':
    unittest.main()
