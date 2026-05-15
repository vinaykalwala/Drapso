# settlement/urls.py

from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from . import views

app_name = 'settlement'

urlpatterns = [
    # Seller URLs
    path('dashboard/', views.dashboard, name='dashboard'),
    path('withdrawal/request/', views.withdrawal_request, name='withdrawal_request'),
    path('withdrawal/history/', views.withdrawal_history, name='withdrawal_history'),
    path('transactions/', views.transaction_history, name='transaction_history'),
    
    # Admin URLs - Withdrawal Management
    path('admin/withdrawals/', views.admin_withdrawal_requests, name='admin_withdrawal_requests'),
    path('admin/withdrawal/<uuid:withdrawal_id>/', views.admin_withdrawal_detail, name='admin_withdrawal_detail'),
    
    # Manual Payout URLs
    path('admin/withdrawal/<uuid:withdrawal_id>/record-payout/', 
         views.admin_record_manual_payout, 
         name='admin_record_manual_payout'),
    
    path('admin/withdrawal/<uuid:withdrawal_id>/cancel/', 
         views.admin_cancel_approved_withdrawal, 
         name='admin_cancel_withdrawal'),
    
    # Company Bank Accounts Management
    path('admin/payout-bank-accounts/', 
         views.admin_payout_bank_accounts, 
         name='admin_payout_bank_accounts'),
    
    path('admin/payout-bank-accounts/<uuid:account_id>/delete/', 
         views.admin_payout_bank_account_delete, 
         name='admin_payout_bank_account_delete'),
    
    # Reports
    path('admin/settlement-report/', views.admin_settlement_report, name='admin_settlement_report'),
    path('admin/earnings/', views.admin_platform_earnings, name='admin_platform_earnings'),
    path('admin/manual-payouts-report/', views.admin_manual_payouts_report, name='admin_manual_payouts_report'),
    path('my-payouts/', views.my_payouts, name='my_payouts'),
    # API URLs
    path('api/balance/', views.api_wallet_balance, name='api_balance'),
    path('api/bank-accounts/', views.api_bank_accounts, name='api_bank_accounts'),
]
