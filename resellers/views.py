# resellers/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.urls import reverse
from django.core.mail import send_mail
from django.conf import settings
from django.http import JsonResponse, Http404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
import random
import string

from .models import Store, SubscriptionPlan, StoreTheme, StoreTransaction
from .forms import StoreCreationForm, PlanSelectionForm, ThemeSelectionForm
from .razorpay_utils import create_razorpay_order, generate_order_id, verify_payment_signature, razorpay_client
from accounts.models import User

def is_reseller(user):
    return user.is_authenticated and user.role == User.Role.RESELLER

def is_admin(user):
    return user.is_authenticated and (user.is_staff or user.role == User.Role.ADMIN)


# ============ RESELLER VIEWS ============

# resellers/views.py - Updated reseller_dashboard

@login_required
@user_passes_test(is_reseller)
def reseller_dashboard(request):
    """Main reseller dashboard - Shows store status and next steps"""
    stores = Store.objects.filter(reseller=request.user)
    
    # For each store, determine next step
    for store in stores:
        if store.status == 'pending_payment' or not store.payment_status:
            store.next_step = 'Complete Payment'
            # ✅ Fixed: Pass store.id as argument
            store.next_step_url = reverse('resellers:create_order', args=[store.id])
            store.next_step_icon = 'fas fa-credit-card'
        elif not store.subscription_plan:
            store.next_step = 'Select Plan'
            store.next_step_url = reverse('resellers:select_plan')
            store.next_step_icon = 'fas fa-tag'
        elif not store.theme:
            store.next_step = 'Select Theme'
            store.next_step_url = reverse('resellers:select_theme')
            store.next_step_icon = 'fas fa-palette'
        elif store.status == 'expired':
            store.next_step = 'Renew Subscription'
            store.next_step_url = reverse('resellers:manage_subscription', args=[store.id])
            store.next_step_icon = 'fas fa-sync-alt'
        elif store.status == 'active' and store.is_published:
            store.next_step = 'Manage Store'
            store.next_step_url = reverse('resellers:store_dashboard', args=[store.id])
            store.next_step_icon = 'fas fa-tachometer-alt'
        else:
            store.next_step = 'View Store'
            store.next_step_url = reverse('resellers:store_dashboard', args=[store.id])
            store.next_step_icon = 'fas fa-eye'
    
    return render(request, 'resellers/resellerdashboard.html', {'stores': stores})


# resellers/views.py - Update create_store_step1

@login_required
@user_passes_test(is_reseller)
def create_store_step1(request):
    """Step 1: Create store basic details"""
    
    # Check if editing existing store
    store_id = request.session.get('temp_store_id')
    existing_store = None
    
    if store_id:
        existing_store = Store.objects.filter(id=store_id, reseller=request.user).first()
    
    if request.method == 'POST':
        form = StoreCreationForm(request.POST, request.FILES, instance=existing_store)
        
        if form.is_valid():
            store = form.save(commit=False)
            store.reseller = request.user
            
            if not existing_store:
                store.status = 'pending_payment'
            
            store.save()
            
            request.session['temp_store_id'] = store.id
            
            # If store already has plan and theme, go to payment
            if store.subscription_plan and store.theme:
                messages.success(request, 'Store details updated! Proceed to payment.')
                return redirect('resellers:create_order', store_id=store.id)
            elif store.subscription_plan:
                messages.success(request, 'Store details updated! Now select your theme.')
                return redirect('resellers:select_theme')
            else:
                messages.success(request, f'✅ Store "{store.store_name}" saved! Now select a subscription plan.')
                return redirect('resellers:select_plan')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = StoreCreationForm(instance=existing_store)
    
    context = {
        'form': form,
        'store': existing_store,
        'step': 1,         
        'total_steps': 4,  
        'step_title': 'Store Details',
        'can_go_back': False,
    }
    return render(request, 'resellers/create_store.html', context)

@login_required
@user_passes_test(is_reseller)
def select_plan(request):
    """Step 2: Select subscription plan"""
    
    store_id = request.session.get('temp_store_id')
    
    if not store_id:
        existing_store = Store.objects.filter(reseller=request.user, subscription_plan__isnull=True).first()
        if existing_store:
            store_id = existing_store.id
            request.session['temp_store_id'] = store_id
    
    if not store_id:
        messages.error(request, 'Please create a store first.')
        return redirect('resellers:create_store_step1')
    
    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    
    # Handle back/previous button
    if request.method == 'POST' and 'back' in request.POST:
        return redirect('resellers:create_store_step1')
    
    plans = SubscriptionPlan.objects.filter(is_active=True)
    
    if request.method == 'POST' and 'next' in request.POST:
        form = PlanSelectionForm(request.POST)
        
        if form.is_valid():
            plan = form.cleaned_data['plan_id']
            store.subscription_plan = plan
            store.save()
            
            request.session['selected_plan_id'] = plan.id
            
            messages.success(request, f'✓ Selected {plan.get_name_display()} plan!')
            return redirect('resellers:select_theme')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = PlanSelectionForm()
    
    # Pre-select current plan if exists
    if store.subscription_plan:
        form = PlanSelectionForm(initial={'plan_id': store.subscription_plan.id})
    
    context = {
        'form': form,
        'store': store,
        'plans': plans,
        'step': 2,
        'total_steps': 4,
        'can_go_back': True,
        'back_url': 'resellers:create_store_step1',
    }
    return render(request, 'resellers/select_plan.html', context)


