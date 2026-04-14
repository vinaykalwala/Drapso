# resellers/urls.py

from django.urls import path, re_path
from . import views

app_name = 'resellers'

urlpatterns = [
    # Dashboard
    path('reseller_dashboard/', views.reseller_dashboard, name='reseller_dashboard'),
    
    # Store Creation Flow
    path('create-store/', views.create_store_step1, name='create_store_step1'),
    path('select-plan/', views.select_plan, name='select_plan'),
    path('select-theme/', views.select_theme, name='select_theme'),
    path('create-order/<int:store_id>/', views.create_order, name='create_order'), 
    path('payment-success/', views.payment_success, name='payment_success'),
    path('payment-failed/', views.payment_failed, name='payment_failed'),
    path('preview/single-theme/<int:theme_id>/', views.preview_single_theme, name='preview_single_theme'),
    path('preview/multiple-theme/<int:theme_id>/', views.preview_multiple_theme, name='preview_multiple_theme'),
    # Store Management
    path('store/<int:store_id>/', views.store_dashboard, name='store_dashboard'),
    path('store/<int:store_id>/preview/', views.preview_store, name='preview_store'),
    path('store/<int:store_id>/copy-link/', views.copy_store_link, name='copy_store_link'),
   

    path('store/<int:store_id>/edit/', views.edit_store, name='edit_store'),    
    
    # Admin Plan CRUD
    path('admin/plans/', views.plan_list, name='plan_list'),
    path('admin/plans/create/', views.plan_create, name='plan_create'),
    path('admin/plans/<int:plan_id>/edit/', views.plan_edit, name='plan_edit'),
    path('admin/plans/<int:plan_id>/delete/', views.plan_delete, name='plan_delete'),
    
    # Admin Theme CRUD
    path('admin/themes/', views.theme_list, name='theme_list'),
    path('admin/themes/create/', views.theme_create, name='theme_create'),
    path('admin/themes/<int:theme_id>/edit/', views.theme_edit, name='theme_edit'),
    path('admin/themes/<int:theme_id>/delete/', views.theme_delete, name='theme_delete'),
    
    # Admin Store Management
    path('admin/stores/', views.admin_stores, name='admin_stores'),
    path('admin/store/<int:store_id>/', views.admin_store_detail, name='admin_store_detail'),
    
    path('', views.store_frontend, name='store_frontend'),
    path('product/<slug:product_slug>/', views.store_product_detail, name='store_product_detail'),
    
    path('manage-subscription/<int:store_id>/', views.manage_subscription, name='manage_subscription'),
    path('renew-subscription/<int:store_id>/', views.process_renewal, name='renew_subscription'),
    path('renew-subscription/<int:store_id>/<int:plan_id>/', views.process_renewal, name='renew_subscription_with_plan'),
    path('subscribe-new-plan/<int:store_id>/<int:plan_id>/', views.subscribe_new_plan, name='subscribe_new_plan'),
    path('renewal-payment-callback/', views.renewal_payment_callback, name='renewal_payment_callback'),
    path('new-subscription-callback/', views.new_subscription_callback, name='new_subscription_callback'),
]