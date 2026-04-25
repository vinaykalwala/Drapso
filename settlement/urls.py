from django.urls import path
from . import views

app_name = 'settlement'

urlpatterns = [
    # Seller URLs
    path('dashboard/', views.dashboard, name='dashboard'),
    path('withdrawal/request/', views.withdrawal_request, name='withdrawal_request'),
    path('withdrawal/history/', views.withdrawal_history, name='withdrawal_history'),
    path('transactions/', views.transaction_history, name='transaction_history'),
    path('admin/earnings/', views.admin_platform_earnings, name='admin_platform_earnings'),
    
    # Admin URLs
    path('admin/withdrawals/', views.admin_withdrawal_requests, name='admin_withdrawal_requests'),
    path('admin/withdrawal/<uuid:withdrawal_id>/', views.admin_withdrawal_detail, name='admin_withdrawal_detail'),
    path('admin/settlement-report/', views.admin_settlement_report, name='admin_settlement_report'),
    
    # API URLs
    path('api/balance/', views.api_wallet_balance, name='api_balance'),
    path('api/bank-accounts/', views.api_bank_accounts, name='api_bank_accounts'),
]