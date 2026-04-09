# theme_manager/views.py - UPDATED with store theme update
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse
from decimal import Decimal
from .services import ThemeSwitchService, RestorationService
from .models import ArchivedProductRecord, RestoreBatch, ThemeSwitchSession
from resellers.models import Store, StoreTheme

@login_required
def switch_to_single_theme(request, store_id):
    """Switch store to Single Product Theme"""
    
    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    service = ThemeSwitchService(store, request)
    
    can_switch, message = service.can_switch_to('single')
    if not can_switch:
        messages.error(request, message)
        return redirect('resellers:store_dashboard', store_id=store.id)
    
    from products.models import ResellerProduct
    active_products = ResellerProduct.objects.filter(store=store, is_active=True)
    product_count = active_products.count()
    
    if request.method == 'POST':
        keep_product_id = request.POST.get('keep_product_id')
        
        if not keep_product_id and product_count > 1:
            messages.error(request, 'Please select which product to keep')
            return redirect('theme_manager:switch_to_single', store_id=store.id)
        
        try:
            result = service.switch_to_single_theme(int(keep_product_id) if keep_product_id else None)
            
            # ✅ UPDATE STORE THEME
            single_theme = StoreTheme.objects.filter(theme_type='single', is_active=True).first()
            if single_theme:
                store.theme = single_theme
                store.save(update_fields=['theme', 'updated_at'])
                messages.info(request, f"Store theme updated to: {single_theme.name}")
            
            if result['success']:
                messages.success(request, f"✅ Switched to Single Product Theme! Kept 1 product, archived {result['archived_count']} products.")
                if result['archived_count'] > 0:
                    messages.info(request, f"📦 {result['archived_count']} products have been archived. You can restore them when switching back to Multiple Theme.")
            else:
                messages.error(request, result.get('message', 'Switch failed'))
        except Exception as e:
            messages.error(request, f'Error switching theme: {str(e)}')
        
        return redirect('resellers:store_dashboard', store_id=store.id)
    
    # GET request - show confirmation
    products = active_products.order_by('-is_featured', '-created_at')
    
    return render(request, 'theme_manager/confirm_switch_to_single.html', {
        'store': store,
        'products': products,
        'product_count': product_count,
        'will_archive': product_count - 1
    })


# theme_manager/views.py

@login_required
def switch_to_multi_theme(request, store_id):
    """Switch store to Multiple Products Theme - Restores archived products"""
    
    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    
    # Get plan limit
    plan_limit = store.subscription_plan.multiple_theme_limit if store.subscription_plan else 50
    
    # Get archived products
    archived_records = ArchivedProductRecord.objects.filter(store=store, is_restorable=True).select_related('product')
    archived_count = archived_records.count()
    
    if request.method == 'POST':
        restore_all = request.POST.get('restore_all') == 'true'
        restore_ids = request.POST.getlist('restore_ids')
        
        from products.models import ResellerProduct
        
        # Check available slots
        current_active = ResellerProduct.objects.filter(store=store, is_active=True).count()
        available_slots = plan_limit - current_active
        
        if available_slots <= 0 and archived_count > 0:
            messages.error(request, f"Cannot restore products. Your store has reached its limit of {plan_limit} products.")
            return redirect('resellers:store_dashboard', store_id=store.id)
        
        # Determine which products to restore
        if restore_all:
            products_to_restore = archived_records[:available_slots]
        else:
            products_to_restore = archived_records.filter(product_id__in=restore_ids)
        
        restored_count = 0
        
        for archive_record in products_to_restore:
            product = archive_record.product
            
            # Set product as ACTIVE
            product.is_active = True
            product.save(update_fields=['is_active', 'updated_at'])
            
            # Delete archive record
            archive_record.delete()
            restored_count += 1
        
        # Update store theme to MULTIPLE
        multi_theme = StoreTheme.objects.filter(theme_type='multiple', is_active=True).first()
        if multi_theme:
            store.theme = multi_theme
            store.save(update_fields=['theme', 'updated_at'])
        
        # Update session
        session, _ = ThemeSwitchSession.objects.get_or_create(
            store_id=store.id,
            defaults={'reseller_id': request.user.id}
        )
        session.current_theme = 'multiple'
        session.active_product_id = None
        session.last_switch_at = timezone.now()
        session.save()
        
        if restored_count > 0:
            messages.success(request, f"✅ Switched to Multiple Products Theme! Restored {restored_count} product(s).")
        else:
            messages.info(request, "Switched to Multiple Products Theme. No products were restored.")
        
        return redirect('resellers:store_dashboard', store_id=store.id)
    
    # GET request - show confirmation page
    from products.models import ResellerProduct
    current_active = ResellerProduct.objects.filter(store=store, is_active=True).count()
    
    return render(request, 'theme_manager/confirm_switch_to_multi.html', {
        'store': store,
        'archived_count': archived_count,
        'archived_products': archived_records[:10],
        'plan_limit': plan_limit,
        'current_active': current_active,
        'available_slots': plan_limit - current_active
    })