@login_required
@user_passes_test(is_reseller)
def select_theme(request):
    """Step 3: Select theme"""
    
    store_id = request.session.get('temp_store_id')
    plan_id = request.session.get('selected_plan_id')
    
    if not store_id or not plan_id:
        existing_store = Store.objects.filter(
            reseller=request.user, 
            subscription_plan__isnull=False,
        ).first()
        if existing_store:
            store_id = existing_store.id
            plan_id = existing_store.subscription_plan.id
            request.session['temp_store_id'] = store_id
            request.session['selected_plan_id'] = plan_id
    
    if not store_id or not plan_id:
        messages.error(request, 'Please complete previous steps.')
        return redirect('resellers:create_store_step1')
    
    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    plan = get_object_or_404(SubscriptionPlan, id=plan_id)
    themes = StoreTheme.objects.filter(is_active=True)
    
    # Handle back/previous button - go back to plan selection
    if request.method == 'POST' and 'back' in request.POST:
        return redirect('resellers:select_plan')
    
    if request.method == 'POST' and 'next' in request.POST:
        theme_id = request.POST.get('theme_id')
        
        if not theme_id:
            messages.error(request, 'Please select a theme to continue.')
        else:
            try:
                theme = StoreTheme.objects.get(id=theme_id, is_active=True)
                store.theme = theme
                store.save()
                
                messages.success(request, f'✓ Selected {theme.name} theme!')
                return redirect('resellers:create_order', store_id=store.id)
            except StoreTheme.DoesNotExist:
                messages.error(request, 'Selected theme is not available.')
    
    # Get limits for display
    single_theme = themes.filter(theme_type='single').first()
    multiple_theme = themes.filter(theme_type='multiple').first()
    
    context = {
        'store': store,
        'plan': plan,
        'single_theme': single_theme,
        'multiple_theme': multiple_theme,
        'multiple_theme_limit': plan.multiple_theme_limit,
        'step': 3,
        'total_steps': 4,
        'can_go_back': True,
        'back_url': 'resellers:select_plan',
    }
    return render(request, 'resellers/select_theme.html', context)


@login_required
@user_passes_test(is_reseller)
def preview_single_theme(request, theme_id):
    """Preview Single Product Theme"""
    theme = get_object_or_404(StoreTheme, id=theme_id, theme_type='single', is_active=True)
    
    # Get the current store or create a dummy store for preview
    store = None
    if request.user.is_authenticated:
        store = Store.objects.filter(reseller=request.user).first()
    
    # Sample product data for preview
    sample_product = {
        'name': 'Premium Product Sample',
        'description': 'This is a sample product demonstration for the single product theme. You can showcase your main product with detailed description, features, and benefits.',
        'price': '49.99',
        'image_url': None,  # You can add a default image
        'features': [
            'Premium quality materials',
            '1 year warranty',
            'Free shipping worldwide',
            '30-day money-back guarantee',
            '24/7 customer support'
        ]
    }
    
    context = {
        'theme': theme,
        'store': store,
        'product': sample_product,
        'is_preview': True,
    }
    return render(request, 'resellers/preview_single_theme.html', context)


@login_required
@user_passes_test(is_reseller)
def preview_multiple_theme(request, theme_id):
    """Preview Multiple Products Theme"""
    theme = get_object_or_404(StoreTheme, id=theme_id, theme_type='multiple', is_active=True)
    
    # Get the current store or create a dummy store for preview
    store = None
    plan_limit = 12  # Default limit
    
    if request.user.is_authenticated:
        store = Store.objects.filter(reseller=request.user).first()
        if store and store.subscription_plan:
            plan_limit = store.subscription_plan.multiple_theme_limit
    
    # Sample products data for preview
    sample_products = []
    for i in range(1, min(plan_limit, 9)):  # Show up to 8 sample products
        sample_products.append({
            'id': i,
            'name': f'Sample Product {i}',
            'description': f'This is a sample product {i} demonstration for the multiple products theme.',
            'price': f'{39.99 + i * 10:.2f}',
            'image_url': None,
            'category': ['Electronics', 'Clothing', 'Home', 'Sports'][i % 4],
        })
    
    context = {
        'theme': theme,
        'store': store,
        'products': sample_products,
        'product_limit': plan_limit,
        'is_preview': True,
    }
    return render(request, 'resellers/preview_multiple_theme.html', context)
# resellers/views.py - Update create_order view

@login_required
@user_passes_test(is_reseller)
def create_order(request, store_id=None):
    """Step 4: Create Razorpay order"""
    
    # Get store from URL parameter or session
    if store_id:
        store = get_object_or_404(Store, id=store_id, reseller=request.user)
        request.session['temp_store_id'] = store.id
    else:
        store_id = request.session.get('temp_store_id')
        if not store_id:
            messages.error(request, 'Please complete store setup first.')
            return redirect('resellers:create_store_step1')
        store = get_object_or_404(Store, id=store_id, reseller=request.user)
    
    # Handle back/previous button
    if request.method == 'POST' and 'back' in request.POST:
        return redirect('resellers:select_theme')
    
    if not store.subscription_plan or not store.theme:
        messages.error(request, 'Please select plan and theme first.')
        return redirect('resellers:select_plan')
    
    plan = store.subscription_plan
    amount = plan.price
    
    # Generate unique order ID
    order_id = generate_order_id()
    
    # Create Razorpay order
    try:
        razorpay_order = create_razorpay_order(amount)
        
        # Create transaction record
        transaction = StoreTransaction.objects.create(
            store=store,
            user=request.user,
            plan_name=plan.get_name_display(),
            plan_price=plan.price,
            plan_duration=plan.get_duration_display(),
            store_name=store.store_name,
            razorpay_order_id=razorpay_order['id'],
            order_id=order_id,
            amount=amount,
            status='created'
        )
        
        request.session['transaction_id'] = transaction.id
        
        # Generate store URL
        current_host = request.get_host()
        if 'localhost' in current_host or '127.0.0.1' in current_host:
            port = ':8000' if ':' not in current_host else f":{current_host.split(':')[1]}"
            store_url = f"http://{store.subdomain}.localhost{port}"
        else:
            store_url = store.get_full_url(request)
        
        context = {
            'store': store,
            'plan': plan,
            'amount': amount,
            'razorpay_order_id': razorpay_order['id'],
            'razorpay_key_id': settings.RAZORPAY_KEY_ID,
            'order_id': order_id,
            'transaction': transaction,
            'store_url': store_url,
            'step': 4,
            'total_steps': 4,
            'step_title': 'Complete Payment',
            'can_go_back': True,
            'back_url': 'resellers:select_theme',
        }
        return render(request, 'resellers/payment.html', context)
        
    except Exception as e:
        messages.error(request, f'Error creating order: {str(e)}')
        return redirect('resellers:select_plan')

