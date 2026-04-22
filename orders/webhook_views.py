# orders/webhook_views.py

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
import json
import hmac
import hashlib
import logging

from .models import Order, ReturnRequest

logger = logging.getLogger(__name__)


# ===============================
# 🔥 STATUS MAPPING (CORE LOGIC)
# ===============================
def map_shiprocket_status(status):
    status = (status or '').lower().strip()

    mapping = {
        # Forward flow
        'pickup scheduled': 'shipped',
        'picked up': 'shipped',
        'manifest generated': 'shipped',
        'in transit': 'shipped',

        'out for delivery': 'out_for_delivery',
        'delivered': 'delivered',

        # Returns / RTO
        'rto initiated': 'return_requested',
        'rto in transit': 'return_requested',
        'rto delivered': 'cancelled',

        # Failures
        'lost': 'cancelled',
        'damaged': 'cancelled',
        'cancelled': 'cancelled',
    }

    return mapping.get(status)


# ===============================
# 🔥 MAIN WEBHOOK ENTRY
# ===============================
@csrf_exempt
@require_http_methods(["POST"])
def shiprocket_webhook(request):
    payload = request.body
    signature = request.headers.get('X-Shiprocket-Signature')

    # --- Signature verification (optional but recommended) ---
    if signature and hasattr(settings, 'SHIPROCKET_WEBHOOK_SECRET'):
        expected = hmac.new(
            settings.SHIPROCKET_WEBHOOK_SECRET.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature, expected):
            logger.warning("❌ Invalid webhook signature")
            return JsonResponse({'error': 'Invalid signature'}, status=401)

    try:
        data = json.loads(payload)
        logger.info(f"📦 Shiprocket webhook: {data}")

        # Route based on type
        if 'new_shipping_charge' in data:
            return handle_weight_webhook(data)

        if data.get('is_return'):
            return handle_return_webhook(data)

        return handle_delivery_webhook(data)

    except Exception as e:
        logger.exception("Webhook failed")
        return HttpResponse(status=200)  # prevent retries


# ===============================
# 🔥 DELIVERY / TRACKING HANDLER
# ===============================
def handle_delivery_webhook(data):
    order_ref = data.get('order_id') or data.get('shipment_id')

    if not order_ref:
        return JsonResponse({'error': 'No reference'}, status=400)

    order = (
        Order.objects.filter(order_id=order_ref).first()
        or Order.objects.filter(shipment_id=order_ref).first()
    )

    if not order:
        logger.warning(f"⚠️ Order not found: {order_ref}")
        return JsonResponse({'status': 'ignored'}, status=200)

    current_status = (data.get('status') or '').strip()
    status_code = data.get('status_code')
    awb_code = data.get('awb_code') or order.awb_code

    print(f"\n📦 WEBHOOK STATUS: {current_status} | AWB: {awb_code}")

    # Always update tracking info
    order.last_shiprocket_status = current_status
    order.last_shiprocket_status_code = status_code
    order.awb_code = awb_code
    order.webhook_received_at = timezone.now()

    # 🔥 Map to internal status
    mapped_status = map_shiprocket_status(current_status)

    if mapped_status:
        order.add_status_history(mapped_status, {
            'shiprocket_status': current_status,
            'awb': awb_code,
            'location': data.get('location')
        })

        # Special handling
        if mapped_status == 'delivered' and not order.delivered_at:
            order.delivered_at = timezone.now()

            # Email (optional)
            try:
                send_mail(
                    subject=f"Delivered: {order.order_id}",
                    message=f"Hi {order.customer_name}, your order is delivered.",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[order.customer_email],
                    fail_silently=True,
                )
            except Exception as e:
                logger.error(f"Email failed: {e}")

    else:
        print(f"⚠️ Unmapped status: {current_status}")

    order.save()
    return JsonResponse({'status': 'success'})


# ===============================
# 🔥 WEIGHT UPDATE HANDLER
# ===============================
def handle_weight_webhook(data):
    order_ref = data.get('order_id')
    order = Order.objects.filter(order_id=order_ref).first()

    if not order:
        return JsonResponse({'status': 'not_found'}, status=200)

    new_charge = data.get('new_shipping_charge')

    if new_charge:
        order.actual_shipping_cost = float(new_charge)

        order.add_status_history('weight_audit', {
            'final_charge': new_charge
        })

        order.save()

    return JsonResponse({'status': 'success'})


# ===============================
# 🔥 RETURN HANDLER
# ===============================
def handle_return_webhook(data):
    awb = data.get('awb_code')

    return_request = ReturnRequest.objects.filter(return_awb=awb).first()

    if not return_request:
        return JsonResponse({'status': 'not_found'}, status=200)

    status = data.get('status')

    if status == 'Return Picked Up':
        return_request.status = 'picked_up'
        return_request.return_picked_up_at = timezone.now()

    elif status == 'Return Delivered':
        return_request.status = 'delivered_to_warehouse'
        return_request.return_delivered_at = timezone.now()

    return_request.save()
    return JsonResponse({'status': 'success'})

from django.http import JsonResponse
from django.utils import timezone

def webhook_health(request):
    return JsonResponse({
        'status': 'ok',
        'timestamp': timezone.now().isoformat()
    })

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from shiprocket.services import ShiprocketService
from .models import Order


@csrf_exempt
@require_http_methods(["POST"])
def sync_order_status(request, order_id):
    """
    Manual sync endpoint (backup if webhook fails)
    """
    order = get_object_or_404(Order, order_id=order_id)

    if not order.awb_code:
        return JsonResponse({'error': 'No AWB found'}, status=400)

    shiprocket = ShiprocketService()

    tracking = shiprocket.track_shipment(order.awb_code)

    print("\n🔁 MANUAL SYNC RESPONSE:")
    print(tracking)

    if not tracking or not tracking.get('data'):
        return JsonResponse({'error': 'Tracking failed'}, status=500)

    data = tracking.get('data', {})

    mock_webhook_data = {
        'order_id': order.order_id,
        'status': data.get('current_status'),
        'awb_code': order.awb_code,
        'location': data.get('location'),
    }

    # Reuse same handler (important)
    handle_delivery_webhook(mock_webhook_data)

    return JsonResponse({'status': 'synced'})