@login_required
def archived_products_list(request, store_id):
    """Display archived products with filtering"""
    
    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    service = RestorationService(store, request.user)
    
    capacity = service.get_restoration_capacity()
    
    search = request.GET.get('search', '')
    min_price = request.GET.get('min_price', '')
    max_price = request.GET.get('max_price', '')
    published_status = request.GET.get('published_status', '')
    sort_by = request.GET.get('sort', '-restore_priority')
    
    filters = {}
    if search:
        filters['search'] = search
    if min_price:
        filters['min_price'] = Decimal(min_price)
    if max_price:
        filters['max_price'] = Decimal(max_price)
    if published_status == 'published':
        filters['published_only'] = True
    elif published_status == 'draft':
        filters['draft_only'] = True
    
    archived_records = service.get_restorable_products(
        filters=filters if filters else None,
        sort_by=sort_by
    )
    
    # Add display data
    for record in archived_records:
        record.published_badge = 'Published' if record.product.is_published else 'Draft'
        record.published_class = 'badge-success' if record.product.is_published else 'badge-secondary'
    
    total_archived = archived_records.count()
    published_archived = archived_records.filter(product__is_published=True).count()
    draft_archived = total_archived - published_archived
    
    paginator = Paginator(archived_records, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'theme_manager/archived_products.html', {
        'store': store,
        'page_obj': page_obj,
        'capacity': capacity,
        'total_archived': total_archived,
        'published_archived': published_archived,
        'draft_archived': draft_archived,
        'can_restore_all': capacity['can_restore_all'] and total_archived > 0,
        'filters': {
            'search': search,
            'min_price': min_price,
            'max_price': max_price,
            'published_status': published_status,
            'sort': sort_by
        },
        'sort_options': [
            {'value': '-restore_priority', 'label': 'Priority (Highest first)'},
            {'value': '-archived_at', 'label': 'Recently Archived'},
            {'value': 'price_low', 'label': 'Price (Low to High)'},
            {'value': 'price_high', 'label': 'Price (High to Low)'},
            {'value': 'name_asc', 'label': 'Name (A to Z)'},
            {'value': 'published_first', 'label': 'Published First'},
        ]
    })


@login_required
def restore_archived_products(request, store_id):
    """Handle restoration of selected archived products"""
    
    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    
    if request.method != 'POST':
        return redirect('theme_manager:archived_products_list', store_id=store_id)
    
    product_ids = request.POST.getlist('restore_ids')
    restore_all = request.POST.get('restore_all') == 'true'
    
    if not product_ids and not restore_all:
        messages.warning(request, 'Please select products to restore')
        return redirect('theme_manager:archived_products_list', store_id=store_id)
    
    service = RestorationService(store, request.user)
    
    try:
        if not restore_all:
            validation = service.validate_restoration(product_ids)
            
            if not validation['valid']:
                messages.error(request, validation['error'])
                return redirect('theme_manager:archived_products_list', store_id=store_id)
            
            if request.POST.get('confirm') != 'yes':
                products_with_status = []
                for record in validation['products']:
                    products_with_status.append({
                        'id': record.product.id,
                        'name': record.product.name,
                        'price': record.product.selling_price,
                        'is_published': record.product.is_published,
                        'published_text': 'Published' if record.product.is_published else 'Draft',
                        'archived_at': record.archived_at
                    })
                
                return render(request, 'theme_manager/confirm_restore.html', {
                    'store': store,
                    'products_to_restore': products_with_status,
                    'capacity': service.get_restoration_capacity(),
                    'product_ids': product_ids
                })
        
        result = service.restore_products(product_ids, restore_all)
        
        if result['success']:
            published_count = sum(1 for r in result['restored'] if r.get('was_published', False))
            draft_count = result['restored_count'] - published_count
            messages.success(request, f"✅ Restored {result['restored_count']} product(s) ({published_count} published, {draft_count} draft). {result['remaining_capacity']} slot(s) remaining.")
        else:
            messages.warning(request, result['message'])
        
        if result['skipped'] or result['failed']:
            request.session['restore_results'] = result
        
        return redirect('theme_manager:archived_products_list', store_id=store_id)
        
    except Exception as e:
        messages.error(request, f'Error restoring products: {str(e)}')
        return redirect('theme_manager:archived_products_list', store_id=store_id)


@login_required
def restore_batch_status(request, store_id, batch_id):
    """View status of a restore batch"""
    
    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    batch = get_object_or_404(RestoreBatch, id=batch_id, store=store)
    
    return render(request, 'theme_manager/restore_batch_detail.html', {
        'store': store,
        'batch': batch
    })


@login_required
def theme_status_api(request, store_id):
    """AJAX endpoint to get current theme status"""
    
    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    
    session = ThemeSwitchSession.objects.filter(store_id=store.id).first()
    
    from products.models import ResellerProduct
    active_count = ResellerProduct.objects.filter(store=store, is_active=True).count()
    
    return JsonResponse({
        'current_theme': session.current_theme if session else 'multiple',
        'active_products_count': active_count,
        'max_products': store.get_max_products(),
        'can_switch_to_single': active_count > 1,
        'can_switch_to_multi': session and session.current_theme == 'single',
        'archived_count': ArchivedProductRecord.objects.filter(store=store, is_restorable=True).count()
    })