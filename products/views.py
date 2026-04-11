from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
import os

from .models import (
    Category, Subcategory, WholesellerProduct, WholesellerProductVariant,
    WholesellerProductImage, WholesellerVariantImage,
    ResellerProduct, ResellerProductVariant, ResellerProductImage,
    ResellerVariantImage, PriceChangeNotification
)
from .forms import *
from accounts.models import *
from resellers.models import Store


def is_wholeseller(user):
    return user.is_authenticated and user.role == User.Role.WHOLESELLER

def is_reseller(user):
    return user.is_authenticated and user.role == User.Role.RESELLER

def is_admin(user):
    return user.is_authenticated and (user.is_staff or user.role == User.Role.ADMIN)


# ============ CATEGORY VIEWS (Admin Only) ============

@login_required
@user_passes_test(is_admin)
def category_list(request):
    categories = Category.objects.all()
    return render(request, 'products/admin/category_list.html', {'categories': categories})


@login_required
@user_passes_test(is_admin)
def category_create(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category created successfully!')
            return redirect('products:category_list')
    else:
        form = CategoryForm()
    return render(request, 'products/admin/category_form.html', {'form': form, 'title': 'Create Category'})


@login_required
@user_passes_test(is_admin)
def category_edit(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    if request.method == 'POST':
        form = CategoryForm(request.POST, request.FILES, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category updated successfully!')
            return redirect('products:category_list')
    else:
        form = CategoryForm(instance=category)
    return render(request, 'products/admin/category_form.html', {'form': form, 'title': 'Edit Category', 'category': category})


@login_required
@user_passes_test(is_admin)
def category_delete(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    if request.method == 'POST':
        if category.image and os.path.isfile(category.image.path):
            os.remove(category.image.path)
        category_name = category.name
        category.delete()
        messages.success(request, f'Category "{category_name}" deleted successfully!')
        return redirect('products:category_list')
    return render(request, 'products/admin/category_delete.html', {'category': category})


@login_required
@user_passes_test(is_admin)
def subcategory_list(request):
    subcategories = Subcategory.objects.select_related('category')
    return render(request, 'products/admin/subcategory_list.html', {'subcategories': subcategories})


@login_required
@user_passes_test(is_admin)
def subcategory_create(request):
    if request.method == 'POST':
        form = SubcategoryForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Subcategory created successfully!')
            return redirect('products:subcategory_list')
    else:
        form = SubcategoryForm()
    return render(request, 'products/admin/subcategory_form.html', {'form': form, 'title': 'Create Subcategory'})


@login_required
@user_passes_test(is_admin)
def subcategory_edit(request, subcategory_id):
    subcategory = get_object_or_404(Subcategory, id=subcategory_id)
    if request.method == 'POST':
        form = SubcategoryForm(request.POST, request.FILES, instance=subcategory)
        if form.is_valid():
            form.save()
            messages.success(request, 'Subcategory updated successfully!')
            return redirect('products:subcategory_list')
    else:
        form = SubcategoryForm(instance=subcategory)
    return render(request, 'products/admin/subcategory_form.html', {'form': form, 'title': 'Edit Subcategory', 'subcategory': subcategory})


@login_required
@user_passes_test(is_admin)
def subcategory_delete(request, subcategory_id):
    subcategory = get_object_or_404(Subcategory, id=subcategory_id)
    if request.method == 'POST':
        if subcategory.image and os.path.isfile(subcategory.image.path):
            os.remove(subcategory.image.path)
        subcategory_name = subcategory.name
        subcategory.delete()
        messages.success(request, f'Subcategory "{subcategory_name}" deleted successfully!')
        return redirect('products:subcategory_list')
    return render(request, 'products/admin/subcategory_delete.html', {'subcategory': subcategory})


# ============ WHOLESELLER VIEWS ============

from django.core.paginator import Paginator
from django.db.models import Q, Sum
from accounts.models import  WholesellerAddress


@login_required
@user_passes_test(is_wholeseller)
def wholeseller_product_list(request):

    # 🔴 CHECK IF VALID ADDRESS EXISTS
    has_valid_address = WholesellerAddress.objects.filter(
        user=request.user,
        is_primary=True,
        is_active=True
    ).exists()

    # PRODUCTS QUERY
    products = (
        WholesellerProduct.objects
        .filter(wholeseller=request.user)
        .select_related('category', 'subcategory')
        .prefetch_related('variants', 'additional_images')
    )

    # SEARCH
    search = request.GET.get('q')
    if search:
        products = products.filter(
            Q(name__icontains=search) |
            Q(brand__icontains=search)
        )

    # PAGINATION
    paginator = Paginator(products, 12)
    page = request.GET.get('page')
    products_page = paginator.get_page(page)

    # STATS
    stats = {
        'total': products.count(),
        'active': products.filter(is_active=True).count(),
        'total_stock': products.aggregate(total=Sum('stock'))['total'] or 0,
    }

    return render(request, 'products/wholeseller/list.html', {
        'products': products_page,
        'stats': stats,
        'search': search,
        'has_valid_address': has_valid_address,  # ✅ key
    })
    
@login_required
@user_passes_test(is_wholeseller)
def wholeseller_product_create(request):

    if request.method == 'POST':
        form = WholesellerProductForm(request.POST, request.FILES)

        # ✅ DO NOT pass instance here
        image_formset = WholesellerProductImageFormSet(request.POST, request.FILES)

        if form.is_valid() and image_formset.is_valid():

            # ✅ STEP 1: Save product first
            product = form.save(commit=False)
            product.wholeseller = request.user
            product.save()

            # ✅ STEP 2: Attach product to formset
            image_formset.instance = product

            # ✅ STEP 3: Save images
            image_formset.save()

            messages.success(
                request,
                f'✅ Product "{product.name}" created successfully!'
            )

            return redirect('products:wholeseller_product_variants', product_id=product.id)

        else:
            print("FORM ERRORS:", form.errors)
            print("FORMSET ERRORS:", image_formset.errors)

    else:
        form = WholesellerProductForm()
        image_formset = WholesellerProductImageFormSet()

    return render(request, 'products/wholeseller/form_with_images.html', {
        'form': form,
        'image_formset': image_formset,
        'title': 'Add New Product',
    })


@login_required
@user_passes_test(is_wholeseller)
def wholeseller_product_edit(request, product_id):
    product = get_object_or_404(WholesellerProduct, id=product_id, wholeseller=request.user)
    
    if request.method == 'POST':
        form = WholesellerProductForm(request.POST, request.FILES, instance=product)
        image_formset = WholesellerProductImageFormSet(request.POST, request.FILES, instance=product)
        
        if form.is_valid() and image_formset.is_valid():
            form.save()
            image_formset.save()
            messages.success(request, f'✅ Product "{product.name}" updated successfully!')
            return redirect('products:wholeseller_product_list')
        else:
            for error in form.errors.values():
                messages.error(request, error)
    else:
        form = WholesellerProductForm(instance=product)
        image_formset = WholesellerProductImageFormSet(instance=product)
    
    return render(request, 'products/wholeseller/form_with_images.html', {
        'form': form,
        'image_formset': image_formset,
        'product': product,
        'title': 'Edit Product',
    })


@login_required
@user_passes_test(is_wholeseller)
def wholeseller_product_delete(request, product_id):
    product = get_object_or_404(WholesellerProduct, id=product_id, wholeseller=request.user)
    
    if request.method == 'POST':
        if product.main_image and os.path.isfile(product.main_image.path):
            os.remove(product.main_image.path)
        product_name = product.name
        product.delete()
        messages.success(request, f'Product "{product_name}" deleted successfully!')
        return redirect('products:wholeseller_product_list')
    
    return render(request, 'products/wholeseller/delete.html', {'product': product})


@login_required
@user_passes_test(is_wholeseller)
def wholeseller_product_variants(request, product_id):
    product = get_object_or_404(WholesellerProduct, id=product_id, wholeseller=request.user)
    variants = product.variants.all().prefetch_related('additional_images')
    
    return render(request, 'products/wholeseller/variants.html', {
        'product': product,
        'variants': variants,
    })


@login_required
@user_passes_test(is_wholeseller)
def wholeseller_variant_create(request, product_id):
    product = get_object_or_404(WholesellerProduct, id=product_id, wholeseller=request.user)
    
    if request.method == 'POST':
        form = WholesellerVariantForm(request.POST, request.FILES)

        # ✅ DO NOT pass instance
        image_formset = WholesellerVariantImageFormSet(request.POST, request.FILES)

        if form.is_valid() and image_formset.is_valid():
            variant = form.save(commit=False)
            variant.product = product
            variant.save()

            image_formset.instance = variant
            image_formset.save()

            return redirect('products:wholeseller_product_variants', product_id=product.id)

    else:
        form = WholesellerVariantForm()
        image_formset = WholesellerVariantImageFormSet()

    return render(request, 'products/wholeseller/variant_form_with_images.html', {
        'form': form,
        'image_formset': image_formset,
        'product': product,
        'title': 'Add Variant',
    })

@login_required
@user_passes_test(is_wholeseller)
def wholeseller_variant_edit(request, variant_id):

    variant = get_object_or_404(
        WholesellerProductVariant,
        id=variant_id,
        product__wholeseller=request.user
    )

    if request.method == 'POST':
        form = WholesellerVariantForm(
            request.POST,
            request.FILES,
            instance=variant
        )

        image_formset = WholesellerVariantImageFormSet(
            request.POST,
            request.FILES,
            instance=variant,
            prefix='images'   # 🔥 MUST MATCH TEMPLATE
        )

        if form.is_valid() and image_formset.is_valid():

            # ✅ save variant first
            form.save()

            # ✅ save images
            image_formset.save()

            messages.success(
                request,
                f'✅ Variant "{variant.variant_name}" updated successfully!'
            )

            return redirect(
                'products:wholeseller_product_variants',
                product_id=variant.product.id
            )

        else:
            print("FORM ERRORS:", form.errors)
            print("FORMSET ERRORS:", image_formset.errors)

    else:
        form = WholesellerVariantForm(instance=variant)

        image_formset = WholesellerVariantImageFormSet(
            instance=variant,
            prefix='images'   # 🔥 MUST MATCH TEMPLATE
        )

    return render(request, 'products/wholeseller/variant_form_with_images.html', {
        'form': form,
        'image_formset': image_formset,
        'product': variant.product,
        'variant': variant,
        'title': 'Edit Variant',
    })

@login_required
@user_passes_test(is_wholeseller)
def wholeseller_variant_delete(request, variant_id):
    variant = get_object_or_404(WholesellerProductVariant, id=variant_id, product__wholeseller=request.user)
    product_id = variant.product.id
    
    if request.method == 'POST':
        if variant.main_image and os.path.isfile(variant.main_image.path):
            os.remove(variant.main_image.path)
        variant_name = variant.variant_name
        variant.delete()
        messages.success(request, f'Variant "{variant_name}" deleted successfully!')
        return redirect('products:wholeseller_product_variants', product_id=product_id)
    
    return render(request, 'products/wholeseller/variant_delete.html', {'variant': variant})


@login_required
@user_passes_test(is_reseller)
def reseller_product_list(request, store_id):

    store = get_object_or_404(Store, id=store_id, reseller=request.user)

    # 🔥 OPTIMIZED QUERY
    products = (
        ResellerProduct.objects
        .filter(store=store)
        .select_related('category', 'subcategory')
        .prefetch_related(
            'additional_images',
            'variants',
            'variants__additional_images'
        )
    )

    # SEARCH
    search = request.GET.get('q')
    if search:
        products = products.filter(
            Q(name__icontains=search) |
            Q(brand__icontains=search)
        )

    # FILTER
    status_filter = request.GET.get('status')
    if status_filter == 'published':
        products = products.filter(is_published=True)
    elif status_filter == 'draft':
        products = products.filter(is_published=False)
    elif status_filter == 'pending_review':
        products = products.filter(
            price_status__in=['price_increased', 'price_decreased']
        )

    # LIMIT
    max_products = store.get_max_products()
    current_count = products.count()
    can_add_more = current_count < max_products

    # PAGINATION
    paginator = Paginator(products, 20)
    page = request.GET.get('page')
    products_page = paginator.get_page(page)

    # SUBSCRIPTION
    days_until_expiry = store.days_until_expiry()
    is_expiring_soon = store.is_expiring_soon(7)

    return render(request, 'products/reseller/list.html', {
        'products': products_page,
        'store': store,
        'max_products': max_products,
        'current_count': current_count,
        'can_add_more': can_add_more,
        'remaining_slots': max_products - current_count,
        'search': search,
        'status_filter': status_filter,
        'days_until_expiry': days_until_expiry,
        'is_expiring_soon': is_expiring_soon,
    })

@login_required
@user_passes_test(is_reseller)
def reseller_import_products(request, store_id):

    store = get_object_or_404(Store, id=store_id, reseller=request.user)

    current_count = ResellerProduct.objects.filter(store=store).count()
    max_products = store.get_max_products()

    if current_count >= max_products:
        messages.error(
            request,
            f'You have reached your product limit of {max_products}.'
        )
        return redirect('products:reseller_product_list', store_id=store.id)

    # ✅ CORRECT QUERY
    wholeseller_products = (
        WholesellerProduct.objects
        .filter(is_active=True)
        .select_related('category')
        .prefetch_related(
            'additional_images',                  # product images
            'variants',                           # variants
            'variants__additional_images'         # ✅ correct relation
        )
    )

    imported_ids = ResellerProduct.objects.filter(
        store=store,
        source_type='imported'
    ).values_list('source_product_id', flat=True)

    wholeseller_products = wholeseller_products.exclude(id__in=imported_ids)

    search = request.GET.get('q')
    if search:
        wholeseller_products = wholeseller_products.filter(
            Q(name__icontains=search) |
            Q(brand__icontains=search)
        )

    category_filter = request.GET.get('category')
    if category_filter:
        wholeseller_products = wholeseller_products.filter(category_id=category_filter)

    paginator = Paginator(wholeseller_products, 20)
    page = request.GET.get('page')
    products_page = paginator.get_page(page)

    return render(request, 'products/reseller/import_list.html', {
        'products': products_page,
        'store': store,
        'remaining_slots': max_products - current_count,
        'search': search,
        'categories': Category.objects.filter(is_active=True),
        'selected_category': category_filter,
    })

@login_required
@user_passes_test(is_reseller)
def reseller_import_product(request, store_id, product_id):

    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    source_product = get_object_or_404(WholesellerProduct, id=product_id, is_active=True)

    if request.method == 'POST':
        form = ResellerImportProductForm(request.POST, wholeseller_product=source_product)

        if form.is_valid():

            margin = form.cleaned_data.get('margin_rupees') or 0

            def calc(price):
                return float(price) + float(margin)

            # ================= PRODUCT CREATE =================
            product = ResellerProduct.objects.create(
                reseller=request.user,
                store=store,
                source_product=source_product,
                source_type='imported',

                category=source_product.category,
                subcategory=source_product.subcategory,

                name=source_product.name,
                description=source_product.description,
                specification=source_product.specification,

                brand=source_product.brand,
                model_name=source_product.model_name,
                size=source_product.size,
                color=source_product.color,
                material=source_product.material,
                gender=source_product.gender,
                attributes=source_product.attributes,

                stock=source_product.stock,
                threshold_limit=source_product.threshold_limit,

                source_price=source_product.price,
                last_known_source_price=source_product.price,

                margin_rupees=margin,
                selling_price=calc(source_product.price),

                # ✅ SHIPPING
                weight=source_product.weight,
                length=source_product.length,
                breadth=source_product.breadth,
                height=source_product.height,
                is_shippable=source_product.is_shippable,

                # ✅ RETURNS
                is_returnable=source_product.is_returnable,
                return_window_days=source_product.return_window_days,
                is_replaceable=source_product.is_replaceable,
                replacement_window_days=source_product.replacement_window_days,

                main_image=source_product.main_image,
                is_published=False,
            )

            # ================= PRODUCT IMAGES =================
            for img in source_product.additional_images.all():
                ResellerProductImage.objects.create(
                    product=product,
                    image=img.image,
                    alt_text=img.alt_text,
                    order=img.order
                )

            # ================= VARIANTS =================
            for sv in source_product.variants.all():

                variant = ResellerProductVariant.objects.create(
                    product=product,
                    source_variant=sv,

                    size=sv.size,
                    color=sv.color,
                    variant_name=sv.variant_name,

                    source_price=sv.price,
                    margin_rupees=margin,
                    selling_price=calc(sv.price),

                    stock=sv.stock,
                    threshold_limit=sv.threshold_limit,
                    order=sv.order,
                    is_active=sv.is_active,

                    # ✅ SHIPPING
                    weight=sv.weight,
                    length=sv.length,
                    breadth=sv.breadth,
                    height=sv.height,

                    # ✅ RETURNS
                    is_returnable=sv.is_returnable,
                    return_window_days=sv.return_window_days,
                    is_replaceable=sv.is_replaceable,
                    replacement_window_days=sv.replacement_window_days,
                )

                if sv.main_image:
                    variant.main_image = sv.main_image
                    variant.save()

                for simg in sv.additional_images.all():
                    ResellerVariantImage.objects.create(
                        variant=variant,
                        image=simg.image,
                        alt_text=simg.alt_text,
                        order=simg.order
                    )

            messages.success(request, f'✅ Imported "{product.name}" with margin ₹{margin}')
            return redirect('products:reseller_product_list', store_id=store.id)

    else:
        form = ResellerImportProductForm(wholeseller_product=source_product)

    return render(request, 'products/reseller/import_form.html', {
        'form': form,
        'source_product': source_product,
        'store': store,
    })

@login_required
@user_passes_test(is_reseller)
def reseller_product_toggle_publish(request, store_id, product_id):
    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    product = get_object_or_404(ResellerProduct, id=product_id, store=store)
    
    if product.is_published:
        product.is_published = False
        product.published_at = None
        message_text = f'📘 Product "{product.name}" has been unpublished and is now hidden from customers.'
    else:
        product.is_published = True
        product.published_at = timezone.now()
        message_text = f'🎉 Product "{product.name}" has been published and is now visible to customers!'
    
    product.save()
    product.refresh_from_db()
    
    messages.success(request, message_text)
    return redirect('products:reseller_product_list', store_id=store.id)


# products/views.py - Updated own product create

# @login_required
# @user_passes_test(is_reseller)
# def reseller_own_product_create(request, store_id):
#     """Create own products - these stay in master catalog and can be imported to stores"""
#     store = get_object_or_404(Store, id=store_id, reseller=request.user)
    
#     # Check limit for this store
#     current_count = ResellerProduct.objects.filter(store=store, is_active=True).count()
#     max_products = store.get_max_products()
    
#     if current_count >= max_products:
#         messages.error(request, f'Product limit reached. Maximum {max_products} products allowed.')
#         return redirect('products:reseller_product_list', store_id=store.id)
    
#     if request.method == 'POST':
#         form = ResellerOwnProductForm(request.POST, request.FILES)
#         image_formset = ResellerProductImageFormSet(request.POST, request.FILES, prefix='images')
        
#         if form.is_valid() and image_formset.is_valid():
#             product = form.save(commit=False)
#             product.reseller = request.user
#             product.store = store
#             product.source_type = 'own'  # Mark as own product
#             product.source_price = 0
#             product.margin_rupees = 0
#             product.is_published = False  # Start as draft
#             product.save()
            
#             image_formset.instance = product
#             image_formset.save()
            
#             messages.success(request, f'✅ Own product "{product.name}" created successfully!')
#             return redirect('products:reseller_product_list', store_id=store.id)
#     else:
#         form = ResellerOwnProductForm()
#         image_formset = ResellerProductImageFormSet(prefix='images')
    
#     return render(request, 'products/reseller/own_form_with_images.html', {
#         'form': form,
#         'image_formset': image_formset,
#         'store': store,
#         'remaining_slots': max_products - current_count,
#     })
    

@login_required
@user_passes_test(is_reseller)
def reseller_product_edit(request, store_id, product_id):

    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    product = get_object_or_404(ResellerProduct, id=product_id, store=store)

    # 🔴 IMPORTED PRODUCT (ONLY MARGIN EDIT)
    if product.source_type == 'imported':

        if request.method == 'POST':

            form = ResellerImportProductEditForm(request.POST)

            if form.is_valid():

                margin = form.cleaned_data['margin_rupees']

                # 🔥 UPDATE PRODUCT
                product.margin_rupees = margin
                product.selling_price = product.source_price + margin
                product.save()

                # 🔥 UPDATE VARIANTS
                for v in product.variants.all():
                    v.margin_rupees = margin
                    v.selling_price = v.source_price + margin
                    v.save()

                messages.success(request, "✅ Margin updated successfully!")
                return redirect('products:reseller_product_list', store_id=store.id)

        else:
            form = ResellerImportProductEditForm(instance=product)

        return render(request, 'products/reseller/edit_form_with_images.html', {
            'form': form,
            'product': product,
            'store': store,
            'is_imported': True,
        })

    # 🟢 OWN PRODUCT (FULL EDIT)
    if request.method == 'POST':
        form = ResellerOwnProductForm(request.POST, request.FILES, instance=product)
        image_formset = ResellerProductImageFormSet(
            request.POST, request.FILES, instance=product
        )

        if form.is_valid() and image_formset.is_valid():
            form.save()
            image_formset.save()

            messages.success(request, f'✅ Product "{product.name}" updated!')
            return redirect('products:reseller_product_list', store_id=store.id)

    else:
        form = ResellerOwnProductForm(instance=product)
        image_formset = ResellerProductImageFormSet(instance=product)

    return render(request, 'products/reseller/edit_form_with_images.html', {
        'form': form,
        'image_formset': image_formset,
        'product': product,
        'store': store,
        'is_imported': False,
    })
    
@login_required
@user_passes_test(is_reseller)
def reseller_product_delete(request, store_id, product_id):
    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    product = get_object_or_404(ResellerProduct, id=product_id, store=store)
    
    if request.method == 'POST':
        if product.main_image and os.path.isfile(product.main_image.path):
            os.remove(product.main_image.path)
        product_name = product.name
        product.delete()
        messages.success(request, f'Product "{product_name}" deleted successfully!')
        return redirect('products:reseller_product_list', store_id=store.id)
    
    return render(request, 'products/reseller/delete.html', {
        'product': product,
        'store': store,
    })


# @login_required
# @user_passes_test(is_reseller)
# def reseller_add_variant(request, store_id, product_id):
#     store = get_object_or_404(Store, id=store_id, reseller=request.user)
#     product = get_object_or_404(ResellerProduct, id=product_id, store=store)
    
#     if request.method == 'POST':
#         form = ResellerVariantForm(request.POST, request.FILES)
#         image_formset = ResellerVariantImageFormSet(request.POST, request.FILES, instance=ResellerProductVariant())
        
#         if form.is_valid() and image_formset.is_valid():
#             variant = form.save(commit=False)
#             variant.product = product
#             if product.source_type == 'imported':
#                 variant.margin_rupees = product.margin_rupees
#             variant.save()
#             image_formset.instance = variant
#             image_formset.save()
#             messages.success(request, f'Variant "{variant.variant_name}" added successfully!')
#             return redirect('products:reseller_product_list', store_id=store.id)
#     else:
#         form = ResellerVariantForm(initial={'margin_rupees': product.margin_rupees})
#         image_formset = ResellerVariantImageFormSet()
    
#     return render(request, 'products/reseller/variant_form_with_images.html', {
#         'form': form,
#         'image_formset': image_formset,
#         'product': product,
#         'store': store,
#     })


# @login_required
# @user_passes_test(is_reseller)
# def reseller_edit_variant(request, store_id, variant_id):
#     store = get_object_or_404(Store, id=store_id, reseller=request.user)
#     variant = get_object_or_404(ResellerProductVariant, id=variant_id, product__store=store)
    
#     if request.method == 'POST':
#         form = ResellerVariantForm(request.POST, request.FILES, instance=variant)
#         image_formset = ResellerVariantImageFormSet(request.POST, request.FILES, instance=variant)
        
#         if form.is_valid() and image_formset.is_valid():
#             form.save()
#             image_formset.save()
#             messages.success(request, f'Variant "{variant.variant_name}" updated successfully!')
#             return redirect('products:reseller_product_list', store_id=store.id)
#     else:
#         form = ResellerVariantForm(instance=variant)
#         image_formset = ResellerVariantImageFormSet(instance=variant)
    
#     return render(request, 'products/reseller/variant_form_with_images.html', {
#         'form': form,
#         'image_formset': image_formset,
#         'variant': variant,
#         'product': variant.product,
#         'store': store,
#     })


# @login_required
# @user_passes_test(is_reseller)
# def reseller_delete_variant(request, store_id, variant_id):
#     store = get_object_or_404(Store, id=store_id, reseller=request.user)
#     variant = get_object_or_404(ResellerProductVariant, id=variant_id, product__store=store)
    
#     if request.method == 'POST':
#         if variant.main_image and os.path.isfile(variant.main_image.path):
#             os.remove(variant.main_image.path)
#         variant_name = variant.variant_name
#         variant.delete()
#         messages.success(request, f'Variant "{variant_name}" deleted successfully!')
#         return redirect('products:reseller_product_list', store_id=store.id)
    
#     return render(request, 'products/reseller/variant_delete.html', {
#         'variant': variant,
#         'store': store,
#     })


# ============ PRICE CHANGE NOTIFICATION VIEWS ============

@login_required
@user_passes_test(is_reseller)
def price_change_notifications(request, store_id):

    store = get_object_or_404(Store, id=store_id, reseller=request.user)

    notifications = PriceChangeNotification.objects.filter(
        store=store,
        reseller=request.user
    ).select_related('reseller_product', 'reseller_variant')

    notifications.filter(is_read=False).update(is_read=True)

    products_with_changes = ResellerProduct.objects.filter(
        store=store,
        price_status__in=['price_increased', 'price_decreased']
    )

    return render(request, 'products/reseller/price_notifications.html', {
        'store': store,
        'notifications': notifications,
        'products_with_changes': products_with_changes,
    })

@login_required
@user_passes_test(is_reseller)
def review_price_change(request, store_id, product_id):

    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    product = get_object_or_404(ResellerProduct, id=product_id, store=store)

    notification = PriceChangeNotification.objects.filter(
        reseller=request.user,
        store=store,
        reseller_product=product
    ).order_by('-created_at').first()

    if not notification:
        messages.error(request, "No price change found")
        return redirect('products:reseller_product_list', store_id=store.id)

    variant = notification.reseller_variant

    old_base = notification.old_price
    new_base = notification.new_price

    old_selling = notification.old_selling_price
    new_selling = notification.new_selling_price

    diff = notification.get_difference()

    if request.method == 'POST':
        action = request.POST.get('action')

        if variant:
            if action == 'update':
                variant.source_price = new_base
                variant.selling_price = new_selling
                variant.save()

        else:
            if action == 'update':
                product.source_price = new_base
                product.selling_price = new_selling
                product.price_status = 'reviewed'
                product.save()

            elif action == 'ignore':
                product.price_status = 'reviewed'
                product.save()

            elif action == 'custom_margin':
                margin = float(request.POST.get('new_margin'))
                product.margin_rupees = margin
                product.selling_price = new_base + margin
                product.save()

        notification.is_actioned = True
        notification.save()

        return redirect('products:price_notifications', store_id=store.id)

    return render(request, 'products/reseller/review_price_change.html', {
        'store': store,
        'product': product,
        'variant': variant,
        'notification': notification,
        'old_base_price': old_base,
        'new_base_price': new_base,
        'old_selling_price': old_selling,
        'new_selling_price': new_selling,
        'price_difference': diff,
        'is_increase': diff > 0,
    })

@login_required
@user_passes_test(is_reseller)
def dismiss_price_notification(request, notification_id):
    notification = get_object_or_404(
        PriceChangeNotification,
        id=notification_id,
        reseller=request.user
    )

    # ✅ enforce review first
    if not notification.is_actioned:
        messages.error(request, "You must review before dismissing.")
        return redirect('products:price_notifications', store_id=notification.store.id)

    store_id = notification.store.id

    notification.delete()

    messages.success(request, "Notification dismissed.")

    # ✅ CORRECT REDIRECT
    return redirect('products:price_notifications', store_id=store_id)

@login_required
@user_passes_test(is_reseller)
def get_notification_count(request):
    count = PriceChangeNotification.objects.filter(
        reseller=request.user,
        is_read=False
    ).count()

    return JsonResponse({'count': count})
# ============ AJAX ENDPOINTS ============


def load_subcategories(request):
    category_id = request.GET.get('category_id')
    qs = Subcategory.objects.filter(category_id=category_id, is_active=True).order_by('name')
    return JsonResponse(list(qs.values('id', 'name')), safe=False)

from django.http import JsonResponse

@login_required
@user_passes_test(is_reseller)
def calculate_price(request):

    margin = float(request.GET.get('margin_rupees', 0))
    source_price = float(request.GET.get('source_price', 0))

    variant_prices = request.GET.getlist('variant_prices[]')

    product_price = source_price + margin

    updated_variants = [
        round(float(p) + margin, 2) for p in variant_prices
    ]

    return JsonResponse({
        'product_price': round(product_price, 2),
        'variant_prices': updated_variants
    })

@login_required
@user_passes_test(is_wholeseller)
def wholeseller_product_detail(request, product_id):

    product = get_object_or_404(
        WholesellerProduct.objects.prefetch_related('variants', 'additional_images'),
        id=product_id,
        wholeseller=request.user
    )

    return render(request, 'products/product_detail.html', {
        'product': product,
        'store': None  # optional (prevents sidebar crash if expecting store)
    })


@login_required
@user_passes_test(is_reseller)
def reseller_product_detail(request, store_id, product_id):

    store = get_object_or_404(Store, id=store_id, reseller=request.user)

    product = get_object_or_404(
        ResellerProduct.objects.prefetch_related('variants', 'additional_images'),
        id=product_id,
        store=store
    )

    return render(request, 'products/product_detail.html', {
        'product': product,
        'store': store   # ✅ required for sidebar url
    })


from django.db import transaction

@login_required
@user_passes_test(is_reseller)
@transaction.atomic
def reseller_product_full_create(request, store_id):

    store = get_object_or_404(Store, id=store_id, reseller=request.user)

    # PRIMARY ADDRESS CHECK
    if not ResellerAddress.objects.filter(user=request.user, is_primary=True).exists():
        messages.error(request, "⚠️ Please add a primary address before creating a product.")
        return redirect('accounts:reseller_addresses')

    # PRODUCT LIMIT CHECK
    current_count = ResellerProduct.objects.filter(
        store=store,
        is_active=True
    ).count()

    if current_count >= store.get_max_products():
        messages.error(request, f'Product limit reached.')
        return redirect('products:reseller_product_list', store_id=store.id)

    if request.method == 'POST':

        product_form = ResellerOwnProductForm(request.POST, request.FILES)
        image_formset = ResellerProductImageFormSet(request.POST, request.FILES, prefix='images')
        variant_formset = ResellerVariantFormSet(request.POST, request.FILES, prefix='variants')

        if product_form.is_valid() and image_formset.is_valid() and variant_formset.is_valid():

            # PRODUCT VALIDATION
            if product_form.cleaned_data.get('weight', 0) <= 0:
                messages.error(request, "⚠️ Product weight is required.")
                return redirect(request.path)

            product = product_form.save(commit=False)
            product.reseller = request.user
            product.store = store
            product.source_type = 'own'
            product.save()

            # PRODUCT IMAGES
            image_formset.instance = product
            image_formset.save()

            # VARIANTS
            variants = variant_formset.save(commit=False)

            for i, variant in enumerate(variants):

                if variant.weight <= 0:
                    messages.error(request, f"⚠️ Variant {i+1} weight is required.")
                    raise Exception("Invalid variant weight")

                variant.product = product
                variant.save()

                images = request.FILES.getlist(f'variant_images_{i}')
                for img in images:
                    ResellerVariantImage.objects.create(
                        variant=variant,
                        image=img
                    )

            variant_formset.save_m2m()

            messages.success(request, "✅ Product created successfully!")
            return redirect('products:reseller_product_list', store_id=store.id)

        else:
            messages.error(request, "❌ Please fix the errors in the form.")

    else:
        product_form = ResellerOwnProductForm()
        image_formset = ResellerProductImageFormSet(prefix='images')
        variant_formset = ResellerVariantFormSet(prefix='variants')

    return render(request, 'products/reseller/full_create.html', {
        'product_form': product_form,
        'image_formset': image_formset,
        'variant_formset': variant_formset,
        'store': store,
    })

@login_required
@user_passes_test(is_reseller)
@transaction.atomic
def reseller_product_full_edit(request, store_id, product_id):

    store = get_object_or_404(Store, id=store_id, reseller=request.user)
    product = get_object_or_404(ResellerProduct, id=product_id, store=store)

    if request.method == 'POST':

        product_form = ResellerOwnProductForm(request.POST, request.FILES, instance=product)

        image_formset = ResellerProductImageFormSet(
            request.POST,
            request.FILES,
            instance=product,
            prefix='images'
        )

        variant_formset = ResellerVariantFormSet(
            request.POST,
            request.FILES,
            instance=product,
            prefix='variants'
        )

        if product_form.is_valid() and image_formset.is_valid() and variant_formset.is_valid():

            # PRODUCT VALIDATION
            if product_form.cleaned_data.get('weight', 0) <= 0:
                messages.error(request, "⚠️ Product weight is required.")
                return redirect(request.path)

            product = product_form.save()

            # PRODUCT IMAGES
            image_formset.save()

            # DELETE VARIANT IMAGES
            for img in ResellerVariantImage.objects.filter(variant__product=product):
                if request.POST.get(f'delete_variant_image_{img.id}'):
                    img.delete()

            variants = variant_formset.save(commit=False)

            # DELETE REMOVED VARIANTS
            for obj in variant_formset.deleted_objects:
                obj.delete()

            for i, form in enumerate(variant_formset.forms):

                if form.cleaned_data.get('DELETE'):
                    continue

                variant = form.save(commit=False)

                if variant.weight <= 0:
                    messages.error(request, f"⚠️ Variant {i+1} weight is required.")
                    raise Exception("Invalid variant weight")

                variant.product = product
                variant.save()

                images = request.FILES.getlist(f'variant_images_{i}')
                for img in images:
                    ResellerVariantImage.objects.create(
                        variant=variant,
                        image=img
                    )

            variant_formset.save_m2m()

            messages.success(request, "✅ Product updated successfully!")
            return redirect('products:reseller_product_list', store_id=store.id)

        else:
            messages.error(request, "❌ Please fix the errors in the form.")

    else:
        product_form = ResellerOwnProductForm(instance=product)

        image_formset = ResellerProductImageFormSet(
            instance=product,
            prefix='images'
        )

        variant_formset = ResellerVariantFormSet(
            instance=product,
            prefix='variants'
        )

    return render(request, 'products/reseller/full_edit.html', {
        'product_form': product_form,
        'image_formset': image_formset,
        'variant_formset': variant_formset,
        'product': product,
        'store': store,
    })

from django.db.models import F, Q, Prefetch

from products.models import (
    WholesellerProduct, WholesellerProductVariant,
    ResellerProduct, ResellerProductVariant
)


@login_required
def low_stock_alerts(request):
    user = request.user
    context = {}

    # =========================
    # WHOLESELLER
    # =========================
    if user.role == 'wholeseller':

        low_products = WholesellerProduct.objects.filter(
            wholeseller=user,
            stock__lte=F('threshold_limit'),
            is_active=True
        )

        low_variants = WholesellerProductVariant.objects.filter(
            product__wholeseller=user,
            stock__lte=F('threshold_limit'),
            is_active=True
        ).select_related('product')

        context.update({
            'low_products': low_products,
            'low_variants': low_variants,
            'role': 'wholeseller'
        })

    # =========================
    # RESELLER
    # =========================
    elif user.role == 'reseller':

        # ✅ FIX: ensure store always exists
        store = getattr(request, 'current_store', None)

        if not store:
            store = Store.objects.filter(reseller=user).first()

        if not store:
            messages.error(request, "⚠️ No store found. Please create a store first.")
            return redirect('resellers:reseller_dashboard')

        # OWN PRODUCTS
        own_products = ResellerProduct.objects.filter(
            reseller=user,
            source_type='own',
            stock__lte=F('threshold_limit'),
            is_active=True
        )

        own_variants = ResellerProductVariant.objects.filter(
            product__reseller=user,
            product__source_type='own',
            stock__lte=F('threshold_limit'),
            is_active=True
        ).select_related('product')

        # IMPORTED PRODUCTS
        imported_products = ResellerProduct.objects.filter(
            reseller=user,
            source_type='imported',
            source_product__stock__lte=F('source_product__threshold_limit'),
            is_active=True
        ).select_related('source_product')

        # IMPORTED VARIANTS
        imported_variants = ResellerProductVariant.objects.filter(
            product__reseller=user,
            product__source_type='imported',
            source_variant__stock__lte=F('source_variant__threshold_limit'),
            is_active=True
        ).select_related('product', 'source_variant')

        context.update({
            'store': store,  # ✅ THIS FIXES YOUR ERROR
            'own_products': own_products,
            'own_variants': own_variants,
            'imported_products': imported_products,
            'imported_variants': imported_variants,
            'role': 'reseller'
        })

    return render(request, 'resellers/low_stock_alerts.html', context)