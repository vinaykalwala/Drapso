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
from shiprocket.services import ShiprocketService

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def shiprocket_webhook(request):
    """
    Handle Shiprocket webhook for shipment status updates
    """
    
    signature = request.headers.get('X-Shiprocket-Signature')
    payload = request.body
    
    if signature and hasattr(settings, 'SHIPROCKET_WEBHOOK_SECRET'):
        expected = hmac.new(
            settings.SHIPROCKET_WEBHOOK_SECRET.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected):
            logger.warning(f"Invalid webhook signature: {signature}")
            return JsonResponse({'error': 'Invalid signature'}, status=401)
    
    try:
        data = json.loads(payload)
        logger.info(f"Shiprocket webhook received: {data}")
        
        is_return = data.get('is_return', False) or 'RET' in data.get('order_id', '')
        
        if is_return:
            return handle_return_webhook(data)
        else:
            return handle_delivery_webhook(data)
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in webhook: {e}")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        return HttpResponse(status=200)


def handle_delivery_webhook(data):
    """Handle delivery webhook for forward shipments"""
    
    order_ref = data.get('order_id') or data.get('shipment_id')
    
    if not order_ref:
        logger.error("No order reference in webhook")
        return JsonResponse({'error': 'No order reference'}, status=400)
    
    order = None
    if order_ref.startswith('ORD'):
        order = Order.objects.filter(order_id=order_ref).first()
    else:
        order = Order.objects.filter(shipment_id=order_ref).first()
    
    if not order:
        logger.warning(f"Order not found for reference: {order_ref}")
        return JsonResponse({'status': 'order_not_found'}, status=200)
    
    current_status = data.get('status', '')
    status_code = data.get('status_code', '')
    awb_code = data.get('awb_code', order.awb_code)
    
    # Update based on status
    if current_status == 'Delivered':
        order.order_status = 'delivered'
        order.delivered_at = timezone.now()
        order.add_status_history('delivered', {
            'shiprocket_status': current_status,
            'location': data.get('location', ''),
            'delivered_time': data.get('delivered_time')
        })
        order.save()
        
        send_mail(
            subject=f'Order Delivered - {order.order_id}',
            message=f"""
Dear {order.customer_name},

Your order has been DELIVERED! 🎉

📦 Order Details:
• Order ID: {order.order_id}
• Product: {order.product.name}
• Delivered On: {order.delivered_at.strftime('%B %d, %Y at %I:%M %p')}

We hope you love your purchase!

📸 Need to return?
If you need to request a return, please do so within 7 days of delivery.

Request Return: {settings.SITE_URL}/orders/return/{order.order_id}/request/

Thank you for shopping with us!

Regards,
Drapso Team
            """,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.customer_email],
            fail_silently=False,
        )
        
    elif current_status == 'Out for Delivery':
        order.order_status = 'out_for_delivery'
        order.add_status_history('out_for_delivery', {'location': data.get('location', '')})
        order.save()
        
        send_mail(
            subject=f'Order Out for Delivery - {order.order_id}',
            message=f"""
Dear {order.customer_name},

Great news! Your order is OUT FOR DELIVERY! 🚚

📦 Order Details:
• Order ID: {order.order_id}
• Product: {order.product.name}
• Estimated Delivery: Today

Please ensure someone is available to receive the package.

Track your delivery: {settings.SITE_URL}/orders/track/{order.order_id}/

Regards,
Drapso Team
            """,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.customer_email],
            fail_silently=False,
        )
        
    elif current_status == 'In Transit' and order.order_status == 'approved':
        order.order_status = 'shipped'
        order.shipped_at = timezone.now()
        order.add_status_history('shipped', {'awb': order.awb_code})
        order.save()
        
    elif current_status in ['RTO Initiated', 'RTO Delivered']:
        order.order_status = 'cancelled'
        order.add_status_history('rto', {'reason': current_status})
        order.save()
    
    # Always update tracking info
    order.last_shiprocket_status = current_status
    order.last_shiprocket_status_code = status_code
    order.awb_code = awb_code or order.awb_code
    order.webhook_received_at = timezone.now()
    order.save()
    
    return JsonResponse({'status': 'success', 'order_status': order.order_status})


