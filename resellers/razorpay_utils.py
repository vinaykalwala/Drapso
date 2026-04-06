# resellers/razorpay_utils.py

import razorpay
import random
import string
from django.conf import settings
from django.utils import timezone

# Initialize Razorpay client
razorpay_client = razorpay.Client(
    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
)

def create_razorpay_order(amount, currency="INR"):
    """Create order in Razorpay"""
    order_data = {
        'amount': int(amount * 100),  # Convert to paise
        'currency': currency,
        'payment_capture': 1  # Auto capture
    }
    order = razorpay_client.order.create(data=order_data)
    return order

def generate_order_id():
    """Generate unique order ID"""
    timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
    random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"ORD{timestamp}{random_str}"

def verify_payment_signature(order_id, payment_id, signature):
    """Verify Razorpay payment signature"""
    params_dict = {
        'razorpay_order_id': order_id,
        'razorpay_payment_id': payment_id,
        'razorpay_signature': signature
    }
    try:
        razorpay_client.utility.verify_payment_signature(params_dict)
        return True
    except:
        return False