@csrf_exempt
@require_http_methods(["POST"])
@login_required
@user_passes_test(is_reseller)
def payment_success(request):
    """Handle payment success callback"""
    
    if request.method == 'POST':
        razorpay_order_id = request.POST.get('razorpay_order_id')
        razorpay_payment_id = request.POST.get('razorpay_payment_id')
        razorpay_signature = request.POST.get('razorpay_signature')
        
        # Verify signature
        if verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
            # Get transaction
            transaction = get_object_or_404(StoreTransaction, razorpay_order_id=razorpay_order_id)
            store = transaction.store
            
            # Update transaction
            transaction.razorpay_payment_id = razorpay_payment_id
            transaction.razorpay_signature = razorpay_signature
            transaction.status = 'success'
            transaction.save()
            
            # Activate store
            plan = store.subscription_plan
            store.payment_status = True
            store.subscription_start = timezone.now()
            
            if plan.duration == 'monthly':
                store.subscription_end = timezone.now() + timezone.timedelta(days=30)
            elif plan.duration == 'yearly':
                store.subscription_end = timezone.now() + timezone.timedelta(days=365)
            else:  # lifetime
                store.subscription_end = None
            
            store.status = 'active'
            store.is_published = True
            store.published_at = timezone.now()
            store.save()
            
            # Clear session
            request.session.pop('temp_store_id', None)
            request.session.pop('selected_plan_id', None)
            request.session.pop('transaction_id', None)
            
            # ✅ FIX: Generate correct store URL
            current_host = request.get_host()
            if 'localhost' in current_host or '127.0.0.1' in current_host:
                # Local development
                port = ':8000' if ':' not in current_host else f":{current_host.split(':')[1]}"
                store_url = f"http://{store.subdomain}.localhost{port}"
            else:
                # Production
                host = request.get_host().split(':')[0]
                host_parts = host.split('.')
                if len(host_parts) >= 3:
                    base_domain = '.'.join(host_parts[1:])
                    store_url = f"https://{store.subdomain}.{base_domain}"
                else:
                    store_url = f"https://{store.subdomain}.{host}"
            
            # Send email
            try:
                send_mail(
                    subject='🎉 Payment Successful! Your Store is Live!',
                    message=f"""
Dear {request.user.first_name},

Congratulations! Your store "{store.store_name}" is now LIVE!

📌 Store Details:
• Store Name: {store.store_name}
• Store URL: {store_url}
• Plan: {plan.get_name_display()} ({plan.get_duration_display()})
• Theme: {store.theme.name}
• Max Products: {store.get_max_products()}
• Transaction ID: {transaction.order_id}

🔗 Share your store link:
{store_url}

Happy Selling!

Regards,
Drapso Team
                    """,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[request.user.email],
                    fail_silently=False,
                )
            except Exception as e:
                print(f"Email error: {e}")
            
            messages.success(request, f'🎉 Payment successful! Your store "{store.store_name}" is now LIVE!')
            messages.success(request, f'🔗 Store URL: {store_url}')
            
            return redirect('resellers:store_dashboard', store_id=store.id)
        else:
            messages.error(request, 'Payment verification failed. Please contact support.')
            return redirect('resellers:payment_failed')

@login_required
@user_passes_test(is_reseller)
def payment_failed(request):
    """Handle payment failure"""
    messages.error(request, 'Payment failed. Please try again.')
    return redirect('resellers:select_plan')


# resellers/views.py - Replace your store_dashboard view

# resellers/views.py - Update the pending_payment case in store_dashboard

