# analytics/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Dashboard views
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('wholeseller-dashboard/', views.wholeseller_dashboard, name='wholeseller_dashboard'),
    path('reseller-dashboard/', views.reseller_dashboard, name='reseller_dashboard'),
    
    # Original dashboard (redirects based on role)
    path('dashboard/', views.dashboard_redirect, name='analytics_dashboard'),
    
    # API endpoints
    path('dashboard-summary/', views.dashboard_summary, name='dashboard_summary'),
    path('revenue/', views.revenue_stats, name='revenue_stats'),
    path('user-growth/', views.user_growth, name='user_growth'),
    path('top-products/', views.top_products, name='top_products'),
    path('settlements/', views.settlement_analytics, name='settlement_analytics'),
    path('product-performance/', views.product_performance, name='product_performance'),
    path('store-performance/', views.store_performance, name='store_performance'),
    path('profit/', views.profit_analytics, name='profit_analytics'),  # Add this line
    path('available-periods/', views.available_periods, name='available_periods'),
    path('export/', views.export_analytics, name='export_analytics'),
]