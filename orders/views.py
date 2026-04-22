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
from django.contrib.admin.views.decorators import staff_member_required


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
    product_id = request.GET.get('product_id')
    variant_id = request.GET.get('variant_id')
    pincode = request.GET.get('pincode')
    quantity = int(request.GET.get('quantity', 1))
    store_id = request.GET.get('store_id')
    
    # 1. Basic Validation
    if not all([product_id, pincode, store_id]):
        return JsonResponse({'success': False, 'error': 'Missing parameters'}, status=400)
    
    try:
        product = ResellerProduct.objects.get(id=product_id, is_active=True)
        store = Store.objects.get(id=store_id)
        
        # 2. Pickup Resolution
        pickup_info = get_pickup_address(product, store)
        if not pickup_info or not pickup_info.get('pincode'):
            logger.error(f"Pickup info missing for Product {product_id}")
            return JsonResponse({'success': False, 'error': 'Warehouse configuration error.'})

        # 3. Product/Variant Data
        variant = None
        if variant_id and variant_id not in ['null', 'undefined', '']:
            variant = ResellerProductVariant.objects.filter(id=variant_id, is_active=True).first()

        source = variant or product
        
        # 4. Critical: Ensure dimensions are NEVER zero (Shiprocket will fail otherwise)
        l = float(source.length) if source.length and source.length > 0 else 10.0
        b = float(source.breadth) if source.breadth and source.breadth > 0 else 10.0
        h = float(source.height) if source.height and source.height > 0 else 10.0
        weight = float(source.weight) if source.weight and source.weight > 0 else 0.5
        
        # 5. Billable Weight Calculation
        actual_weight = weight * quantity
        volumetric_weight = ((l * b * h) / 5000.0) * quantity
        billable_weight = round(max(actual_weight, volumetric_weight), 2)

        product_price = float(variant.selling_price if variant else product.selling_price)
        
        # 6. Shiprocket API Call
        shiprocket = ShiprocketService()
        cheapest_courier = shiprocket.get_cheapest_courier(
            pickup_postcode=str(pickup_info['pincode']),
            delivery_postcode=str(pincode),
            weight=billable_weight,
            length=l, breadth=b, height=h
        )
        
        if cheapest_courier:
            # Note: 'delivery_time' key added to match your frontend JS
            return JsonResponse({
                'success': True,
                'delivery_time': cheapest_courier['etd'],  # Matches frontend JS
                'etd_date': cheapest_courier['etd'],       # Matches hidden field
                'product_price': round(product_price, 2),
                'shipping_charge': 0,                      # Free for customer
                'courier_name': cheapest_courier['courier_name'],
                'courier_id': cheapest_courier['courier_id'],
                'pickup_address': pickup_info.get('address', ''),
                'pickup_pincode': pickup_info.get('pincode', ''),
                'pickup_location_type': pickup_info.get('type', ''),
                'weight': billable_weight,
                'length': l, 'breadth': b, 'height': h,
            })
        else:
            # This logs the specific failure in your console
            logger.warning(f"No couriers for {pickup_info['pincode']} to {pincode}")
            return JsonResponse({
                'success': False, 
                'error': f'No delivery partners available for pincode {pincode}'
            })
        
    except Exception as e:
        logger.exception("Shipping calculation failed")
        return JsonResponse({'success': False, 'error': 'Internal server error'}, status=500)

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
            product_price = float(variant.selling_price if variant else product.selling_price)
            shipping_charge = float(request.POST.get('shipping_charge', 0))
            total_amount = (product_price * quantity) + shipping_charge
            
            # CAPTURE DIMENSIONS FROM POST (Sent by the AJAX/Hidden fields)
            order_data = {
                'form_data': form.cleaned_data,
                'product_id': product.id,
                'variant_id': variant.id if variant else None,
                'quantity': quantity,
                'product_price': product_price,
                'shipping_charge': shipping_charge,
                'total_amount': total_amount,
                'amount_paise': int(total_amount * 100),
                # Logic Persistence
                'weight': request.POST.get('weight', 0.5),
                'length': request.POST.get('length', 10),
                'breadth': request.POST.get('breadth', 10),
                'height': request.POST.get('height', 10),
                'courier_id': request.POST.get('courier_id'),
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
    
    form = CheckoutForm(initial={'quantity': 1})
    return render(request, 'orders/checkout.html', {'form': form, 'product': product, 'variant': variant, 'store': store})

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
    
    # Merge existing payment_data into context
    context = {
        'razorpay_order_id': razorpay_order_id,
        'razorpay_key_id': settings.RAZORPAY_KEY_ID,
        'amount': payment_data['total_amount'],
        'amount_paise': payment_data['amount_paise'],
        'form_data': payment_data['form_data'],
        'product_id': payment_data['product_id'],
        'variant_id': payment_data['variant_id'],
        'quantity': payment_data['quantity'],
        'product_price': payment_data.get('product_price', 0),
        'shipping_charge': payment_data['shipping_charge'],
        # DIMENSIONS PASSED TO TEMPLATE
        'weight': payment_data.get('weight'),
        'length': payment_data.get('length'),
        'breadth': payment_data.get('breadth'),
        'height': payment_data.get('height'),
        # LOGISTICS
        'courier_id': payment_data.get('courier_id'),
        'courier_name': payment_data.get('courier_name'),
        'estimated_delivery_date': payment_data.get('estimated_delivery_date'),
        'pickup_address': payment_data.get('pickup_address'),
        'pickup_pincode': payment_data.get('pickup_pincode'),
        'pickup_address_type': payment_data.get('pickup_address_type'),
        'store': product.store if product else None,
    }
    return render(request, 'orders/payment.html', context)
    
from django.db.models import F
from datetime import datetime
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

@csrf_exempt
def payment_success(request):
    if request.method != 'POST':
        return redirect('home')

    params_dict = {
        'razorpay_order_id': request.POST.get('razorpay_order_id'),
        'razorpay_payment_id': request.POST.get('razorpay_payment_id'),
        'razorpay_signature': request.POST.get('razorpay_signature')
    }
    
    try:
        # 1. Verify Payment Signature
        razorpay_client.utility.verify_payment_signature(params_dict)
        
        with transaction.atomic():
            def get_clean(key, default=None):
                val = request.POST.get(key)
                if val in ['None', '', 'null', 'undefined', None]:
                    return default
                return val

            # --- NEW DATE PARSING LOGIC ---
            etd_raw = get_clean('estimated_delivery_date')
            formatted_etd = None
            if etd_raw:
                try:
                    # Converts "Apr 27, 2026" to YYYY-MM-DD
                    formatted_etd = datetime.strptime(etd_raw, "%b %d, %Y").date()
                except (ValueError, TypeError):
                    logger.warning(f"Could not parse ETD: {etd_raw}")
                    formatted_etd = None
            # ------------------------------

            product_id = request.POST.get('product_id')
            variant_id = get_clean('variant_id')
            quantity = int(request.POST.get('quantity', 1))

            # select_for_update() locks the row so two people can't buy the same stock
            rp = ResellerProduct.objects.select_for_update().get(id=product_id)

            # 2. STRICT STOCK CHECK
            stock_object = None
            if rp.source_type == 'imported':
                if variant_id:
                    rv = get_object_or_404(ResellerProductVariant, id=variant_id, product=rp)
                    if rv.source_variant:
                        stock_object = WholesellerProductVariant.objects.select_for_update().get(id=rv.source_variant.id)
                else:
                    stock_object = WholesellerProduct.objects.select_for_update().get(id=rp.source_product.id)
            else:
                if variant_id:
                    stock_object = ResellerProductVariant.objects.select_for_update().get(id=variant_id, product=rp)
                else:
                    stock_object = rp

            if stock_object and stock_object.stock < quantity:
                logger.error(f"Oversell detected for Order {params_dict['razorpay_order_id']}")
                return redirect('orders:payment_failed')

            # 3. DEDUCT STOCK
            if stock_object:
                stock_object.stock = F('stock') - quantity
                stock_object.save()

            # 4. CREATE ORDER RECORD
            total_amt = float(get_clean('total_amount', 0))
            order = Order.objects.create(
                razorpay_order_id=params_dict['razorpay_order_id'],
                razorpay_payment_id=params_dict['razorpay_payment_id'],
                customer_name=get_clean('customer_name'),
                customer_email=get_clean('customer_email'),
                customer_phone=get_clean('customer_phone'),
                shipping_address=get_clean('shipping_address'),
                shipping_city=get_clean('shipping_city'),
                shipping_state=get_clean('shipping_state'),
                shipping_pincode=get_clean('shipping_pincode'),
                product=rp,
                variant_id=variant_id,
                quantity=quantity,
                store=rp.store,
                reseller=rp.store.reseller,
                wholeseller=rp.source_product.wholeseller if rp.source_type == 'imported' else None,
                product_price=float(get_clean('product_price', 0)),
                shipping_charge=float(get_clean('shipping_charge', 0)),
                total_amount=total_amt,
                payment_amount=total_amt,
                courier_id=get_clean('courier_id'),
                courier_name=get_clean('courier_name'),
                estimated_delivery_date=formatted_etd,  # <--- UPDATED FIELD
                pickup_address=get_clean('pickup_address'),
                pickup_pincode=get_clean('pickup_pincode'),
                pickup_address_type=get_clean('pickup_address_type'),
                weight=float(get_clean('weight', 0.5)),
                length=float(get_clean('length', 10.0)),
                breadth=float(get_clean('breadth', 10.0)),
                height=float(get_clean('height', 10.0)),
                order_status='paid',
                payment_status='success',
                paid_at=timezone.now()
            )

            # Trigger emails in a try-except to not break the transaction
            try:
                _send_order_emails(order)
            except Exception as e:
                logger.error(f"Email failed: {str(e)}")

        return redirect('orders:order_success', order_id=order.id)

    except Exception as e:
        logger.exception(f"Order Creation Failed: {str(e)}")
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

from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
import logging

logger = logging.getLogger(__name__)

@login_required
@user_passes_test(is_reseller)
def approve_order(request, store_id, order_id):
    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    order = get_object_or_404(Order, id=order_id, store=store)

    logger.info(f"=== APPROVE ORDER STARTED for Order {order.order_id} ===")
    logger.info(f"Order courier_id: {order.courier_id}")
    logger.info(f"Order estimated shipping_charge: {order.shipping_charge}")

    if order.payment_status != 'success':
        messages.error(request, "Order cannot be approved without successful payment.")
        return redirect('orders:reseller_order_detail', store_id=store.id, order_id=order.id)

    if request.method == 'POST':
        shiprocket = ShiprocketService()

        # --- STEP 0: WALLET PRE-CHECK ---
        wallet_balance = shiprocket.get_wallet_balance()
        required_charge = float(order.shipping_charge or 0)
        
        logger.info(f"Wallet balance: ₹{wallet_balance}, Required charge: ₹{required_charge}")

        if wallet_balance < required_charge:
            messages.error(request, f"Insufficient Shiprocket balance (Current: ₹{wallet_balance}).")
            return redirect('orders:reseller_order_detail', store_id=store.id, order_id=order.id)

        # --- STEP 1: RESOLVE PICKUP & PAYLOAD ---
        pickup_nickname = shiprocket.get_pickup_nickname(order.pickup_pincode)
        logger.info(f"Pickup nickname: {pickup_nickname}")
        
        order_payload = {
            'order_id': f"{order.order_id}",
            'order_date': order.created_at.strftime('%Y-%m-%d %H:%M'),
            'pickup_location': pickup_nickname,
            'customer_name': order.customer_name,
            'email': order.customer_email,
            'phone': str(order.customer_phone),
            'address': order.shipping_address,
            'city': order.shipping_city,
            'state': order.shipping_state,
            'pincode': order.shipping_pincode,
            'items': [{
                'name': order.product.name[:40],
                'sku': order.sku or f"SKU-{order.product.id}",
                'units': int(order.quantity),
                'selling_price': float(order.product_price),
            }],
            'weight': float(order.weight or 0.5),
            'length': float(order.length or 10),
            'breadth': float(order.breadth or 10),
            'height': float(order.height or 10),
            'sub_total': float(order.product_price * order.quantity),
            'shipping_charges': required_charge,
            'total': float(order.total_amount),
        }

        # --- STEP 2: CREATE ORDER IN SHIPROCKET ---
        create_res = shiprocket.create_order(order_payload)
        
        if not create_res.get('success'):
            messages.error(request, f"Shiprocket Order Creation Failed: {create_res.get('error')}")
            return redirect('orders:reseller_order_detail', store_id=store.id, order_id=order.id)
        
        # --- STEP 3: ASSIGN AWB ---
        assign_res = shiprocket.assign_awb(create_res.get('shipment_id'), order.courier_id)
        
        if not assign_res.get('success'):
            # Still save partial order info
            with transaction.atomic():
                order.shiprocket_order_id = create_res.get('shiprocket_order_id')
                order.shipment_id = create_res.get('shipment_id')
                order.order_status = 'approved'
                order.approved_at = timezone.now()
                order.save(update_fields=['shiprocket_order_id', 'shipment_id', 'order_status', 'approved_at'])
                order.add_status_history('approval_failed_awb', {'error': assign_res.get('error')})
            
            messages.warning(request, f"Order created but AWB assignment failed: {assign_res.get('error')}")
            return redirect('orders:reseller_order_detail', store_id=store.id, order_id=order.id)
        
        # --- STEP 4: GET ACTUAL SHIPPING CHARGE ---
        raw_charge = assign_res.get('actual_charge', 0)
        logger.info(f"Raw charge from assign_awb: {raw_charge}")
        
        # CRITICAL FIX: If assign_awb returns 0, use calculate_shipping_charge method
        if raw_charge == 0 or raw_charge is None:
            logger.warning("assign_awb returned 0, calling calculate_shipping_charge to get actual rate")
            
            # Call calculate_shipping_charge with order details
            shipping_calc = shiprocket.calculate_shipping_charge(
                pickup_postcode=str(order.pickup_pincode),
                delivery_postcode=str(order.shipping_pincode),
                weight=float(order.weight or 0.5),
                pickup_location=pickup_nickname,
                length=float(order.length or 10),
                breadth=float(order.breadth or 10),
                height=float(order.height or 10)
            )
            
            if shipping_calc and shipping_calc.get('shipping_charge', 0) > 0:
                raw_charge = shipping_calc['shipping_charge']
                logger.info(f"Retrieved shipping charge from calculate_shipping_charge: {raw_charge}")
                logger.info(f"Courier: {shipping_calc.get('courier_name')}, Delivery: {shipping_calc.get('delivery_time')}")
            else:
                # Last resort: use the estimated charge
                raw_charge = required_charge
                logger.warning(f"calculate_shipping_charge failed, using estimated charge: {raw_charge}")
        
        # Final validation
        if raw_charge <= 0:
            error_msg = f"CRITICAL: Cannot determine shipping charge. Raw: {raw_charge}, Estimated: {required_charge}"
            logger.error(f"Order {order.order_id} - {error_msg}")
            messages.error(request, error_msg)
            return redirect('orders:reseller_order_detail', store_id=store.id, order_id=order.id)
        
        logger.info(f"Final actual shipping rate: {raw_charge}")
        
        # --- STEP 5: CALCULATE FINAL COST WITH TAXES ---
        base_rate = Decimal(str(raw_charge))
        
        # Apply 18% GST + 25% Buffer
        gst_multiplier = Decimal('1.18')
        buffer_multiplier = Decimal('1.25')
        
        final_cost = base_rate * gst_multiplier * buffer_multiplier
        final_cost_rounded = final_cost.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        logger.info(f"Final cost (incl. GST + Buffer): ₹{final_cost_rounded}")
        
        # --- STEP 6: SAVE ALL ORDER DATA ---
        try:
            with transaction.atomic():
                order.shiprocket_order_id = create_res.get('shiprocket_order_id')
                order.shipment_id = create_res.get('shipment_id')
                order.awb_code = assign_res.get('awb_code')
                order.courier_name = assign_res.get('courier_name')
                order.actual_shipping_cost = final_cost_rounded
                order.order_status = 'approved'
                order.approved_at = timezone.now()
                
                order.save(update_fields=[
                    'shiprocket_order_id', 'shipment_id', 'awb_code', 'courier_name',
                    'actual_shipping_cost', 'order_status', 'approved_at'
                ])
                
                # Verify save
                order.refresh_from_db()
                logger.info(f"Verified DB value - actual_shipping_cost: {order.actual_shipping_cost}")
                
                # Add status history
                history_details = {
                    'actual_shipping_cost': str(order.actual_shipping_cost),
                    'base_rate': str(base_rate),
                    'rate_source': 'calculate_shipping_charge' if raw_charge != required_charge else 'estimated',
                    'gst_applied': '1.18',
                    'buffer_applied': '1.25',
                    'courier_id': order.courier_id,
                    'awb_code': order.awb_code
                }
                order.add_status_history('approved', history_details)
                
            messages.success(request, f"Order Approved! Shipping Cost: ₹{order.actual_shipping_cost}")
            
        except Exception as e:
            logger.error(f"Failed to save order: {str(e)}", exc_info=True)
            messages.error(request, f"Failed to save order: {str(e)}")
            return redirect('orders:reseller_order_detail', store_id=store.id, order_id=order.id)

        return redirect('orders:reseller_order_detail', store_id=store.id, order_id=order.id)

    return render(request, 'orders/approve_confirm.html', {'order': order})
    
# orders/views.py - Add these imports at the top
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from .models import Order
from shiprocket.services import ShiprocketService

logger = logging.getLogger(__name__)
@login_required
def mark_order_shipped(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    # ---------- AUTH ----------
    if order.product.source_type == 'imported':
        if order.wholeseller != request.user:
            messages.error(request, "Unauthorized")
            return redirect('dashboard')
        redirect_url = redirect('orders:wholeseller_order_detail', order_id=order.id)
    else:
        if order.store.reseller != request.user:
            messages.error(request, "Unauthorized")
            return redirect('dashboard')
        redirect_url = redirect('orders:reseller_order_detail', store_id=order.store.id, order_id=order.id)

    # ---------- GUARDS ----------
    if order.order_status == 'shipped':
        messages.warning(request, "Already shipped")
        return redirect_url

    if not order.shipment_id:
        messages.error(request, "Shipment not created")
        return redirect_url

    if request.method == 'POST':
        try:
            shiprocket = ShiprocketService()

            # ===============================
            # STEP 1: REQUEST PICKUP
            # ===============================
            
            pickup_result = shiprocket.request_pickup(order.shipment_id)
            

            # Don't fail if already scheduled
            if pickup_result.get('error') not in [None, 'Already in Pickup Queue.']:
                print("⚠️ Pickup issue:", pickup_result)

            # ===============================
            # STEP 2: GENERATE LABEL (WITH RETRY)
            # ===============================
            

            import time
            label_result = None

            for i in range(3):
                
                label_result = shiprocket.generate_shipping_label(order.shipment_id)
                
                if label_result.get('success'):
                    break

                time.sleep(2)

            if not label_result or not label_result.get('success'):
                
                messages.error(request, f"Label failed: {label_result}")
                return redirect_url

            label_url = label_result.get('label_url')

            if not label_url:
                
                messages.error(request, f"Invalid label response: {label_result}")
                return redirect_url

            
            # ===============================
            # STEP 3: ASSIGN VALUES
            # ===============================
            order.label_url = label_url

            if order.awb_code:
                order.tracking_url = f"https://shiprocket.co/tracking/{order.awb_code}"
               
            else:
                pass

            # ===============================
            # STEP 4: SAVE
            # ===============================
            

            order.add_status_history('shipped', {
                'label_url': order.label_url,
                'awb_code': order.awb_code,
                'tracking_url': order.tracking_url,
                'pickup_response': pickup_result,
                'label_response': label_result
            })

            # ===============================
            # STEP 5: VERIFY
            # ===============================
            order.refresh_from_db()

            
            # ===============================
            # STEP 6: EMAIL
            # ===============================
            try:
                send_mail(
                    f"Order Shipped - {order.order_id}",
                    f"""
Hi {order.customer_name},

Your order has been shipped.

AWB: {order.awb_code}
Tracking: {order.tracking_url or 'Will update soon'}

Thank you.
                    """,
                    settings.DEFAULT_FROM_EMAIL,
                    [order.customer_email],
                    fail_silently=True
                )
            except Exception as e:
                print(f"Email failed: {e}")

            messages.success(request, "Order shipped successfully")

        except Exception as e:
            import traceback

            traceback.print_exc()

            messages.error(request, str(e))

        return redirect_url

    return render(request, 'orders/ship_order.html', {'order': order})
    
@login_required
def download_order_document(request, order_id, doc_type):
    """Unified view to download Label, Invoice, or Manifest."""
    order = get_object_or_404(Order, id=order_id)
    
    is_authorized = False
    if order.product.source_type == 'imported' and order.wholeseller == request.user:
        is_authorized = True
    elif order.store.reseller == request.user:
        is_authorized = True

    if not is_authorized:
        messages.error(request, "You are not authorized to view these documents.")
        return redirect('dashboard')

    if not order.shipment_id:
        messages.error(request, "Shipment has not been created yet.")
        return redirect(request.META.get('HTTP_REFERER', 'dashboard'))

    shiprocket = ShiprocketService()
    result = {'success': False, 'error': 'Invalid document type'}

    # For label, check if we already have it in database
    if doc_type == 'label':
        if order.label_url:
            # Use existing label URL from database
            return redirect(order.label_url)
        else:
            # Generate new label
            result = shiprocket.generate_shipping_label(order.shipment_id)
            if result.get('success'):
                # Save the label URL for future use
                order.label_url = result.get('url')
                order.save(update_fields=['label_url'])
    elif doc_type == 'invoice':
        result = shiprocket.generate_invoice(order.shiprocket_order_id)
    elif doc_type == 'manifest':
        result = shiprocket.generate_manifest(order.shipment_id)

    if result.get('success'):
        return redirect(result.get('url'))
    else:
        messages.error(request, f"Shiprocket Error: {result.get('error')}")
        return redirect(request.META.get('HTTP_REFERER', 'dashboard'))


@login_required
def recreate_shipment(request, order_id):
    """Recreate the Shiprocket shipment if it was lost or invalid"""
    order = get_object_or_404(Order, id=order_id)
    
    # Authorization check
    if order.product.source_type == 'imported':
        if order.wholeseller != request.user:
            messages.error(request, "Not authorized")
            return redirect('dashboard')
    else:
        if order.store.reseller != request.user:
            messages.error(request, "Not authorized")
            return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            shiprocket = ShiprocketService()
            
            # Get pickup location
            pickup_pincode = order.pickup_pincode
            pickup_location = shiprocket.get_pickup_location_by_pincode(pickup_pincode)
            
            if not pickup_location:
                pickup_location = "Primary"
            
            # Prepare order data for Shiprocket
            order_data = {
                'order_id': order.order_id,
                'order_date': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
                'pickup_location': pickup_location,
                'customer_name': order.customer_name,
                'address': order.shipping_address,
                'city': order.shipping_city,
                'state': order.shipping_state,
                'pincode': order.shipping_pincode,
                'email': order.customer_email,
                'phone': order.customer_phone,
                'items': [{
                    'name': order.product.name[:40],
                    'sku': order.sku or 'SKU001',
                    'units': order.quantity,
                    'selling_price': float(order.product_price),
                }],
                'sub_total': float(order.product_price * order.quantity),
                'shipping_charges': float(order.shipping_charge),
                'total': float(order.total_amount),
                'weight': order.weight,
                'length': order.length,
                'breadth': order.breadth,
                'height': order.height,
            }
            
            # Create new order in Shiprocket
            result = shiprocket.create_order(order_data)
            
            if result.get('success'):
                # Update order with new Shiprocket IDs
                order.shiprocket_order_id = result.get('shiprocket_order_id')
                order.shipment_id = result.get('shipment_id')
                order.save(update_fields=['shiprocket_order_id', 'shipment_id'])
                
                messages.success(request, f"Shipment recreated successfully! New Shipment ID: {order.shipment_id}")
            else:
                messages.error(request, f"Failed to recreate shipment: {result.get('error')}")
                
        except Exception as e:
            logger.error(f"Recreate shipment error: {e}")
            messages.error(request, f"Error: {str(e)}")
    
    return redirect('orders:wholeseller_order_detail', order_id=order.id)


# Add this helper view to fix existing orders
@login_required
def fix_missing_label_url(request, order_id):
    """Fix orders that have AWB but missing label_url"""
    order = get_object_or_404(Order, id=order_id)
    
    # Authorization check
    if order.product.source_type == 'imported':
        if order.wholeseller != request.user:
            messages.error(request, "Not authorized")
            return redirect('dashboard')
    else:
        if order.store.reseller != request.user:
            messages.error(request, "Not authorized")
            return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            shiprocket = ShiprocketService()
            
            # Generate label
            result = shiprocket.generate_shipping_label(order.shipment_id)
            
            if result.get('success'):
                order.label_url = result.get('url')
                
                # Set tracking URL if AWB exists
                if order.awb_code and not order.tracking_url:
                    order.tracking_url = f"https://shiprocket.co/tracking/{order.awb_code}"
                
                order.save(update_fields=['label_url', 'tracking_url'])
                messages.success(request, f"Label URL saved successfully!")
            else:
                messages.error(request, f"Failed to get label: {result.get('error')}")
                
        except Exception as e:
            logger.error(f"Fix label error: {e}")
            messages.error(request, f"Error: {str(e)}")
    
    return redirect('orders:wholeseller_order_detail', order_id=order.id)
    
@login_required
def trigger_order_cancellation(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    
    # 1. Authorization Check (Only Wholesaler/Reseller who shipped it)
    if not (order.wholeseller == request.user or order.store.reseller == request.user):
        messages.error(request, "Unauthorized action.")
        return redirect('dashboard')

    if request.method == 'POST':
        shiprocket = ShiprocketService()
        
        # 2. Check if AWB exists
        if order.awb_code:
            result = shiprocket.cancel_shipment(order.awb_code)
            
            if result.get('success'):
                # 3. Update local DB status
                order.order_status = 'cancelled'
                order.add_status_history('cancelled', {'note': 'API Cancellation Triggered'})
                order.save()
                messages.success(request, f"Order {order.order_id} cancelled. Shiprocket wallet refund initiated.")
            else:
                messages.error(request, f"Shiprocket refused cancellation: {result.get('error')}")
        else:
            # Simple local cancellation if no AWB was ever generated
            order.order_status = 'cancelled'
            order.save()
            messages.success(request, "Order cancelled locally.")

    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))     
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
    """Wholesellers view orders assigned to them that are ready for shipment"""
    # Only show orders that the reseller has already approved
    orders = Order.objects.filter(
        wholeseller=request.user,
        order_status__in=['approved', 'shipped', 'delivered', 'cancelled']
    ).select_related('store', 'product').order_by('-created_at') # Changed order_at to order_by
    
    status_filter = request.GET.get('status')
    if status_filter:
        orders = orders.filter(order_status=status_filter)
    
    return render(request, 'orders/wholeseller/order_list.html', {
        'orders': orders,
        'status_filter': status_filter
    })

@login_required
@user_passes_test(is_wholeseller)
def wholeseller_order_detail(request, order_id):
    """View details of a specific order assigned to a wholesaler"""
    # Ensure the wholesaler can only see orders assigned to them and approved for processing
    order = get_object_or_404(
        Order, 
        id=order_id, 
        wholeseller=request.user,
        order_status__in=['approved', 'shipped', 'out_for_delivery', 'delivered', 'cancelled']
    )
    
    return render(request, 'orders/wholeseller/order_detail.html', {
        'order': order
    })

def refresh_orders_from_shiprocket(user_orders):
    shiprocket = ShiprocketService()
    # Get IDs of orders that are approved but not yet delivered
    sr_ids = list(user_orders.filter(
        order_status__in=['approved', 'shipped']
    ).values_list('shiprocket_order_id', flat=True))

    if sr_ids:
        updates = shiprocket.sync_order_statuses(sr_ids)
        for update in updates:
            # Map Shiprocket status to your local Order model status
            sr_status = update.get('status').lower()
            Order.objects.filter(shiprocket_order_id=update.get('id')).update(
                order_status=sr_status
            )

@login_required
def reseller_dashboard(request):
    orders = Order.objects.filter(store__reseller=request.user).order_by('-created_at')
    # Auto-sync before displaying
    refresh_orders_from_shiprocket(orders)
    
    return render(request, 'dashboard/reseller.html', {
        'pending_orders': orders.filter(order_status='paid'),
        'in_transit': orders.filter(order_status__in=['approved', 'shipped']),
        'completed': orders.filter(order_status='delivered')
    })

@login_required
def wholeseller_dashboard(request):
    # Only show orders assigned to this wholesaler that are ready to pack
    orders = Order.objects.filter(wholeseller=request.user).order_by('-created_at')
    refresh_orders_from_shiprocket(orders)

    return render(request, 'dashboard/wholeseller.html', {
        'ready_to_ship': orders.filter(order_status='approved'),
        'shipped_orders': orders.filter(order_status='shipped'),
    })

@staff_member_required
def admin_order_panel(request):
    all_orders = Order.objects.all().select_related('store', 'wholeseller')
    
    return render(request, 'dashboard/admin_orders.html', {
        'total_revenue': sum(o.total_amount for o in all_orders),
        'shipping_losses': all_orders.filter(actual_shipping_cost__gt=F('shipping_charge')),
        'all_orders': all_orders
    })