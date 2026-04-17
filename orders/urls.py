# orders/urls.py
from django.urls import path
from . import views
from . import webhook_views
from .views import *

app_name = 'orders'

urlpatterns = [
    # Checkout & Payment
    path('store/<int:store_id>/product/<int:product_id>/checkout/', views.create_order, name='create_order'),
    path('pay-securely/<str:razorpay_order_id>/', central_payment, name='central_payment'),
    path('pay-securely/<str:razorpay_order_id>/<str:encoded_data>/', central_payment, name='central_payment_with_data'),  path('payment/success/', views.payment_success, name='payment_success'),
    path('payment/failed/', views.payment_failed, name='payment_failed'),
    path('success/<str:order_id>/', views.order_success, name='order_success'),
    path('track/<str:order_id>/', views.track_order, name='track_order'),
    
    # Shipping Calculation AJAX
    path('calculate-shipping/', views.calculate_shipping, name='calculate_shipping'),
    
    # Reseller Orders
    path('reseller/store/<int:store_id>/orders/', views.reseller_orders, name='reseller_orders'),
    path('reseller/store/<int:store_id>/order/<int:order_id>/', views.reseller_order_detail, name='reseller_order_detail'),
    path('reseller/store/<int:store_id>/order/<int:order_id>/approve/', views.approve_order, name='approve_order'),
    path('reseller/store/<int:store_id>/order/<int:order_id>/ship/', views.mark_order_shipped, name='mark_order_shipped'),
    
    # Return Management
    path('return/<str:order_id>/request/', views.request_return, name='request_return'),
    path('reseller/store/<int:store_id>/return/<int:return_id>/review/', views.review_return_request, name='review_return'),
    
    # Admin Refund Management
    path('admin/refunds/', views.admin_refund_requests, name='admin_refund_requests'),
    path('admin/refund/<int:refund_id>/process/', views.process_refund, name='process_refund'),
    path('admin/order/<str:order_id>/manual-refund/', views.create_manual_refund, name='create_manual_refund'),
    
    # Cancellation
    path('cancel/<str:order_id>/', views.cancel_order, name='cancel_order'),
    
    # Wholeseller Orders
    path('wholeseller/orders/', views.wholeseller_orders, name='wholeseller_orders'),
    
    # Webhooks
    path('webhook/shiprocket/', webhook_views.shiprocket_webhook, name='shiprocket_webhook'),
    path('webhook/health/', webhook_views.webhook_health, name='webhook_health'),
    path('admin/sync-order/<str:order_id>/', webhook_views.sync_order_status, name='sync_order_status'),
]