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
from shiprocket.services import ShiprocketService
from settlement.services import DrapsoSettlementService  # Import the service

logger = logging.getLogger(__name__)

# orders/webhook_views.py

def map_shiprocket_status(shiprocket_status):
    """
    Map Shiprocket status to internal order status
    """
    status_mapping = {
        # Active/In-transit statuses
        "Pending": "approved",
        "Confirmed": "approved",
        "Packed": "approved",
        "Manifested": "shipped",
        "Picked Up": "shipped",
        "Out For Delivery": "out_for_delivery",
        "Out for delivery": "out_for_delivery",
        
        # Delivery statuses
        "Delivered": "delivered",
        "Delivered successfully": "delivered",
        
        # Cancellation statuses
        "CANCELED": "cancelled",
        "CANCELLED": "cancelled",
        "CANCELLATION REQUESTED": "cancelled",
        "Cancelled": "cancelled",
        "Canceled": "cancelled",
        
        # Return statuses
        "RTO": "cancelled",
        "Return to Origin": "cancelled",
    }
    
    # Handle case-insensitive matching
    if shiprocket_status:
        status_upper = shiprocket_status.upper()
        for key, value in status_mapping.items():
            if key.upper() == status_upper:
                return value
    
    return status_mapping.get(shiprocket_status, None)
    
@csrf_exempt
@require_http_methods(["POST"])
def shiprocket_webhook(request):
    payload = request.body
    signature = request.headers.get('X-Shiprocket-Signature')

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

        if 'new_shipping_charge' in data:
            return handle_weight_webhook(data)

        if data.get('is_return'):
            return handle_return_webhook(data)

        return handle_delivery_webhook(data)

    except Exception as e:
        logger.exception("Webhook failed")
        return HttpResponse(status=200)

# ===============================
# 🔥 DELIVERY HANDLER
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

    order.last_shiprocket_status = current_status
    order.last_shiprocket_status_code = status_code
    order.awb_code = awb_code
    order.webhook_received_at = timezone.now()

    mapped_status = map_shiprocket_status(current_status)

    if mapped_status:
        order.add_status_history(mapped_status, {
            'shiprocket_status': current_status,
            'awb': awb_code,
            'location': data.get('location')
        })

        if mapped_status == 'delivered' and not order.delivered_at:
            order.delivered_at = timezone.now()

            # 🔥 FETCH FINAL SHIPPING COST & RECALCULATE SETTLEMENT
            try:
                shiprocket = ShiprocketService()
                shipment_result = shiprocket.get_order_by_shipment_id(order.shipment_id)

                if shipment_result.get("success"):
                    shipment = shipment_result.get("shipment", {})
                    freight = shipment.get("awb_data", {}).get("charges", {}).get("freight_charges")

                    if freight:
                        order.actual_shipping_cost = float(freight)
                        order.save()
                        # 💰 Update financial records
                        DrapsoSettlementService.recalculate_after_shipping(order)
                    else:
                        recalculated = recalculate_shipping_cost(order)
                        if recalculated:
                            order.actual_shipping_cost = recalculated
                            order.save()
                            # 💰 Update financial records
                            DrapsoSettlementService.recalculate_after_shipping(order)

            except Exception as e:
                logger.error(f"Cost fetch/settlement update failed: {e}")

            # Delivery Email
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

    order.save()
    return JsonResponse({'status': 'success'})

# ===============================
# 🔥 WEIGHT WEBHOOK (SETTLEMENT INTEGRATED)
# ===============================
def handle_weight_webhook(data):
    order_ref = data.get('order_id')
    order = Order.objects.filter(order_id=order_ref).first()

    if not order:
        return JsonResponse({'status': 'not_found'}, status=200)

    new_charge = data.get('new_shipping_charge')
    if new_charge:
        order.actual_shipping_cost = float(new_charge)
        order.add_status_history('weight_audit', {'final_charge': new_charge})
        order.save()

        # 🔥 UPDATE SETTLEMENT FOR WEIGHT CHANGES
        try:
            DrapsoSettlementService.recalculate_after_shipping(order)
            logger.info(f"⚖️ Weight Audit: Settlement updated for {order_ref}")
        except Exception as e:
            logger.error(f"Settlement update failed during weight audit: {e}")

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

# ===============================
# 🔥 UTILITIES & MANUAL SYNC
# ===============================
def recalculate_shipping_cost(order):
    try:
        shiprocket = ShiprocketService()
        result = shiprocket.get_order_by_shipment_id(order.shipment_id)
        if not result.get("success"): return None

        shipment = result.get("shipment", {})
        weight = shipment.get("applied_weight") or shipment.get("weight")
        courier_name = shipment.get("courier_name")

        rate_result = shiprocket.get_shipping_rate(order.pickup_pincode, order.delivery_pincode, weight)
        if not rate_result.get("success"): return None

        for courier in rate_result["data"]:
            if courier["courier_name"] == courier_name:
                return float(courier["rate"])
    except Exception as e:
        logger.error(f"Recalculation failed: {e}")
    return None

def sync_order_status(request, order_id):
    from django.shortcuts import redirect, get_object_or_404
    from django.contrib import messages

    shiprocket = ShiprocketService()
    order = get_object_or_404(Order, order_id=order_id)

    try:
        result = shiprocket.get_order_by_shiprocket_id(order.shiprocket_order_id)
        if not result.get("success"):
            messages.error(request, "Failed to sync order")
            return redirect(request.META.get('HTTP_REFERER', '/'))

        sr_order = result.get("order", {})
        shipments = sr_order.get("shipments", [])
        shipment = shipments[0] if isinstance(shipments, list) and shipments else (shipments or {})

        order.last_shiprocket_status = sr_order.get("status")
        order.awb_code = shipment.get("awb") or order.awb_code

        freight = shipment.get("awb_data", {}).get("charges", {}).get("freight_charges")
        if freight:
            order.actual_shipping_cost = float(freight)
            order.save()
            # 🔥 MANUAL SYNC SETTLEMENT TRIGGER
            DrapsoSettlementService.recalculate_after_shipping(order)

        order.save()
        messages.success(request, "Order synced successfully with updated settlement")
    except Exception as e:
        messages.error(request, f"Sync failed: {str(e)}")

    return redirect(request.META.get('HTTP_REFERER', '/'))

# ===============================
# 🔥 HEALTH CHECK
# ===============================
def webhook_health(request):
    return JsonResponse({
        'status': 'ok',
        'timestamp': timezone.now().isoformat()
    })