@login_required
@user_passes_test(is_reseller)
def store_dashboard(request, store_id):
    """Store dashboard - Redirects based on store status with expiry check"""
    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    
    # ✅ Check and update subscription expiry status
    store.check_and_update_expiry()
    
    # Case 1: No subscription plan selected
    if not store.subscription_plan:
        messages.warning(request, 'Please select a subscription plan first.')
        request.session['temp_store_id'] = store.id
        return redirect('resellers:select_plan')
    
    # Case 2: No theme selected
    if not store.theme:
        messages.warning(request, 'Please select a theme for your store.')
        request.session['temp_store_id'] = store.id
        request.session['selected_plan_id'] = store.subscription_plan.id
        return redirect('resellers:select_theme')
    
    # Case 3: Payment pending
    if store.status == 'pending_payment' or not store.payment_status:
        messages.warning(request, 'Complete payment to activate your store.')
        return redirect('resellers:create_order', store_id=store.id)
    
    # Case 4: Subscription expired
    if store.status == 'expired':
        expiry_date = store.subscription_end.strftime('%B %d, %Y') if store.subscription_end else 'unknown date'
        messages.error(request, f'Your subscription expired on {expiry_date}. Please renew to reactivate your store. All your products are still saved and will be restored immediately upon renewal.')
        return redirect('resellers:manage_subscription', store_id=store.id)
    
    # Case 5: Store suspended
    if store.status == 'suspended':
        messages.error(request, 'Your store has been suspended. Please contact support at support@example.com')
        return redirect('resellers:reseller_dashboard')
    
    # Case 6: Store is active - show dashboard
    if store.status == 'active' and store.is_published:
        # Generate store URL
        current_host = request.get_host()
        if 'localhost' in current_host or '127.0.0.1' in current_host:
            port = ':8000' if ':' not in current_host else f":{current_host.split(':')[1]}"
            store_url = f"http://{store.subdomain}.localhost{port}"
        else:
            store_url = store.get_full_url(request)
        
        # Get max products based on theme and plan
        max_products = store.get_max_products()
        
        # ✅ Get ResellerProduct counts
        try:
            total_products = store.products.filter(is_active=True).count()
            published_products = store.products.filter(is_active=True, is_published=True).count()
            draft_products = store.products.filter(is_active=True, is_published=False).count()
        except Exception:
            total_products = 0
            published_products = 0
            draft_products = 0
        
        # Calculate subscription info for display
        days_until_expiry = store.days_until_expiry()
        is_expiring_soon = store.is_expiring_soon(7)
        
        # Add warning message if expiring soon
        if is_expiring_soon and days_until_expiry:
            messages.warning(request, f'⚠️ Your subscription will expire in {days_until_expiry} days. Please renew to avoid interruption.')
        
        context = {
            'store': store,
            'store_url': store_url,
            'max_products': max_products,
            'total_products': total_products,
            'published_products': published_products,
            'draft_products': draft_products,
            'theme_type': store.theme.theme_type if store.theme else None,
            'days_until_expiry': days_until_expiry,
            'is_expiring_soon': is_expiring_soon,
            'subscription_plan': store.subscription_plan,
            'subscription_end': store.subscription_end,
        }
        return render(request, 'resellers/store_dashboard.html', context)
    
    # Fallback for any other status
    messages.info(request, 'Your store is being set up. Please complete the steps below.')
    return redirect('resellers:create_store_step1')
     
@login_required
@user_passes_test(is_reseller)
def preview_store(request, store_id):
    store = get_object_or_404(Store, id=store_id, reseller=request.user)

    current_host = request.get_host()
    if 'localhost' in current_host or '127.0.0.1' in current_host:
        port = ':8000' if ':' not in current_host else f":{current_host.split(':')[1]}"
        store_url = f"http://{store.subdomain}.localhost{port}"
    else:
        store_url = store.get_full_url(request)

    # 🔥 FULL DATA LOAD
    all_products = store.products.filter(
        is_active=True
    ).select_related(
        'category', 'subcategory'
    ).prefetch_related(
        'additional_images',
        Prefetch(
            'variants',
            queryset=ResellerProductVariant.objects.filter(is_active=True)
            .prefetch_related('additional_images')
        )
    )

    published_products = all_products.filter(is_published=True)
    draft_products = all_products.filter(is_published=False)

    context = {
        'store': store,
        'store_url': store_url,
        'products': all_products,
        'published_products': published_products,
        'draft_products': draft_products,
        'published_count': published_products.count(),
        'draft_count': draft_products.count(),
        'is_preview': True,
    }
    return render(request, 'resellers/preview_store.html', context)

@login_required
@user_passes_test(is_reseller)
def copy_store_link(request, store_id):
    """AJAX copy link with fixed URL"""
    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    
    # Fix URL for local development
    current_host = request.get_host()
    if 'localhost' in current_host or '127.0.0.1' in current_host:
        port = ':8000' if ':' not in current_host else f":{current_host.split(':')[1]}"
        store_url = f"http://{store.subdomain}.localhost{port}"
    else:
        store_url = store.get_full_url(request)
    
    return JsonResponse({
        'success': True, 
        'store_url': store_url,
        'message': 'Link copied to clipboard!'
    })


# resellers/views.py

from django.shortcuts import render
from django.http import Http404
from general.views import home

from django.shortcuts import render
from django.http import Http404
from django.db.models import Prefetch
from products.models import *

def store_frontend(request):

    if not getattr(request, 'is_store_request', False):
        raise Http404("Not a store request")

    store = getattr(request, 'current_store', None)

    if not store:
        return render(request, 'resellers/store_not_found.html')

    if store.status in ['expired', 'suspended'] or not store.is_published:
        return render(request, 'resellers/store_not_found.html')

    try:
        store.increment_visitor()
    except Exception:
        pass

    current_host = request.get_host()
    if 'localhost' in current_host or '127.0.0.1' in current_host:
        port = ':8000' if ':' not in current_host else f":{current_host.split(':')[1]}"
        store_url = f"http://{store.subdomain}.localhost{port}"
    else:
        store_url = store.get_full_url(request)

    # 🔥 FULL DATA LOAD (ONLY PUBLISHED)
    products = store.products.filter(
        is_active=True,
        is_published=True
    ).select_related(
        'category', 'subcategory'
    ).prefetch_related(
        'additional_images',
        Prefetch(
            'variants',
            queryset=ResellerProductVariant.objects.filter(is_active=True)
            .prefetch_related('additional_images')
        )
    )

    context = {
        'store': store,
        'store_url': store_url,
        'products': products,
        'products_count': products.count(),
    }

    template = 'resellers/store_frontend.html'
    return render(request, template, context)