def handle_return_webhook(data):
    """Handle webhook for return shipments"""
    
    return_awb = data.get('awb_code')
    
    if not return_awb:
        logger.error("No return AWB in webhook")
        return JsonResponse({'error': 'No return AWB'}, status=400)
    
    return_request = ReturnRequest.objects.filter(return_awb=return_awb).first()
    
    if not return_request:
        logger.warning(f"Return request not found for AWB: {return_awb}")
        return JsonResponse({'status': 'not_found'}, status=200)
    
    current_status = data.get('status', '')
    
    if current_status == 'Return Picked Up':
        return_request.return_pickup_completed = True
        return_request.return_picked_up_at = timezone.now()
        return_request.status = 'picked_up'
        return_request.save()
        
        send_mail(
            subject=f'Return Pickup Completed - {return_request.order.order_id}',
            message=f"""
Dear {return_request.order.customer_name},

Your return package has been picked up! 🚚

📦 Return Details:
• Return AWB: {return_request.return_awb}
• Pickup Time: {return_request.return_picked_up_at.strftime('%B %d, %Y at %I:%M %p')}

Your return is now on its way to the warehouse for inspection.

Track your return: {settings.SITE_URL}/orders/return/track/{return_request.id}/

Regards,
Drapso Team
            """,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[return_request.order.customer_email],
            fail_silently=False,
        )
        
    elif current_status == 'Return Delivered':
        return_request.return_delivered_at = timezone.now()
        return_request.status = 'delivered_to_warehouse'
        return_request.save()
        
        # Notify reseller that product is received
        send_mail(
            subject=f'Return Product Received - {return_request.order.order_id}',
            message=f"""
Dear {return_request.order.reseller.first_name},

The returned product for Order {return_request.order.order_id} has been received at the warehouse.

📦 Return Details:
• Product: {return_request.order.product.name}
• Return AWB: {return_request.return_awb}
• Received At: {return_request.return_delivered_at.strftime('%B %d, %Y at %I:%M %p')}

Please inspect the product and initiate refund if applicable.

Regards,
Drapso Team
            """,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[return_request.order.reseller.email],
            fail_silently=False,
        )
    
    return_request.save()
    
    return JsonResponse({'status': 'success', 'return_status': return_request.status})


@csrf_exempt
def webhook_health(request):
    """Health check endpoint for webhook configuration"""
    return JsonResponse({'status': 'healthy', 'timestamp': timezone.now().isoformat()})


@csrf_exempt
@require_http_methods(["POST"])
def sync_order_status(request, order_id):
    """Manually sync order status from Shiprocket"""
    from django.shortcuts import get_object_or_404
    
    order = get_object_or_404(Order, order_id=order_id)
    
    if not order.awb_code:
        return JsonResponse({'error': 'No AWB code found'}, status=400)
    
    shiprocket = ShiprocketService()
    tracking_info = shiprocket.track_shipment(order.awb_code)
    
    if tracking_info and tracking_info.get('data'):
        data = tracking_info['data']
        current_status = data.get('current_status', '')
        
        # Create mock webhook data
        mock_data = {
            'order_id': order.order_id,
            'shipment_id': order.shipment_id,
            'awb_code': order.awb_code,
            'status': current_status,
            'status_code': data.get('status_code', ''),
            'location': data.get('location', ''),
            'remarks': data.get('remarks', '')
        }
        
        handle_delivery_webhook(mock_data)
        
        return JsonResponse({
            'status': 'synced',
            'order_status': order.order_status,
            'shiprocket_status': current_status
        })
    
    return JsonResponse({'error': 'Failed to sync'}, status=500)