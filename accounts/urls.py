from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'accounts'

urlpatterns = [
    # Template-based signup URLs (for Wholeseller, Reseller, Admin)
    path('signup/wholeseller/', views.wholeseller_signup, name='wholeseller_signup'),
    path('signup/reseller/', views.reseller_signup, name='reseller_signup'),
    path('signup/admin/', views.admin_signup, name='admin_signup'),
    
    # Authentication URLs
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    path('resend-otp/', views.resend_otp, name='resend_otp'),
    
    # Password management URLs
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('reset-password/', views.reset_password, name='reset_password'),
    path('change-password/', views.change_password, name='change_password'),
    path('change-password/verify-otp/', views.verify_change_password_otp, name='verify_change_password_otp'),
    
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Profile URLs
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),


    path('bank-accounts/', views.bank_accounts, name='bank_accounts'),
    path('bank-accounts/add/', views.add_bank_account, name='add_bank_account'),
    path('bank-accounts/verify/<int:account_id>/', views.verify_bank_account_otp, name='verify_bank_account_otp'),
    path('bank-accounts/resend-otp/<int:account_id>/', views.resend_bank_otp, name='resend_bank_otp'),
    path('bank-accounts/edit/<int:account_id>/', views.edit_bank_account, name='edit_bank_account'),
    path('bank-accounts/set-primary/<int:account_id>/', views.set_primary_bank_account, name='set_primary_bank_account'),
    path('bank-accounts/delete/<int:account_id>/', views.delete_bank_account, name='delete_bank_account'),
    
    # Wholeseller Address URLs
    path('wholeseller/addresses/', views.wholeseller_addresses, name='wholeseller_addresses'),
    path('wholeseller/addresses/add/', views.add_wholeseller_address, name='add_wholeseller_address'),
    path('wholeseller/addresses/edit/<int:address_id>/', views.edit_wholeseller_address, name='edit_wholeseller_address'),
    path('wholeseller/addresses/set-primary/<int:address_id>/', views.set_primary_wholeseller_address, name='set_primary_wholeseller_address'),
    path('wholeseller/addresses/delete/<int:address_id>/', views.delete_wholeseller_address, name='delete_wholeseller_address'),
    
    # Reseller Address URLs
    path('reseller/addresses/', views.reseller_addresses, name='reseller_addresses'),
    path('reseller/addresses/add/', views.add_reseller_address, name='add_reseller_address'),
    path('reseller/addresses/edit/<int:address_id>/', views.edit_reseller_address, name='edit_reseller_address'),
    path('reseller/addresses/set-primary/<int:address_id>/', views.set_primary_reseller_address, name='set_primary_reseller_address'),
    path('reseller/addresses/delete/<int:address_id>/', views.delete_reseller_address, name='delete_reseller_address'),
   
]