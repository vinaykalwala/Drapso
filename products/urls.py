from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    # ============ CATEGORY MANAGEMENT (Admin Only) ============
    path('admin/categories/', views.category_list, name='category_list'),
    path('admin/categories/create/', views.category_create, name='category_create'),
    path('admin/categories/<int:category_id>/edit/', views.category_edit, name='category_edit'),
    path('admin/categories/<int:category_id>/delete/', views.category_delete, name='category_delete'),
    
    path('admin/subcategories/', views.subcategory_list, name='subcategory_list'),
    path('admin/subcategories/create/', views.subcategory_create, name='subcategory_create'),
    path('admin/subcategories/<int:subcategory_id>/edit/', views.subcategory_edit, name='subcategory_edit'),
    path('admin/subcategories/<int:subcategory_id>/delete/', views.subcategory_delete, name='subcategory_delete'),
    
    # ============ WHOLESELLER PRODUCTS ============
    # Product CRUD
    path('wholeseller/products/', views.wholeseller_product_list, name='wholeseller_product_list'),
    path('wholeseller/products/create/', views.wholeseller_product_create, name='wholeseller_product_create'),
    path('wholeseller/products/<int:product_id>/edit/', views.wholeseller_product_edit, name='wholeseller_product_edit'),
    path('wholeseller/products/<int:product_id>/delete/', views.wholeseller_product_delete, name='wholeseller_product_delete'),
    path('wholeseller/products/<int:product_id>/variants/', views.wholeseller_product_variants, name='wholeseller_product_variants'),
    
    # Wholeseller Variants
    path('wholeseller/products/<int:product_id>/variants/create/', views.wholeseller_variant_create, name='wholeseller_variant_create'),
    path('wholeseller/variants/<int:variant_id>/edit/', views.wholeseller_variant_edit, name='wholeseller_variant_edit'),
    path('wholeseller/variants/<int:variant_id>/delete/', views.wholeseller_variant_delete, name='wholeseller_variant_delete'),
    
    # ============ RESELLER PRODUCTS ============
    # Product Management
    path('reseller/store/<int:store_id>/products/', views.reseller_product_list, name='reseller_product_list'),
    
    # Import Products from Wholeseller
    path('reseller/store/<int:store_id>/import/', views.reseller_import_products, name='reseller_import_products'),
    path('reseller/store/<int:store_id>/import/<int:product_id>/', views.reseller_import_product, name='reseller_import_product'),
    
    # Own Products
    # path('reseller/store/<int:store_id>/create-own/', views.reseller_own_product_create, name='reseller_own_product_create'),
    path(
    'reseller/store/<int:store_id>/create-full/',
    views.reseller_product_full_create,
    name='reseller_product_full_create'
),

path(
    'reseller/store/<int:store_id>/product/<int:product_id>/edit-full/',
    views.reseller_product_full_edit,
    name='reseller_product_full_edit'
),
    # Product Edit/Delete/Publish
    path('reseller/store/<int:store_id>/product/<int:product_id>/edit/', views.reseller_product_edit, name='reseller_product_edit'),
    path('reseller/store/<int:store_id>/product/<int:product_id>/toggle-publish/', views.reseller_product_toggle_publish, name='reseller_product_toggle_publish'),
    path('reseller/store/<int:store_id>/product/<int:product_id>/delete/', views.reseller_product_delete, name='reseller_product_delete'),
    
    # # Reseller Variants
    # path('reseller/store/<int:store_id>/product/<int:product_id>/add-variant/', views.reseller_add_variant, name='reseller_add_variant'),
    # path('reseller/store/<int:store_id>/variant/<int:variant_id>/edit/', views.reseller_edit_variant, name='reseller_edit_variant'),
    # path('reseller/store/<int:store_id>/variant/<int:variant_id>/delete/', views.reseller_delete_variant, name='reseller_delete_variant'),
    
    # ============ PRICE CHANGE NOTIFICATIONS ============
    path('reseller/store/<int:store_id>/price-notifications/', views.price_change_notifications, name='price_notifications'),
    path('reseller/store/<int:store_id>/product/<int:product_id>/review-price/', views.review_price_change, name='review_price_change'),
    path('reseller/notification/<int:notification_id>/dismiss/', views.dismiss_price_notification, name='dismiss_notification'),
    path('reseller/notification/count/', views.get_notification_count, name='notification_count'),
    # products/urls.py

    # wholeseller
    path('wholeseller/product/<int:product_id>/', views.wholeseller_product_detail, name='wholeseller_product_detail'),

    # reseller
    path('reseller/store/<int:store_id>/product/<int:product_id>/', views.reseller_product_detail, name='reseller_product_detail'),
        # ============ AJAX ENDPOINTS ============
    path('ajax/load-subcategories/', views.load_subcategories, name='load_subcategories'),
    path('ajax/calculate-price/', views.calculate_price, name='calculate_price'),
]