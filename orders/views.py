# orders/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import razorpay
import json
import math
import logging
from django.db import transaction 

from .models import Order, ReturnRequest, Refund
from .forms import CheckoutForm, ReturnRequestForm, RefundForm
from shiprocket.services import ShiprocketService
from products.models import *
from resellers.models import Store
from accounts.models import WholesellerAddress, ResellerAddress

logger = logging.getLogger(__name__)

# Initialize Razorpay client
razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def is_reseller(user):
    return user.is_authenticated and user.role == 'reseller'


def is_wholeseller(user):
    return user.is_authenticated and user.role == 'wholeseller'


def is_admin(user):
    return user.is_authenticated and (user.is_staff or user.role == 'admin')


def get_pickup_address(product, store):
    """Determine pickup address based on product source type"""
    
    # For imported products (from wholeseller)
    if product.source_type == 'imported' and product.source_product:
        wholeseller_address = WholesellerAddress.objects.filter(
            user=product.source_product.wholeseller,
            is_primary=True,
            is_active=True
        ).first()
        
        if wholeseller_address:
            # Build complete address string
            address_parts = [
                wholeseller_address.address_line1,
                wholeseller_address.address_line2 or '',
                f"{wholeseller_address.city}, {wholeseller_address.state} - {wholeseller_address.postal_code}"
            ]
            full_address = '\n'.join([part for part in address_parts if part])
            
            return {
                'type': 'wholeseller',
                'address': full_address,
                'pincode': wholeseller_address.postal_code,
                'contact_person': wholeseller_address.contact_person,
                'contact_phone': wholeseller_address.contact_phone,
            }
    
    # For reseller's own products
    reseller_address = ResellerAddress.objects.filter(
        user=store.reseller,
        is_primary=True
    ).first()
    
    if reseller_address:
        # Build complete address string
        address_parts = [
            reseller_address.address_line1,
            reseller_address.address_line2 or '',
            f"{reseller_address.city}, {reseller_address.state} - {reseller_address.postal_code}"
        ]
        full_address = '\n'.join([part for part in address_parts if part])
        
        return {
            'type': 'reseller',
            'address': full_address,
            'pincode': reseller_address.postal_code,
            'contact_person': reseller_address.contact_person,
            'contact_phone': reseller_address.contact_phone,
        }
    
    # Fallback to store address
    if store.address and store.pincode:
        return {
            'type': 'reseller',
            'address': store.address,
            'pincode': store.pincode,
            'contact_person': store.reseller.get_full_name() if store.reseller else '',
            'contact_phone': store.reseller.phone if store.reseller else '',
        }
    
    return None

def get_pickup_location_name_by_pincode(pincode):
    """Helper to get pickup location tag name from pincode for Shiprocket"""
    try:
        shiprocket = ShiprocketService()
        return shiprocket.get_pickup_location_by_pincode(pincode)
    except Exception as e:
        logger.error(f"Error getting pickup location for pincode {pincode}: {str(e)}")
        return None

def calculate_shipping_internal(pickup_postcode, delivery_postcode, weight):
    """Internal fallback calculation for Prepaid orders"""
    try:
        weight = float(weight)
    except (ValueError, TypeError):
        weight = 0.5
    
    if pickup_postcode == delivery_postcode:
        base_rate = 40
        zone = "Local"
    elif pickup_postcode[:3] == delivery_postcode[:3]:
        base_rate = 50
        zone = "Same City"
    elif pickup_postcode[:2] == delivery_postcode[:2]:
        base_rate = 70
        zone = "Same State"
    else:
        base_rate = 90
        zone = "Different State"
    
    if weight <= 0.5:
        weight_charge = 0
    elif weight <= 1:
        weight_charge = 20
    else:
        extra_kg = weight - 1
        weight_charge = 20 + (extra_kg * 25)
    
    total = base_rate + weight_charge
    total = max(40, min(total, 350))
    
    return {
        'shipping_charge': math.ceil(total),
        'delivery_time': "3-5 days",
        'courier_name': 'Standard Delivery',
        'is_cod_available': False, # Strictly False
        'calculation_method': 'internal'
    }


