import random
import uuid

class PaymentService:
    """Service adapter for Payment Gateways (Paystack, Flutterwave, Stripe)."""

    @staticmethod
    def initialize_deposit(user_id, amount, gateway='paystack'):
        """Creates a payment deposit intent/checkout URL."""
        ref = f"DEP-{uuid.uuid4().hex[:8].upper()}"
        return {
            'success': True,
            'reference': ref,
            'amount': amount,
            'currency': 'USD',
            'gateway': gateway,
            'checkout_url': f"/wallet/checkout-demo?ref={ref}&amount={amount}"
        }

    @staticmethod
    def verify_payment(reference):
        """Simulates payment verification callback."""
        return {
            'success': True,
            'status': 'completed',
            'reference': reference
        }
