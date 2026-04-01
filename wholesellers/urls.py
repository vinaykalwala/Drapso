# wholesellers/urls.py

from django.urls import path
from . import views

app_name = 'wholesellers'

urlpatterns = [
    # Wholeseller URLs
    path('create-inventory/', views.create_inventory, name='create_inventory'),
    path('submit-kyc/', views.submit_kyc, name='submit_kyc'),
    path('kycdashboard/', views.wholeseller_dashboard, name='wholeseller_dashboard'),
    path('edit-inventory/', views.edit_inventory, name='edit_inventory'),
    
    # Admin URLs for wholeseller verification
    path('pending-kyc/', views.admin_pending_kyc, name='admin_pending_kyc'),
    path('review-kyc/<int:kyc_id>/', views.admin_review_kyc, name='admin_review_kyc'),
    path('verified-wholesellers/', views.admin_verified_wholesellers, name='admin_verified_wholesellers'),
]