from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import os

def is_admin(user):
    return user.is_superuser or (hasattr(user, 'is_admin') and user.is_admin)

@login_required
@user_passes_test(is_admin)
def plan_list(request):
    plans = SubscriptionPlan.objects.all()
    return render(request, 'resellers/admin/plan_list.html', {'plans': plans})

@login_required
@user_passes_test(is_admin)
def plan_create(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        duration = request.POST.get('duration')
        price = request.POST.get('price')
        multiple_theme_limit = request.POST.get('multiple_theme_limit')
        features = request.POST.get('features')
        
        # Validation
        if not all([name, duration, price, multiple_theme_limit]):
            messages.error(request, 'All fields are required!')
            return render(request, 'resellers/admin/plan_form.html')
        
        try:
            plan = SubscriptionPlan.objects.create(
                name=name,
                duration=duration,
                price=price,
                multiple_theme_limit=multiple_theme_limit,
                features=features
            )
            messages.success(request, f'Plan "{plan.get_name_display()}" created successfully!')
            return redirect('resellers:plan_list')
        except Exception as e:
            messages.error(request, f'Error creating plan: {str(e)}')
    
    return render(request, 'resellers/admin/plan_form.html')

@login_required
@user_passes_test(is_admin)
def plan_edit(request, plan_id):
    plan = get_object_or_404(SubscriptionPlan, id=plan_id)
    
    if request.method == 'POST':
        plan.name = request.POST.get('name')
        plan.duration = request.POST.get('duration')
        plan.price = request.POST.get('price')
        plan.multiple_theme_limit = request.POST.get('multiple_theme_limit')
        plan.features = request.POST.get('features')
        plan.save()
        messages.success(request, f'Plan "{plan.get_name_display()}" updated successfully!')
        return redirect('resellers:plan_list')
    
    return render(request, 'resellers/admin/plan_form.html', {'plan': plan})

@login_required
@user_passes_test(is_admin)
def plan_delete(request, plan_id):
    plan = get_object_or_404(SubscriptionPlan, id=plan_id)
    if request.method == 'POST':
        plan_name = plan.get_name_display()
        plan.delete()
        messages.success(request, f'Plan "{plan_name}" deleted successfully!')
        return redirect('resellers:plan_list')
    
    return render(request, 'resellers/admin/plan_confirm_delete.html', {'plan': plan})

@login_required
@user_passes_test(is_admin)
def theme_list(request):
    themes = StoreTheme.objects.all()
    return render(request, 'resellers/admin/theme_list.html', {'themes': themes})

@login_required
@user_passes_test(is_admin)
def theme_create(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        theme_type = request.POST.get('theme_type')
        description = request.POST.get('description')
        
        # Validation
        if not all([name, theme_type]):
            messages.error(request, 'Name and Theme Type are required!')
            return render(request, 'resellers/admin/theme_form.html')
        
        try:
            theme = StoreTheme.objects.create(
                name=name,
                theme_type=theme_type,
                description=description
            )
            
            # Handle preview image upload
            if request.FILES.get('preview_image'):
                theme.preview_image = request.FILES['preview_image']
            
            # Handle thumbnail upload
            if request.FILES.get('thumbnail'):
                theme.thumbnail = request.FILES['thumbnail']
            
            theme.save()
            messages.success(request, f'Theme "{theme.name}" created successfully!')
            return redirect('resellers:theme_list')
        except Exception as e:
            messages.error(request, f'Error creating theme: {str(e)}')
    
    return render(request, 'resellers/admin/theme_form.html')

@login_required
@user_passes_test(is_admin)
def theme_edit(request, theme_id):
    theme = get_object_or_404(StoreTheme, id=theme_id)
    
    if request.method == 'POST':
        theme.name = request.POST.get('name')
        theme.theme_type = request.POST.get('theme_type')
        theme.description = request.POST.get('description')
        
        # Handle preview image upload - remove old if new is uploaded
        if request.FILES.get('preview_image'):
            # Delete old image if exists
            if theme.preview_image:
                if os.path.isfile(theme.preview_image.path):
                    os.remove(theme.preview_image.path)
            theme.preview_image = request.FILES['preview_image']
        
        # Handle thumbnail upload - remove old if new is uploaded
        if request.FILES.get('thumbnail'):
            if theme.thumbnail:
                if os.path.isfile(theme.thumbnail.path):
                    os.remove(theme.thumbnail.path)
            theme.thumbnail = request.FILES['thumbnail']
        
        theme.save()
        messages.success(request, f'Theme "{theme.name}" updated successfully!')
        return redirect('resellers:theme_list')
    
    return render(request, 'resellers/admin/theme_form.html', {'theme': theme})

@login_required
@user_passes_test(is_admin)
def theme_delete(request, theme_id):
    theme = get_object_or_404(StoreTheme, id=theme_id)
    if request.method == 'POST':
        theme_name = theme.name
        # Delete image files from storage
        if theme.preview_image:
            if os.path.isfile(theme.preview_image.path):
                os.remove(theme.preview_image.path)
        if theme.thumbnail:
            if os.path.isfile(theme.thumbnail.path):
                os.remove(theme.thumbnail.path)
        theme.delete()
        messages.success(request, f'Theme "{theme_name}" deleted successfully!')
        return redirect('resellers:theme_list')
    
    return render(request, 'resellers/admin/theme_confirm_delete.html', {'theme': theme})

# resellers/views.py - Updated admin_stores view

@login_required
@user_passes_test(is_admin)
def admin_stores(request):
    stores = Store.objects.all().select_related('reseller', 'subscription_plan', 'theme')
    # Remove prefetch_related('products') since it doesn't exist
    
    # Calculate statistics
    total_stores = stores.count()
    active_stores = stores.filter(status='active').count()
    pending_stores = stores.filter(status='pending_payment').count()
    expired_stores = stores.filter(status='expired').count()
    suspended_stores = stores.filter(status='suspended').count()
    
    # Calculate total revenue from successful transactions
    transactions = StoreTransaction.objects.filter(status='success')
    total_revenue = sum(t.amount for t in transactions)
    
    context = {
        'stores': stores,
        'total_stores': total_stores,
        'active_stores': active_stores,
        'pending_stores': pending_stores,
        'expired_stores': expired_stores,
        'suspended_stores': suspended_stores,
        'total_revenue': total_revenue,
    }
    return render(request, 'resellers/admin_stores.html', context)

@login_required
@user_passes_test(is_admin)
def admin_store_detail(request, store_id):
    store = get_object_or_404(Store, id=store_id)
    
    # Generate correct store URL based on environment
    current_host = request.get_host()
    if 'localhost' in current_host or '127.0.0.1' in current_host:
        port = ':8000' if ':' not in current_host else f":{current_host.split(':')[1]}"
        store_url = f"http://{store.subdomain}.localhost{port}"
    else:
        # Production environment
        host = request.get_host().split(':')[0]
        host_parts = host.split('.')
        if len(host_parts) >= 3:
            base_domain = '.'.join(host_parts[1:])
            store_url = f"https://{store.subdomain}.{base_domain}"
        else:
            store_url = f"https://{store.subdomain}.{host}"
    
    # Calculate subscription info
    days_until_expiry = store.days_until_expiry()
    is_expiring_soon = store.is_expiring_soon(7)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            store.status = 'active'
            store.is_published = True
            if not store.subscription_start:
                store.subscription_start = timezone.now()
            store.save()
            messages.success(request, f'✅ Store "{store.store_name}" has been approved and is now live!')
        elif action == 'suspend':
            store.status = 'suspended'
            store.is_published = False
            store.save()
            messages.warning(request, f'⚠️ Store "{store.store_name}" has been suspended.')
        elif action == 'activate':
            store.status = 'active'
            store.is_published = True
            store.save()
            messages.success(request, f'✅ Store "{store.store_name}" has been activated.')
        return redirect('resellers:admin_store_detail', store_id=store.id)
    
    return render(request, 'resellers/admin/admin_store_detail.html', {
        'store': store,
        'store_url': store_url,
        'days_until_expiry': days_until_expiry,
        'is_expiring_soon': is_expiring_soon,
    })

from django.utils import timezone
from datetime import timedelta
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

# Add these to your existing resellers/views.py

@login_required
@user_passes_test(is_reseller)
def manage_subscription(request, store_id):
    """Manage store subscription - renew, upgrade, or subscribe to new plan"""
    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    
    store.check_and_update_expiry()
    
    remaining_days = store.get_remaining_days()
    is_expired = store.status == 'expired'
    can_renew = store.can_renew_early()
    can_upgrade = store.can_upgrade()
    
    all_plans_list = SubscriptionPlan.objects.filter(is_active=True)
    plan_priority = {'silver': 1, 'gold': 2, 'platinum': 3}
    
    renewal_plan = store.subscription_plan if store.subscription_plan else None
    
    # All plans for new subscription (when expired)
    all_plans = [{'plan': plan} for plan in all_plans_list]
    
    # Upgrade plans (higher tiers only for active subscriptions)
    upgrade_plans = []
    if store.subscription_plan and not is_expired:
        current_priority = plan_priority.get(store.subscription_plan.name, 0)
        for plan in all_plans_list:
            if plan_priority.get(plan.name, 0) > current_priority:
                upgrade_plans.append({
                    'plan': plan,
                    'upgrade_price': store.calculate_prorated_upgrade_price(plan)
                })
    
    renewal_message = ""
    if not is_expired and remaining_days > 0 and remaining_days <= 7:
        renewal_message = f"Your subscription expires in {remaining_days} days. Renew now to add {remaining_days} extra days to your new subscription period!"
    
    context = {
        'store': store,
        'renewal_plan': renewal_plan,
        'upgrade_plans': upgrade_plans,
        'all_plans': all_plans,
        'remaining_days': remaining_days,
        'is_expired': is_expired,
        'can_renew': can_renew,
        'can_upgrade': can_upgrade,
        'renewal_message': renewal_message,
        'current_plan': store.subscription_plan,
        'days_until_expiry': store.days_until_expiry(),
        'is_expiring_soon': store.is_expiring_soon(7),
        'subscription_end': store.subscription_end,
    }
    
    return render(request, 'resellers/manage_subscription.html', context)


@login_required
@user_passes_test(is_reseller)
def process_renewal(request, store_id, plan_id=None):
    """Process renewal or upgrade payment"""
    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    
    is_upgrade = False
    new_plan = None
    
    if plan_id:
        new_plan = get_object_or_404(SubscriptionPlan, id=plan_id, is_active=True)
        if store.subscription_plan and store.subscription_plan.id != new_plan.id:
            if not store.can_upgrade_plan(new_plan):
                messages.error(request, 'You can only upgrade to higher tier plans.')
                return redirect('resellers:manage_subscription', store_id=store.id)
            is_upgrade = True
    else:
        if not store.subscription_plan:
            messages.error(request, 'No subscription plan found.')
            return redirect('resellers:manage_subscription', store_id=store.id)
        new_plan = store.subscription_plan
    
    remaining_days = store.get_remaining_days() if not is_upgrade else 0
    
    if not is_upgrade and not store.can_renew_early():
        messages.error(request, 'Renewal is only available when 7 days or less remaining, or after expiry.')
        return redirect('resellers:manage_subscription', store_id=store.id)
    
    if is_upgrade:
        amount = store.calculate_prorated_upgrade_price(new_plan)
        if amount <= 0:
            amount = new_plan.price
    else:
        amount = new_plan.price
    
    order_id = generate_order_id()
    
    try:
        razorpay_order = create_razorpay_order(amount)
        
        transaction = StoreTransaction.objects.create(
            store=store,
            user=request.user,
            plan_name=new_plan.get_name_display(),
            plan_price=new_plan.price,
            plan_duration=new_plan.get_duration_display(),
            store_name=store.store_name,
            razorpay_order_id=razorpay_order['id'],
            order_id=order_id,
            amount=amount,
            status='created'
        )
        
        request.session['renewal_data'] = {
            'transaction_id': transaction.id,
            'store_id': store.id,
            'plan_id': new_plan.id,
            'is_upgrade': is_upgrade,
            'remaining_days': remaining_days,
            'old_plan_name': store.subscription_plan.get_name_display() if store.subscription_plan else None,
        }
        
        current_host = request.get_host()
        if 'localhost' in current_host or '127.0.0.1' in current_host:
            port = ':8000' if ':' not in current_host else f":{current_host.split(':')[1]}"
            store_url = f"http://{store.subdomain}.localhost{port}"
        else:
            store_url = store.get_full_url(request)
        
        context = {
            'store': store,
            'plan': new_plan,
            'amount': amount,
            'razorpay_order_id': razorpay_order['id'],
            'razorpay_key_id': settings.RAZORPAY_KEY_ID,
            'order_id': order_id,
            'transaction': transaction,
            'store_url': store_url,
            'is_renewal': not is_upgrade,
            'is_upgrade': is_upgrade,
            'old_plan': store.subscription_plan,
            'remaining_days': remaining_days,
            'will_get_extra_days': remaining_days > 0 and not is_upgrade,
        }
        return render(request, 'resellers/renewal_payment.html', context)
        
    except Exception as e:
        messages.error(request, f'Error creating order: {str(e)}')
        return redirect('resellers:manage_subscription', store_id=store.id)


@login_required
@user_passes_test(is_reseller)
def subscribe_new_plan(request, store_id, plan_id):
    """Subscribe to a new plan (for expired subscriptions)"""
    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    new_plan = get_object_or_404(SubscriptionPlan, id=plan_id, is_active=True)
    
    if store.status != 'expired':
        messages.error(request, 'This option is only available for expired subscriptions.')
        return redirect('resellers:manage_subscription', store_id=store.id)
    
    amount = new_plan.price
    order_id = generate_order_id()
    
    try:
        razorpay_order = create_razorpay_order(amount)
        
        transaction = StoreTransaction.objects.create(
            store=store,
            user=request.user,
            plan_name=new_plan.get_name_display(),
            plan_price=new_plan.price,
            plan_duration=new_plan.get_duration_display(),
            store_name=store.store_name,
            razorpay_order_id=razorpay_order['id'],
            order_id=order_id,
            amount=amount,
            status='created'
        )
        
        request.session['new_subscription_data'] = {
            'transaction_id': transaction.id,
            'store_id': store.id,
            'plan_id': new_plan.id,
            'old_plan_name': store.subscription_plan.get_name_display() if store.subscription_plan else None,
        }
        
        current_host = request.get_host()
        if 'localhost' in current_host or '127.0.0.1' in current_host:
            port = ':8000' if ':' not in current_host else f":{current_host.split(':')[1]}"
            store_url = f"http://{store.subdomain}.localhost{port}"
        else:
            store_url = store.get_full_url(request)
        
        context = {
            'store': store,
            'plan': new_plan,
            'amount': amount,
            'razorpay_order_id': razorpay_order['id'],
            'razorpay_key_id': settings.RAZORPAY_KEY_ID,
            'order_id': order_id,
            'transaction': transaction,
            'store_url': store_url,
            'is_new_subscription': True,
            'old_plan': store.subscription_plan,
            'products_count': store.products.count() if hasattr(store, 'products') else 0,
        }
        return render(request, 'resellers/new_subscription_payment.html', context)
        
    except Exception as e:
        messages.error(request, f'Error creating order: {str(e)}')
        return redirect('resellers:manage_subscription', store_id=store.id)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
@user_passes_test(is_reseller)
def renewal_payment_callback(request):
    """Handle renewal/upgrade payment callback"""
    
    razorpay_order_id = request.POST.get('razorpay_order_id')
    razorpay_payment_id = request.POST.get('razorpay_payment_id')
    razorpay_signature = request.POST.get('razorpay_signature')
    
    if verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
        transaction = get_object_or_404(StoreTransaction, razorpay_order_id=razorpay_order_id)
        store = transaction.store
        renewal_data = request.session.get('renewal_data', {})
        
        transaction.razorpay_payment_id = razorpay_payment_id
        transaction.razorpay_signature = razorpay_signature
        transaction.status = 'success'
        transaction.save()
        
        new_plan_id = renewal_data.get('plan_id')
        new_plan = get_object_or_404(SubscriptionPlan, id=new_plan_id) if new_plan_id else store.subscription_plan
        
        is_upgrade = renewal_data.get('is_upgrade', False)
        remaining_days = renewal_data.get('remaining_days', 0)
        old_plan_name = renewal_data.get('old_plan_name')
        
        existing_products_count = store.products.count() if hasattr(store, 'products') else 0
        
        store.renew_subscription(plan=new_plan, is_upgrade=is_upgrade, remaining_days_to_add=remaining_days if not is_upgrade else 0)
        
        request.session.pop('renewal_data', None)
        
        try:
            if is_upgrade:
                subject = f"🎉 Store Upgraded to {new_plan.get_name_display().title()} Plan!"
                message = f"""
Dear {store.reseller.first_name},

Your store "{store.store_name}" has been upgraded!

📊 Upgrade Details:
• Old Plan: {old_plan_name}
• New Plan: {new_plan.get_name_display().title()} ({new_plan.get_duration_display()})
• Amount Paid: ${transaction.amount}

✅ Your {existing_products_count} products have been preserved!

Transaction ID: {transaction.order_id}

Thank you for upgrading!
"""
            else:
                new_expiry = store.subscription_end.strftime('%B %d, %Y') if store.subscription_end else 'Lifetime'
                extra_days_msg = f" You also received {remaining_days} extra days!" if remaining_days > 0 else ""
                subject = f"🔄 Store '{store.store_name}' Subscription Renewed!"
                message = f"""
Dear {store.reseller.first_name},

Your store "{store.store_name}" subscription has been renewed!

📊 Renewal Details:
• Plan: {new_plan.get_name_display().title()} ({new_plan.get_duration_display()})
• Amount Paid: ${transaction.amount}
• New Expiry Date: {new_expiry}{extra_days_msg}

✅ Your {existing_products_count} products have been preserved!

Transaction ID: {transaction.order_id}

Thank you for continuing with Drapso!
"""
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[store.reseller.email, store.contact_email],
                fail_silently=False,
            )
        except Exception as e:
            print(f"Email failed: {e}")
        
        if is_upgrade:
            messages.success(request, f'🎉 Upgraded to {new_plan.get_name_display().title()} plan! Your {existing_products_count} products preserved!')
        else:
            messages.success(request, f'🔄 Renewed successfully! Your {existing_products_count} products preserved!')
        
        return redirect('resellers:store_dashboard', store_id=store.id)
    else:
        messages.error(request, 'Payment verification failed.')
        return redirect('resellers:manage_subscription', store_id=request.session.get('renewal_data', {}).get('store_id'))


@csrf_exempt
@require_http_methods(["POST"])
@login_required
@user_passes_test(is_reseller)
def new_subscription_callback(request):
    """Handle new subscription payment callback - PRESERVES ALL PRODUCTS"""
    
    razorpay_order_id = request.POST.get('razorpay_order_id')
    razorpay_payment_id = request.POST.get('razorpay_payment_id')
    razorpay_signature = request.POST.get('razorpay_signature')
    
    if verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
        transaction = get_object_or_404(StoreTransaction, razorpay_order_id=razorpay_order_id)
        store = transaction.store
        sub_data = request.session.get('new_subscription_data', {})
        
        transaction.razorpay_payment_id = razorpay_payment_id
        transaction.razorpay_signature = razorpay_signature
        transaction.status = 'success'
        transaction.save()
        
        new_plan_id = sub_data.get('plan_id')
        new_plan = get_object_or_404(SubscriptionPlan, id=new_plan_id)
        old_plan_name = sub_data.get('old_plan_name', 'None')
        
        existing_products_count = store.products.count() if hasattr(store, 'products') else 0
        
        # Update subscription - products remain untouched
        store.subscription_plan = new_plan
        store.subscription_start = timezone.now()
        
        if new_plan.duration == 'monthly':
            store.subscription_end = timezone.now() + timezone.timedelta(days=30)
        elif new_plan.duration == 'yearly':
            store.subscription_end = timezone.now() + timezone.timedelta(days=365)
        else:
            store.subscription_end = None
        
        store.payment_status = True
        store.status = 'active'
        store.is_published = True
        store.expiry_notified_7 = False
        store.expiry_notified_3 = False
        store.expiry_notified_expired = False
        
        if not store.published_at:
            store.published_at = timezone.now()
        
        store.save()
        
        request.session.pop('new_subscription_data', None)
        
        try:
            subject = f"🎉 Store '{store.store_name}' Reactivated with {new_plan.get_name_display().title()} Plan!"
            message = f"""
Dear {store.reseller.first_name},

Your store "{store.store_name}" has been reactivated!

📊 Subscription Details:
• Previous Plan: {old_plan_name}
• New Plan: {new_plan.get_name_display().title()} ({new_plan.get_duration_display()})
• Amount Paid: ${transaction.amount}
• New Expiry Date: {store.subscription_end.strftime('%B %d, %Y') if store.subscription_end else 'Lifetime'}

✅ IMPORTANT: Your {existing_products_count} products have been preserved!

Transaction ID: {transaction.order_id}

Thank you for continuing with Drapso!
"""
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[store.reseller.email, store.contact_email],
                fail_silently=False,
            )
        except Exception as e:
            print(f"Email failed: {e}")
        
        messages.success(request, f'🎉 Subscribed to {new_plan.get_name_display().title()} plan! Your {existing_products_count} products preserved! Store is LIVE!')
        
        return redirect('resellers:store_dashboard', store_id=store.id)
    else:
        messages.error(request, 'Payment verification failed.')
        return redirect('resellers:manage_subscription', store_id=request.session.get('new_subscription_data', {}).get('store_id'))