@require_http_methods(["GET"])
def calculate_shipping(request):
    """AJAX endpoint for Prepaid shipping - Cheapest Courier Only"""
    product_id = request.GET.get('product_id')
    variant_id = request.GET.get('variant_id')
    pincode = request.GET.get('pincode')
    quantity = int(request.GET.get('quantity', 1))
    store_id = request.GET.get('store_id')
    
    if not all([product_id, pincode, store_id]):
        return JsonResponse({'error': 'Missing required parameters'}, status=400)
    
    try:
        product = ResellerProduct.objects.get(id=product_id, is_active=True)
        store = Store.objects.get(id=store_id)
        pickup_info = get_pickup_address(product, store)
        
        if not pickup_info:
            return JsonResponse({'error': 'Pickup address not configured'}, status=400)

        variant = None
        if variant_id and variant_id not in ['null', 'undefined', '']:
            variant = ResellerProductVariant.objects.filter(id=variant_id, is_active=True).first()

        # Calculate metrics
        weight = float(getattr(variant or product, 'weight', 0.5)) * quantity
        product_price = float(variant.selling_price if variant else product.selling_price)
        total_product_price = product_price * quantity
        
        # Get Shiprocket location nickname
        pickup_location_name = get_pickup_location_name_by_pincode(pickup_info['pincode'])
        
        shiprocket = ShiprocketService()
        result = shiprocket.calculate_shipping_charge(
            pickup_postcode=pickup_info['pincode'],
            delivery_postcode=pincode,
            weight=weight,
            pickup_location=pickup_location_name
        )
        
        # Check if we got a valid service from Shiprocket
        if result and result.get('shipping_charge', 0) > 0:
            shipping_charge = result.get('shipping_charge')
            delivery_time = result.get('delivery_time')
            courier_name = result.get('courier_name')
            
            # Calculate estimated delivery date
            from datetime import datetime, timedelta
            estimated_delivery_date = (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d')
            
            # Return complete response with pickup information
            return JsonResponse({
                'success': True,
                'product_price': round(product_price, 2),
                'total_product_price': round(total_product_price, 2),
                'shipping_charge': round(shipping_charge, 2),
                'total_amount': round(total_product_price + shipping_charge, 2),
                'delivery_time': delivery_time,
                'courier_name': courier_name,
                # CRITICAL: Add these pickup fields for the frontend
                'pickup_address': pickup_info.get('address', ''),
                'pickup_pincode': pickup_info.get('pincode', ''),
                'pickup_location_type': pickup_info.get('type', ''),
                'etd_date': estimated_delivery_date,  # Estimated delivery date
            })
        else:
            # NO FALLBACK: Return error if Shiprocket has no services
            return JsonResponse({
                'success': False,
                'error': 'Delivery not available for this location.',
                'message': 'No courier partners service this pincode currently.'
            }, status=200)
        
    except Exception as e:
        logger.exception("Shipping calculation failed")
        return JsonResponse({'error': 'An error occurred while checking serviceability.'}, status=500)

import json
import base64

from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder
from django.conf import settings
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt

import base64, json
from django.core.serializers.json import DjangoJSONEncoder

def create_order(request, store_id, product_id):
    store = get_object_or_404(Store, id=store_id, is_published=True)
    product = get_object_or_404(ResellerProduct, id=product_id, store=store, is_active=True)
    
    variant_id = request.GET.get('variant_id')
    variant = ResellerProductVariant.objects.filter(id=variant_id, product=product, is_active=True).first() if variant_id else None

    if request.method == 'POST':
        form = CheckoutForm(request.POST)
        if form.is_valid():
            quantity = form.cleaned_data['quantity']
            # CONSISTENT KEY: product_price
            product_price = float(variant.selling_price if variant else product.selling_price)
            
            shipping_charge = float(request.POST.get('shipping_charge', 0))
            total_amount = (product_price * quantity) + shipping_charge
            
            order_data = {
                'form_data': form.cleaned_data,
                'product_id': product.id,
                'variant_id': variant.id if variant else None,
                'quantity': quantity,
                'product_price': product_price,  # Critical Fix
                'shipping_charge': shipping_charge,
                'total_amount': total_amount,
                'amount_paise': int(total_amount * 100),
                'courier_name': request.POST.get('courier_name'),
                'estimated_delivery_date': request.POST.get('estimated_delivery_date'),
                'pickup_address': request.POST.get('pickup_address'),
                'pickup_pincode': request.POST.get('pickup_pincode'),
                'pickup_address_type': request.POST.get('pickup_address_type'),
            }
            
            encoded_data = base64.urlsafe_b64encode(json.dumps(order_data, cls=DjangoJSONEncoder).encode()).decode()
            
            razorpay_order = razorpay_client.order.create({
                'amount': int(total_amount * 100),
                'currency': 'INR',
                'payment_capture': 1,
            })
            
            main_host = getattr(settings, 'MAIN_WEBSITE_URL', 'localhost:8000')
            protocol = "https" if request.is_secure() else "http"
            redirect_url = f"{protocol}://{main_host}/orders/pay-securely/{razorpay_order['id']}/{encoded_data}/"
            
            return redirect(redirect_url)
    else:
        form = CheckoutForm(initial={'quantity': 1})
    
    return render(request, 'orders/checkout.html', {
        'form': form, 'product': product, 'variant': variant, 'store': store
    })

from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
import logging

logger = logging.getLogger(__name__)

def central_payment(request, razorpay_order_id, encoded_data=None):
    if not encoded_data: return redirect('home')

    try:
        decoded_data = base64.urlsafe_b64decode(encoded_data).decode()
        payment_data = json.loads(decoded_data)
    except:
        return redirect('home')
    
    product = ResellerProduct.objects.filter(id=payment_data.get('product_id')).first()
    
    context = {
        'razorpay_order_id': razorpay_order_id,
        'razorpay_key_id': settings.RAZORPAY_KEY_ID,
        'amount': payment_data['total_amount'],
        'amount_paise': payment_data['amount_paise'],
        'form_data': payment_data['form_data'],
        'product_id': payment_data['product_id'],
        'variant_id': payment_data['variant_id'],
        'quantity': payment_data['quantity'],
        'product_price': payment_data.get('product_price', 0), # Pass to template
        'shipping_charge': payment_data['shipping_charge'],
        'courier_name': payment_data.get('courier_name'),
        'estimated_delivery_date': payment_data.get('estimated_delivery_date'),
        'pickup_address': payment_data.get('pickup_address'),
        'pickup_pincode': payment_data.get('pickup_pincode'),
        'pickup_address_type': payment_data.get('pickup_address_type'),
        'store': product.store if product else None,
    }
    return render(request, 'orders/payment.html', context)

from django.db.models import F
@csrf_exempt
def payment_success(request):
    if request.method != 'POST':
        return redirect('home')

    # Capture Razorpay Response
    params_dict = {
        'razorpay_order_id': request.POST.get('razorpay_order_id'),
        'razorpay_payment_id': request.POST.get('razorpay_payment_id'),
        'razorpay_signature': request.POST.get('razorpay_signature')
    }
    
    try:
        # 1. Verify Payment Signature
        razorpay_client.utility.verify_payment_signature(params_dict)
        
        with transaction.atomic():
            # Helper to handle 'None' or empty strings from JavaScript/Hidden Inputs
            def get_clean(key, default=None):
                val = request.POST.get(key)
                if val in ['None', '', 'null', 'undefined', None]:
                    return default
                return val

            product_id = request.POST.get('product_id')
            variant_id = get_clean('variant_id')
            quantity = int(request.POST.get('quantity', 1))

            # Fetch the Reseller Product (Locked for update)
            rp = ResellerProduct.objects.select_for_update().get(id=product_id)

            # 2. STOCK DEDUCTION LOGIC
            if rp.source_type == 'imported':
                if variant_id:
                    # Deduct from Wholeseller Variant
                    rv = get_object_or_404(ResellerProductVariant, id=variant_id, product=rp)
                    if rv.source_variant:
                        source_v = WholesellerProductVariant.objects.select_for_update().get(id=rv.source_variant.id)
                        source_v.stock = F('stock') - quantity
                        source_v.save()
                else:
                    # Deduct from Wholeseller Main Product
                    source_p = WholesellerProduct.objects.select_for_update().get(id=rp.source_product.id)
                    source_p.stock = F('stock') - quantity
                    source_p.save()
            else:
                # Deduct from Reseller's OWN stock
                if variant_id:
                    own_v = ResellerProductVariant.objects.select_for_update().get(id=variant_id, product=rp)
                    own_v.stock = F('stock') - quantity
                    own_v.save()
                else:
                    rp.stock = F('stock') - quantity
                    rp.save()

            # 3. PARSING DATA
            total_amt = float(get_clean('total_amount', 0))
            ship_charge = float(get_clean('shipping_charge', 0))
            prod_price = float(get_clean('product_price', 0))
            wholeseller = rp.source_product.wholeseller if rp.source_type == 'imported' else None

            # 4. CREATE ORDER RECORD (Includes all Pickup & Logistics fields)
            order = Order.objects.create(
                razorpay_order_id=params_dict['razorpay_order_id'],
                razorpay_payment_id=params_dict['razorpay_payment_id'],
                
                # Customer Details
                customer_name=get_clean('customer_name'),
                customer_email=get_clean('customer_email'),
                customer_phone=get_clean('customer_phone'),
                shipping_address=get_clean('shipping_address'),
                shipping_city=get_clean('shipping_city'),
                shipping_state=get_clean('shipping_state'),
                shipping_pincode=get_clean('shipping_pincode'),
                
                # Product & Store Info
                product=rp,
                variant_id=variant_id,
                quantity=quantity,
                store=rp.store,
                reseller=rp.store.reseller,
                wholeseller=wholeseller,
                
                # Pricing
                product_price=prod_price,
                shipping_charge=ship_charge,
                total_amount=total_amt,
                payment_amount=total_amt, 
                
                # Logistics & Pickup Info (RESTORED)
                courier_name=get_clean('courier_name'),
                estimated_delivery_date=get_clean('estimated_delivery_date'),
                pickup_address=get_clean('pickup_address'),
                pickup_pincode=get_clean('pickup_pincode'),
                pickup_address_type=get_clean('pickup_address_type'),

                # Status
                order_status='paid',
                payment_status='success',
                paid_at=timezone.now()
            )

        return redirect('orders:order_success', order_id=order.id)

    except Exception as e:
        logger.error(f"Order Creation Failed: {str(e)}")
        return redirect('orders:payment_failed')

def _send_order_emails(order):
    """Helper to send emails after successful creation"""
    # Customer Email
    send_mail(
        subject=f'Order Confirmed - Drapso #{order.id}',
        message=f"Dear {order.customer_name},\n\nYour payment for order #{order.id} was successful.\nTotal: ₹{order.total_amount}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[order.customer_email],
        fail_silently=True
    )
    # Reseller Email
    send_mail(
        subject=f'New Order on Drapso - #{order.id}',
        message=f"Store: {order.store.store_name}\nAmount: ₹{order.total_amount}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[order.reseller.email],
        fail_silently=True
    )

def payment_failed(request):
    """Handle payment failure"""
    # Optional: Log the failure reason if sent from Razorpay
    logger.warning("A payment attempt failed on Drapso.")
    
    return render(request, 'orders/payment_failed.html', {
        'support_email': settings.DEFAULT_FROM_EMAIL,
        'brand_name': 'Drapso'
    })

def order_success(request, order_id):
    """Order success page - using database primary key"""
    order = get_object_or_404(Order, id=order_id) 
    return render(request, 'orders/success.html', {'order': order})

def track_order(request, order_id):
    """Track order status"""
    order = get_object_or_404(Order, order_id=order_id)
    
    tracking_info = None
    if order.awb_code:
        try:
            shiprocket = ShiprocketService()
            tracking_info = shiprocket.track_shipment(order.awb_code)
        except Exception as e:
            logger.error(f"Tracking failed for {order.awb_code}: {str(e)}")
    
    can_cancel = order.can_cancel()
    can_return = order.can_request_return()
    has_return_request = order.return_requests.exists()
    
    context = {
        'order': order,
        'tracking_info': tracking_info,
        'can_cancel': can_cancel,
        'can_return': can_return,
        'has_return_request': has_return_request,
    }
    return render(request, 'orders/track.html', context)


# ============ RESELLER ORDER MANAGEMENT ============

@login_required
@user_passes_test(is_reseller)
def reseller_orders(request, store_id):
    """List all orders for a reseller's store"""
    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    
    orders = Order.objects.filter(store=store).select_related('product', 'variant')
    
    status_filter = request.GET.get('status')
    if status_filter:
        orders = orders.filter(order_status=status_filter)
    
    context = {
        'store': store,
        'orders': orders,
        'status_filter': status_filter,
    }
    return render(request, 'orders/order_list.html', context)


@login_required
@user_passes_test(is_reseller)
def reseller_order_detail(request, store_id, order_id):
    """View order details for reseller"""
    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    order = get_object_or_404(Order, id=order_id, store=store)
    
    return_request = order.return_requests.first()
    
    context = {
        'store': store,
        'order': order,
        'return_request': return_request,
    }
    return render(request, 'orders/order_detail.html', context)


@login_required
@user_passes_test(is_reseller)
def approve_order(request, store_id, order_id):
    """Reseller moves order to Shiprocket using pre-selected courier info."""
    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    order = get_object_or_404(Order, id=order_id, store=store)
    
    # SECURITY GATE
    if order.payment_status != 'success':
        messages.error(request, "Cannot approve: Payment is not verified yet.")
        return redirect('orders:reseller_order_detail', store_id=store.id, order_id=order.id)

    if request.method == 'POST':
        shiprocket = ShiprocketService()
        
        # Resolve Pickup Location
        # If order.pickup_pincode exists, service will find the 'Location Tag'
        pickup_loc = order.pickup_pincode if order.pickup_pincode else "PRIMARY"
        
        # Prepare the payload to match ShiprocketService.create_order expectations
        order_data = {
            'order_id': f"DRAPSO-{order.id}", # Unique ID for Shiprocket
            'order_date': order.created_at.strftime('%Y-%m-%d %H:%M'),
            'pickup_location': pickup_loc,
            'customer_name': order.customer_name,
            'email': order.customer_email,
            'phone': order.customer_phone,
            'address': order.shipping_address,
            'city': order.shipping_city,
            'state': order.shipping_state,
            'pincode': order.shipping_pincode,
            'country': 'India',
            
            # Use 'items' key as expected by your service loop
            'items': [{
                'name': order.product.name,
                'sku': getattr(order.variant or order.product, 'sku', f"PROD-{order.product.id}"),
                'units': order.quantity,
                'selling_price': float(order.product_price),
                'discount': 0,
                'tax': 0,
                'hsn': 0
            }],
            
            'payment_method': 'Prepaid',
            'sub_total': float(order.total_amount - order.shipping_charge),
            'shipping_charges': float(order.shipping_charge),
            'total': float(order.total_amount),
            'weight': float(getattr(order.variant or order.product, 'weight', 0.5)),
            
            # Pass the courier selected during checkout
            'courier_id': getattr(order, 'courier_id', None), 
        }
        
        result = shiprocket.create_order(order_data)
        
        if result.get('success'):
            order.shiprocket_order_id = result.get('shiprocket_order_id')
            order.shipment_id = result.get('shipment_id')
            order.order_status = 'approved'
            # Save specific courier response if provided
            if result.get('awb_code'):
                order.awb_code = result.get('awb_code')
            
            order.save()
            messages.success(request, f"Order synced with Shiprocket! Shipment ID: {order.shipment_id}")
        else:
            messages.error(request, f"Shiprocket Error: {result.get('error')}")
            
        return redirect('orders:reseller_order_detail', store_id=store.id, order_id=order.id)

    return render(request, 'orders/reseller/approve_order.html', {'order': order, 'store': store})
    
@login_required
@user_passes_test(is_reseller)
def mark_order_shipped(request, store_id, order_id):
    """Mark order as shipped and generate shipping label"""
    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    order = get_object_or_404(Order, id=order_id, store=store)
    
    if order.order_status != 'approved':
        messages.error(request, 'Order must be approved before shipping.')
        return redirect('orders:reseller_order_detail', store_id=store.id, order_id=order.id)
    
    if request.method == 'POST':
        if order.shipment_id:
            try:
                shiprocket = ShiprocketService()
                label_result = shiprocket.generate_shipping_label(order.shipment_id)
                
                if label_result:
                    order.order_status = 'shipped'
                    order.shipped_at = timezone.now()
                    order.add_status_history('shipped', {'awb': order.awb_code})
                    order.save()
                    
                    # Send email to customer
                    send_mail(
                        subject=f'Order Shipped - {order.order_id}',
                        message=f"""
Dear {order.customer_name},

Your order has been shipped!

📦 Order Details:
• Order ID: {order.order_id}
• Courier: {order.courier_name}
• AWB Number: {order.awb_code}

Track your shipment: {order.tracking_url or settings.SITE_URL}/orders/track/{order.order_id}/

Estimated Delivery: {order.estimated_delivery_date.strftime('%B %d, %Y') if order.estimated_delivery_date else 'Check tracking'}

Thank you for shopping with us!

Regards,
Drapso Team
                        """,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[order.customer_email],
                        fail_silently=False,
                    )
                    
                    messages.success(request, f'Order {order.order_id} marked as shipped!')
                else:
                    messages.error(request, 'Failed to generate shipping label.')
            except Exception as e:
                logger.error(f"Shipping label generation error: {str(e)}")
                messages.error(request, f'Error generating label: {str(e)}')
        else:
            messages.error(request, 'No shipment found for this order.')
        
        return redirect('orders:reseller_order_detail', store_id=store.id, order_id=order.id)
    
    context = {
        'store': store,
        'order': order,
    }
    return render(request, 'orders/reseller/ship_order.html', context)


# ============ RETURN MANAGEMENT ============

def request_return(request, order_id):
    """Customer requests return for an order"""
    order = get_object_or_404(Order, order_id=order_id)
    
    if not order.can_request_return():
        messages.error(request, 'Return cannot be requested for this order.')
        return redirect('orders:track_order', order_id=order_id)
    
    if order.return_requests.exists():
        messages.error(request, 'A return request has already been submitted for this order.')
        return redirect('orders:track_order', order_id=order_id)
    
    if order.product.source_type == 'imported' and order.wholeseller:
        return_address_obj = WholesellerAddress.objects.filter(
            user=order.wholeseller,
            is_primary=True,
            is_active=True
        ).first()
        return_address = f"{return_address_obj.address_line1}\n{return_address_obj.address_line2 or ''}\n{return_address_obj.city}, {return_address_obj.state} - {return_address_obj.postal_code}" if return_address_obj else "Contact support for return address"
    else:
        return_address_obj = ResellerAddress.objects.filter(
            user=order.reseller,
            is_primary=True
        ).first()
        return_address = f"{return_address_obj.address_line1}\n{return_address_obj.address_line2 or ''}\n{return_address_obj.city}, {return_address_obj.state} - {return_address_obj.postal_code}" if return_address_obj else "Contact support for return address"
    
    if request.method == 'POST':
        form = ReturnRequestForm(request.POST, request.FILES)
        
        if form.is_valid():
            return_request = form.save(commit=False)
            return_request.order = order
            return_request.user = request.user if request.user.is_authenticated else None
            return_request.return_address = return_address
            return_request.refund_amount = order.total_amount
            return_request.save()
            
            order.order_status = 'return_requested'
            order.add_status_history('return_requested', {'return_id': return_request.id})
            order.save()
            
            # Notify reseller
            send_mail(
                subject=f'Return Request - {order.order_id}',
                message=f"""
Dear {order.reseller.first_name},

A return request has been submitted for Order {order.order_id}.

📦 Return Details:
• Customer: {order.customer_name}
• Reason: {return_request.get_reason_display()}
• Description: {return_request.description}

Please login to review this return request.

Regards,
Drapso Team
                """,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[order.reseller.email],
                fail_silently=False,
            )
            
            messages.success(request, 'Return request submitted successfully! You will be notified once reviewed.')
            return redirect('orders:track_order', order_id=order_id)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ReturnRequestForm()
    
    context = {
        'form': form,
        'order': order,
        'return_address': return_address,
    }
    return render(request, 'orders/return_request.html', context)


@login_required
@user_passes_test(is_reseller)
def review_return_request(request, store_id, return_id):
    """Reseller reviews return request and triggers reverse pickup"""
    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    return_request = get_object_or_404(ReturnRequest, id=return_id, order__store=store)
    order = return_request.order
    
    if request.method == 'POST':
        action = request.POST.get('action')
        notes = request.POST.get('admin_notes', '')
        
        if action == 'approve':
            try:
                shiprocket = ShiprocketService()
                
                # Get pickup location for return
                pickup_location_name = shiprocket.get_pickup_location_by_pincode(order.pickup_pincode)
                
                if not pickup_location_name:
                    pickup_location_name = order.pickup_address_type.upper()
                    logger.warning(f"No pickup location found for return, using '{pickup_location_name}'")
                
                pickup_data = {
                    'order_id': order.order_id,
                    'pickup_location': pickup_location_name,  # Add pickup location for return
                    'customer_name': order.customer_name,
                    'address': order.shipping_address,
                    'city': order.shipping_city,
                    'state': order.shipping_state,
                    'pincode': order.shipping_pincode,
                    'phone': order.customer_phone,
                    'items': [
                        {
                            'name': order.product.name,
                            'quantity': order.quantity,
                            'price': float(order.product_price)
                        }
                    ],
                    'weight': float(getattr(order.variant if order.variant else order.product, 'weight', 0.5)),
                    'is_replacement': return_request.reason in ['wrong_product', 'defective']
                }
                
                result = shiprocket.create_return_order(pickup_data)
                
                if result.get('success'):
                    return_request.return_shipment_id = result.get('return_shipment_id')
                    return_request.return_awb = result.get('return_awb')
                    return_request.return_label_url = result.get('label_url')
                    return_request.return_courier_name = result.get('courier_name')
                    return_request.status = 'approved'
                    return_request.admin_notes = notes
                    return_request.reviewed_at = timezone.now()
                    return_request.save()
                    
                    # Schedule pickup
                    pickup_result = shiprocket.schedule_return_pickup(return_request.return_shipment_id)
                    
                    if pickup_result:
                        return_request.return_pickup_scheduled_date = pickup_result.get('pickup_date')
                        return_request.status = 'pickup_scheduled'
                        return_request.save()
                    
                    order.order_status = 'return_approved'
                    order.add_status_history('return_approved', {'return_shipment_id': return_request.return_shipment_id})
                    order.save()
                    
                    # Notify customer
                    send_mail(
                        subject=f'Return Request Approved - Pickup Scheduled - {order.order_id}',
                        message=f"""
Dear {order.customer_name},

Your return request has been APPROVED! 🚚

📦 Return Details:
• Return AWB: {return_request.return_awb}
• Courier: {return_request.return_courier_name}
• Pickup Date: {return_request.return_pickup_scheduled_date}

📎 Download your return shipping label:
{return_request.return_label_url}

Please pack the product securely and hand it over to the courier when they arrive.

Track your return: {settings.SITE_URL}/orders/return/track/{return_request.id}/

Regards,
Drapso Team
                        """,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[order.customer_email],
                        fail_silently=False,
                    )
                    
                    messages.success(request, f'Return pickup scheduled for {return_request.return_pickup_scheduled_date}')
                else:
                    messages.error(request, f'Failed to create return shipment: {result.get("error")}')
            except Exception as e:
                logger.error(f"Return processing error: {str(e)}")
                messages.error(request, f'Error processing return: {str(e)}')
            
        elif action == 'reject':
            return_request.status = 'rejected'
            return_request.admin_notes = notes
            return_request.reviewed_at = timezone.now()
            return_request.save()
            
            order.order_status = 'delivered'
            order.add_status_history('return_rejected', {'reason': notes})
            order.save()
            
            # Notify customer
            send_mail(
                subject=f'Return Request Rejected - {order.order_id}',
                message=f"""
Dear {order.customer_name},

We have reviewed your return request for Order {order.order_id}.

Unfortunately, your return request has been REJECTED.

Reason: {notes or 'The return request did not meet our policy requirements.'}

If you believe this is a mistake, please contact our support team.

Regards,
Drapso Team
                """,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[order.customer_email],
                fail_silently=False,
            )
            
            messages.warning(request, 'Return request rejected.')
        
        return redirect('orders:reseller_order_detail', store_id=store.id, order_id=order.id)
    
    context = {
        'store': store,
        'order': order,
        'return_request': return_request,
    }
    return render(request, 'orders/reseller/review_return.html', context)


# ============ ADMIN REFUND MANAGEMENT ============

@login_required
@user_passes_test(is_admin)
def admin_refund_requests(request):
    """Admin view all refund requests"""
    refunds = Refund.objects.filter(status='pending').select_related('order', 'return_request')
    completed_refunds = Refund.objects.filter(status='completed').select_related('order', 'return_request')[:50]
    
    context = {
        'refunds': refunds,
        'completed_refunds': completed_refunds,
    }
    return render(request, 'orders/admin/refund_requests.html', context)


@login_required
@user_passes_test(is_admin)
def process_refund(request, refund_id):
    """Admin processes manual refund"""
    refund = get_object_or_404(Refund, id=refund_id)
    
    if request.method == 'POST':
        form = RefundForm(request.POST, request.FILES)
        
        if form.is_valid():
            refund.refund_amount = form.cleaned_data['refund_amount']
            refund.transaction_id = form.cleaned_data['transaction_id']
            refund.admin_notes = form.cleaned_data['admin_notes']
            
            if form.cleaned_data['transfer_proof']:
                refund.transfer_proof = form.cleaned_data['transfer_proof']
            
            refund.status = 'completed'
            refund.processed_at = timezone.now()
            refund.save()
            
            order = refund.order
            order.order_status = 'refunded'
            order.payment_status = 'refunded'
            order.add_status_history('refunded', {'refund_id': refund.id})
            order.save()
            
            if refund.return_request:
                refund.return_request.status = 'refunded'
                refund.return_request.refunded_at = timezone.now()
                refund.return_request.save()
            
            # Notify customer
            send_mail(
                subject=f'Refund Processed - {order.order_id}',
                message=f"""
Dear {order.customer_name},

Your refund for Order {order.order_id} has been processed.

💰 Refund Details:
• Amount: ₹{refund.refund_amount}
• Transaction Reference: {refund.transaction_id or 'Manual Transfer'}

The amount has been transferred to your provided bank account. Please allow 2-3 business days for it to reflect.

Regards,
Drapso Team
                """,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[order.customer_email],
                fail_silently=False,
            )
            
            messages.success(request, f'Refund of ₹{refund.refund_amount} marked as completed.')
            return redirect('orders:admin_refund_requests')
    else:
        form = RefundForm(initial={'refund_amount': refund.refund_amount})
    
    context = {
        'form': form,
        'refund': refund,
    }
    return render(request, 'orders/admin/process_refund.html', context)


@login_required
@user_passes_test(is_admin)
def create_manual_refund(request, order_id):
    """Admin creates manual refund record"""
    order = get_object_or_404(Order, order_id=order_id)
    
    if order.refunds.exists():
        messages.error(request, 'A refund already exists for this order.')
        return redirect('orders:admin_refund_requests')
    
    if request.method == 'POST':
        form = RefundForm(request.POST)
        
        if form.is_valid():
            refund = Refund.objects.create(
                order=order,
                refund_type='cancellation' if order.order_status == 'cancelled' else 'return',
                refund_amount=form.cleaned_data['refund_amount'],
                account_holder_name=form.cleaned_data.get('account_holder_name', order.customer_name),
                account_number=form.cleaned_data.get('account_number', ''),
                ifsc_code=form.cleaned_data.get('ifsc_code', ''),
                bank_name=form.cleaned_data.get('bank_name', ''),
                upi_id=form.cleaned_data.get('upi_id', ''),
                status='pending'
            )
            
            messages.success(request, f'Manual refund record created for ₹{refund.refund_amount}')
            return redirect('orders:process_refund', refund_id=refund.id)
    else:
        form = RefundForm(initial={'refund_amount': order.total_amount})
    
    context = {
        'form': form,
        'order': order,
    }
    return render(request, 'orders/admin/create_manual_refund.html', context)


# ============ CANCELLATION ============

def cancel_order(request, order_id):
    """Customer cancels order before shipping"""
    order = get_object_or_404(Order, order_id=order_id)
    
    if not order.can_cancel():
        messages.error(request, 'Order cannot be cancelled. It may have already been shipped.')
        return redirect('orders:track_order', order_id=order_id)
    
    if request.method == 'POST':
        account_holder_name = request.POST.get('account_holder_name')
        account_number = request.POST.get('account_number')
        confirm_account_number = request.POST.get('confirm_account_number')
        ifsc_code = request.POST.get('ifsc_code')
        bank_name = request.POST.get('bank_name')
        upi_id = request.POST.get('upi_id')
        
        if account_number != confirm_account_number:
            messages.error(request, 'Account numbers do not match.')
            return redirect('orders:cancel_order', order_id=order_id)
        
        refund = Refund.objects.create(
            order=order,
            refund_type='cancellation',
            refund_amount=order.total_amount,
            account_holder_name=account_holder_name,
            account_number=account_number,
            ifsc_code=ifsc_code,
            bank_name=bank_name,
            upi_id=upi_id,
            status='pending'
        )
        
        order.order_status = 'cancelled'
        order.add_status_history('cancelled', {'refund_id': refund.id})
        order.save()
        
        # Notify reseller
        send_mail(
            subject=f'Order Cancelled - {order.order_id}',
            message=f"""
Dear {order.reseller.first_name},

Order {order.order_id} has been CANCELLED by the customer.

📦 Order Details:
• Product: {order.product.name}
• Quantity: {order.quantity}
• Refund Amount: ₹{order.total_amount}

Please do not ship this order.

Regards,
Drapso Team
            """,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.reseller.email],
            fail_silently=False,
        )
        
        messages.success(request, f'Order {order.order_id} has been cancelled. Your refund will be processed within 5-7 business days.')
        return redirect('orders:track_order', order_id=order_id)
    
    context = {
        'order': order,
    }
    return render(request, 'orders/cancel_order.html', context)


# ============ WHOLESELLER ORDER VIEWS ============

@login_required
@user_passes_test(is_wholeseller)
def wholeseller_orders(request):
    """Wholeseller views orders for their products"""
    orders = Order.objects.filter(wholeseller=request.user).select_related('store', 'product')
    
    context = {
        'orders': orders,
    }
    return render(request, 'orders/wholeseller/order_list.html', context)