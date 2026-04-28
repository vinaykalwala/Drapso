# analytics/views.py
from django.shortcuts import render,redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.core.cache import cache
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from datetime import datetime, timedelta
import csv
import json
import logging
from django.db.models import Sum, Count, Avg
from django.db.models.functions import TruncMonth

from .services import AnalyticsService

logger = logging.getLogger(__name__)


@login_required
def dashboard_view(request):
    """Main dashboard template view"""
    return render(request, 'analytics/dashboard.html', {
        'user_role': request.user.role,
    })


@login_required
@require_http_methods(["GET"])
def revenue_stats(request):
    """Get revenue analytics - Accessible to all non-customer users"""
    try:
        period_type = request.GET.get('period', 'monthly')
        custom_start = request.GET.get('start_date')
        custom_end = request.GET.get('end_date')
        
        start_date = None
        end_date = None
        
        if custom_start:
            try:
                start_date = datetime.strptime(custom_start, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({'error': 'Invalid start_date format. Use YYYY-MM-DD'}, status=400)
        
        if custom_end:
            try:
                end_date = datetime.strptime(custom_end, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({'error': 'Invalid end_date format. Use YYYY-MM-DD'}, status=400)
        
        valid_periods = ['daily', 'weekly', 'monthly', 'quarterly', 'yearly']
        if period_type not in valid_periods:
            return JsonResponse({'error': f'Invalid period. Choose from: {valid_periods}'}, status=400)
        
        # Customers cannot access analytics
        if request.user.role == 'customer':
            return JsonResponse({'error': 'Customers cannot access analytics'}, status=403)
        
        cache_key = f"analytics_revenue_{request.user.id}_{period_type}_{custom_start}_{custom_end}"
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return JsonResponse(cached_data, safe=False)
        
        # For wholesellers and resellers, filter by their ID
        user_param = None
        if request.user.role in ['wholeseller', 'reseller']:
            user_param = request.user
        
        data = AnalyticsService.get_revenue_stats(
            period_type=period_type,
            custom_start=start_date,
            custom_end=end_date,
            user=user_param
        )
        
        cache.set(cache_key, data, 900)
        return JsonResponse(data, safe=False)
        
    except Exception as e:
        logger.error(f"Error in revenue_stats: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def user_growth(request):
    """Get user growth analytics - Admin only"""
    try:
        # Only admin can view user growth
        if request.user.role != 'admin':
            return JsonResponse({
                'error': 'Only admins can view user growth analytics',
                'total_wholesellers': 0,
                'total_resellers': 0,
                'total_users': 0,
                'verified_wholesellers': 0,
                'verified_resellers': 0,
                'kyced_wholesellers': 0,
                'wholeseller_growth': 0,
                'reseller_growth': 0,
                'store_growth': 0,
                'data_points': []
            }, status=200)  # Return 200 with empty data instead of 403
        
        period_type = request.GET.get('period', 'monthly')
        custom_start = request.GET.get('start_date')
        custom_end = request.GET.get('end_date')
        
        start_date = None
        end_date = None
        
        if custom_start:
            start_date = datetime.strptime(custom_start, '%Y-%m-%d').date()
        if custom_end:
            end_date = datetime.strptime(custom_end, '%Y-%m-%d').date()
        
        cache_key = f"analytics_user_growth_{period_type}_{custom_start}_{custom_end}"
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return JsonResponse(cached_data, safe=False)
        
        data = AnalyticsService.get_user_growth(
            period_type=period_type,
            custom_start=start_date,
            custom_end=end_date
        )
        
        cache.set(cache_key, data, 1800)
        return JsonResponse(data, safe=False)
        
    except Exception as e:
        logger.error(f"Error in user_growth: {str(e)}")
        return JsonResponse({'error': str(e), 'data_points': []}, status=500)


@login_required
@require_http_methods(["GET"])
def top_products(request):
    """Get top selling products - Accessible to all non-customer users"""
    try:
        scope = request.GET.get('scope', 'platform')
        limit = int(request.GET.get('limit', 10))
        period_type = request.GET.get('period', 'monthly')
        custom_start = request.GET.get('start_date')
        custom_end = request.GET.get('end_date')
        
        valid_scopes = ['platform', 'wholeseller', 'reseller']
        if scope not in valid_scopes:
            return JsonResponse({'error': f'Invalid scope. Choose from: {valid_scopes}'}, status=400)
        
        if limit < 1 or limit > 100:
            return JsonResponse({'error': 'Limit must be between 1 and 100'}, status=400)
        
        start_date = None
        end_date = None
        
        if custom_start:
            start_date = datetime.strptime(custom_start, '%Y-%m-%d').date()
        if custom_end:
            end_date = datetime.strptime(custom_end, '%Y-%m-%d').date()
        
        if request.user.role == 'customer':
            return JsonResponse({'error': 'Customers cannot access analytics'}, status=403)
        
        cache_key = f"analytics_top_products_{request.user.id}_{scope}_{limit}_{period_type}_{custom_start}_{custom_end}"
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return JsonResponse(cached_data, safe=False)
        
        # For wholesellers and resellers, filter by their ID
        user_param = None
        if request.user.role in ['wholeseller', 'reseller']:
            user_param = request.user
        
        data = AnalyticsService.get_top_selling_products(
            scope=scope,
            limit=limit,
            period_type=period_type,
            custom_start=start_date,
            custom_end=end_date,
            user=user_param
        )
        
        cache.set(cache_key, data, 1800)
        return JsonResponse(data, safe=False)
        
    except Exception as e:
        logger.error(f"Error in top_products: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def settlement_analytics(request):
    """Get settlement and withdrawal analytics - Accessible to all non-customer users"""
    try:
        period_type = request.GET.get('period', 'monthly')
        custom_start = request.GET.get('start_date')
        custom_end = request.GET.get('end_date')
        
        start_date = None
        end_date = None
        
        if custom_start:
            start_date = datetime.strptime(custom_start, '%Y-%m-%d').date()
        if custom_end:
            end_date = datetime.strptime(custom_end, '%Y-%m-%d').date()
        
        if request.user.role == 'customer':
            return JsonResponse({'error': 'Customers cannot access analytics'}, status=403)
        
        cache_key = f"analytics_settlements_{request.user.id}_{period_type}_{custom_start}_{custom_end}"
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return JsonResponse(cached_data, safe=False)
        
        # For wholesellers and resellers, filter by their ID
        user_param = None
        if request.user.role in ['wholeseller', 'reseller']:
            user_param = request.user
        
        data = AnalyticsService.get_settlement_analytics(
            period_type=period_type,
            custom_start=start_date,
            custom_end=end_date,
            user=user_param
        )
        
        cache.set(cache_key, data, 900)
        return JsonResponse(data, safe=False)
        
    except Exception as e:
        logger.error(f"Error in settlement_analytics: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def product_performance(request):
    """Get product performance metrics - Accessible to all non-customer users"""
    try:
        period_type = request.GET.get('period', 'monthly')
        custom_start = request.GET.get('start_date')
        custom_end = request.GET.get('end_date')
        
        start_date = None
        end_date = None
        
        if custom_start:
            start_date = datetime.strptime(custom_start, '%Y-%m-%d').date()
        if custom_end:
            end_date = datetime.strptime(custom_end, '%Y-%m-%d').date()
        
        if request.user.role == 'customer':
            return JsonResponse({'error': 'Customers cannot access analytics'}, status=403)
        
        # For wholesellers and resellers, filter by their ID
        user_param = None
        if request.user.role in ['wholeseller', 'reseller']:
            user_param = request.user
        
        data = AnalyticsService.get_product_performance(
            period_type=period_type,
            custom_start=start_date,
            custom_end=end_date,
            user=user_param
        )
        
        return JsonResponse(data, safe=False)
        
    except Exception as e:
        logger.error(f"Error in product_performance: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def store_performance(request):
    """Get store performance metrics - Resellers and Admins only"""
    try:
        # Only resellers and admins can view store performance
        if request.user.role not in ['reseller', 'admin']:
            return JsonResponse({
                'error': 'Only resellers and admins can view store performance',
                'summary': {
                    'total_stores': 0,
                    'active_stores': 0,
                    'expired_stores': 0,
                    'new_stores': 0,
                    'stores_with_products': 0
                },
                'store_performance': []
            }, status=200)  # Return 200 with empty data instead of 403
        
        period_type = request.GET.get('period', 'monthly')
        custom_start = request.GET.get('start_date')
        custom_end = request.GET.get('end_date')
        
        start_date = None
        end_date = None
        
        if custom_start:
            start_date = datetime.strptime(custom_start, '%Y-%m-%d').date()
        if custom_end:
            end_date = datetime.strptime(custom_end, '%Y-%m-%d').date()
        
        # For resellers, filter by their ID
        reseller_user = None
        if request.user.role == 'reseller':
            reseller_user = request.user
        
        data = AnalyticsService.get_store_performance(
            period_type=period_type,
            custom_start=start_date,
            custom_end=end_date,
            reseller_user=reseller_user
        )
        
        return JsonResponse(data, safe=False)
        
    except Exception as e:
        logger.error(f"Error in store_performance: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def dashboard_summary(request):
    """Get complete dashboard summary - Accessible to all non-customer users"""
    try:
        period_type = request.GET.get('period', 'monthly')
        custom_start = request.GET.get('start_date')
        custom_end = request.GET.get('end_date')
        
        start_date = None
        end_date = None
        
        if custom_start:
            start_date = datetime.strptime(custom_start, '%Y-%m-%d').date()
        if custom_end:
            end_date = datetime.strptime(custom_end, '%Y-%m-%d').date()
        
        if request.user.role == 'customer':
            return JsonResponse({'error': 'Customers cannot access analytics'}, status=403)
        
        cache_key = f"analytics_dashboard_{request.user.id}_{period_type}_{custom_start}_{custom_end}"
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return JsonResponse(cached_data, safe=False)
        
        # For wholesellers and resellers, filter by their ID
        user_param = None
        if request.user.role in ['wholeseller', 'reseller']:
            user_param = request.user
        
        data = AnalyticsService.get_dashboard_summary(
            period_type=period_type,
            custom_start=start_date,
            custom_end=end_date,
            user=user_param
        )
        
        cache.set(cache_key, data, 300)
        return JsonResponse(data, safe=False)
        
    except Exception as e:
        logger.error(f"Error in dashboard_summary: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def available_periods(request):
    """Get available predefined periods - Accessible to all authenticated users"""
    try:
        today = timezone.now().date()
        periods = [
            {'value': 'daily', 'label': 'Today', 'days': 1},
            {'value': 'weekly', 'label': 'This Week', 'days': 7},
            {'value': 'monthly', 'label': 'This Month', 'days': 30},
            {'value': 'quarterly', 'label': 'This Quarter', 'days': 90},
            {'value': 'yearly', 'label': 'This Year', 'days': 365},
        ]
        
        return JsonResponse({
            'predefined_periods': periods,
            'max_custom_days': 365,
            'min_date': (today - timedelta(days=365*2)).isoformat(),
            'max_date': today.isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error in available_periods: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def export_analytics(request):
    """Export analytics data as CSV - Accessible to all non-customer users"""
    try:
        report_type = request.GET.get('type', 'revenue')
        period_type = request.GET.get('period', 'monthly')
        custom_start = request.GET.get('start_date')
        custom_end = request.GET.get('end_date')
        
        if request.user.role == 'customer':
            return JsonResponse({'error': 'Customers cannot access analytics'}, status=403)
        
        start_date = None
        end_date = None
        
        if custom_start:
            start_date = datetime.strptime(custom_start, '%Y-%m-%d').date()
        if custom_end:
            end_date = datetime.strptime(custom_end, '%Y-%m-%d').date()
        
        # For wholesellers and resellers, filter by their ID
        user_param = None
        if request.user.role in ['wholeseller', 'reseller']:
            user_param = request.user
        
        if report_type == 'revenue':
            data = AnalyticsService.get_revenue_stats(
                period_type, start_date, end_date, user=user_param
            )
            
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="revenue_report_{timezone.now().date()}.csv"'
            writer = csv.writer(response)
            
            writer.writerow(['Date', 'Revenue (₹)', 'Orders', 'Average Order Value (₹)'])
            for point in data.get('data_points', []):
                writer.writerow([
                    point.get('date') or point.get('month') or point.get('week_start') or point.get('year'),
                    point.get('revenue', 0),
                    point.get('orders', 0),
                    point.get('avg_order_value', 0)
                ])
            
            writer.writerow([])
            writer.writerow(['SUMMARY'])
            writer.writerow(['Total Revenue', f"₹{data['total_revenue']:,.2f}"])
            writer.writerow(['Total Orders', data['order_count']])
            writer.writerow(['Average Order Value', f"₹{data['avg_order_value']:,.2f}"])
            writer.writerow(['Platform Commission', f"₹{data['platform_commission']:,.2f}"])
            
            return response
        
        elif report_type == 'top_products':
            data = AnalyticsService.get_top_selling_products(
                'platform', 100, period_type, start_date, end_date, user=user_param
            )
            
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="top_products_{timezone.now().date()}.csv"'
            writer = csv.writer(response)
            writer.writerow(['Rank', 'Product Name', 'SKU', 'Quantity Sold', 'Revenue (₹)', 'Sales %'])
            
            for product in data.get('products', []):
                writer.writerow([
                    product['rank'],
                    product['product_name'],
                    product['sku'],
                    product['total_quantity_sold'],
                    f"₹{product['total_revenue']:,.2f}",
                    f"{product['sales_percentage']}%"
                ])
            
            return response
        
        elif report_type == 'settlements':
            data = AnalyticsService.get_settlement_analytics(
                period_type, start_date, end_date, user=user_param
            )
            
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="settlement_report_{timezone.now().date()}.csv"'
            writer = csv.writer(response)
            writer.writerow(['Metric', 'Value'])
            writer.writerow(['Total Settled Amount', f"₹{data['settlements']['total_settled_amount']:,.2f}"])
            writer.writerow(['Total Escrow Amount', f"₹{data['settlements']['total_escrow_amount']:,.2f}"])
            writer.writerow(['Total Released', data['settlements']['total_released']])
            writer.writerow(['Total In Escrow', data['settlements']['total_in_escrow']])
            writer.writerow(['Average Settlement Days', data['settlements']['average_settlement_days']])
            writer.writerow(['Settlement Rate', f"{data['settlements']['settlement_rate']}%"])
            
            return response
        
        return JsonResponse({'error': 'Invalid report type'}, status=400)
        
    except Exception as e:
        logger.error(f"Error in export_analytics: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def admin_dashboard(request):
    """Admin/Superuser dashboard"""
    if request.user.role != 'admin':
        return redirect('reseller_dashboard' if request.user.role == 'reseller' else 'wholeseller_dashboard')
    return render(request, 'analytics/admin_dashboard.html', {'user_role': 'admin'})

@login_required
def wholeseller_dashboard(request):
    """Wholeseller dashboard"""
    if request.user.role != 'wholeseller':
        return redirect('admin_dashboard' if request.user.role == 'admin' else 'reseller_dashboard')
    return render(request, 'analytics/wholeseller_dashboard.html', {'user_role': 'wholeseller'})

@login_required
def reseller_dashboard(request):
    """Reseller dashboard"""
    if request.user.role != 'reseller':
        return redirect('admin_dashboard' if request.user.role == 'admin' else 'wholeseller_dashboard')
    return render(request, 'analytics/reseller_dashboard.html', {'user_role': 'reseller'})

@login_required
@require_http_methods(["GET"])
def profit_analytics(request):
    """Get platform profit analytics - Admin only"""
    try:
        if request.user.role != 'admin':
            return JsonResponse({'error': 'Only admins can view profit analytics'}, status=403)
        
        period_type = request.GET.get('period', 'monthly')
        custom_start = request.GET.get('start_date')
        custom_end = request.GET.get('end_date')
        
        start_date = None
        end_date = None
        
        if custom_start:
            start_date = datetime.strptime(custom_start, '%Y-%m-%d').date()
        if custom_end:
            end_date = datetime.strptime(custom_end, '%Y-%m-%d').date()
        
        from .services import get_profit_analytics
        
        data = get_profit_analytics(period_type, start_date, end_date)
        return JsonResponse(data, safe=False)
        
    except Exception as e:
        logger.error(f"Error in profit_analytics: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def dashboard_redirect(request):
    """Redirect to the appropriate dashboard based on user role"""
    if request.user.role == 'admin':
        return redirect('admin_dashboard')
    elif request.user.role == 'wholeseller':
        return redirect('wholeseller_dashboard')
    elif request.user.role == 'reseller':
        return redirect('reseller_dashboard')
    else:
        # Customer role - no access
        return JsonResponse({'error': 'Access denied'}, status=403)

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Avg
from django.db.models.functions import TruncDay, TruncMonth, TruncYear, ExtractHour

from orders.models import Order
from settlement.services import DrapsoSettlementService


@login_required
def complete_sales_dashboard(request):
    user = request.user

    # ---------------- ROLE FILTER ----------------
    if user.is_superuser or user.role == 'admin':
        orders = Order.objects.all()

    elif user.role == 'reseller':
        orders = Order.objects.filter(reseller=user)

    elif user.role == 'wholeseller':
        orders = Order.objects.filter(wholeseller=user)

    else:
        orders = Order.objects.none()

    # Only successful payments
    orders = orders.filter(payment_status='success')

    # ---------------- DATE FILTER ----------------
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    filter_type = request.GET.get('filter', 'month')

    if start_date and end_date:
        orders = orders.filter(created_at__date__range=[start_date, end_date])

    # ---------------- GROUPING ----------------
    if filter_type == 'day':
        grouped = orders.annotate(period=TruncDay('created_at'))
    elif filter_type == 'year':
        grouped = orders.annotate(period=TruncYear('created_at'))
    else:
        grouped = orders.annotate(period=TruncMonth('created_at'))

    sales_data = grouped.values('period').annotate(
        total_sales=Sum('total_amount'),
        total_orders=Count('id'),
        avg_order=Avg('total_amount')
    ).order_by('period')

    # ---------------- SETTLEMENT CALCULATIONS ----------------
    total_reseller_profit = 0
    total_wholeseller_earnings = 0
    platform_revenue = 0
    total_shipping = 0
    loss_orders = 0

    for order in orders:
        data = DrapsoSettlementService.calculate_settlement(order)

        reseller_amt = data['sellers_payout']['reseller']['amount']
        wholeseller_amt = data['sellers_payout']['wholeseller']['amount']

        total_reseller_profit += reseller_amt
        total_wholeseller_earnings += wholeseller_amt
        platform_revenue += data['deductions']['drapso_commission']
        total_shipping += data['delivery_charges']

        if reseller_amt <= 0:
            loss_orders += 1

    # ---------------- BASIC METRICS ----------------
    total_sales = orders.aggregate(total=Sum('total_amount'))['total'] or 0
    total_orders = orders.count()
    avg_order = orders.aggregate(avg=Avg('total_amount'))['avg'] or 0

    # ---------------- GROWTH ----------------
    growth = 0
    if len(sales_data) > 1:
        current = sales_data[len(sales_data)-1]['total_sales'] or 0
        previous = sales_data[len(sales_data)-2]['total_sales'] or 0
        if previous:
            growth = ((current - previous) / previous) * 100

    # ---------------- STATUS ----------------
    status_data = orders.values('order_status').annotate(count=Count('id'))

    # ---------------- PAYMENT ----------------
    payment_data = orders.values('payment_status').annotate(count=Count('id'))

    # ---------------- TOP RESELLERS (ADMIN ONLY) ----------------
    reseller_data = []
    if user.role == 'admin' or user.is_superuser:
        reseller_data = orders.values('reseller__username').annotate(
            total=Sum('total_amount')
        ).order_by('-total')[:5]

    # ---------------- TOP PRODUCTS ----------------
    top_products = orders.values('product__name').annotate(
        revenue=Sum('total_amount'),
        qty=Sum('quantity')
    ).order_by('-revenue')[:5]

    # ---------------- PEAK HOURS ----------------
    peak_hours = orders.annotate(hour=ExtractHour('created_at')).values('hour').annotate(
        count=Count('id')
    ).order_by('-count')

    context = {
        'sales_data': sales_data,
        'total_sales': total_sales,
        'total_orders': total_orders,
        'avg_order': avg_order,
        'growth': round(growth, 2),

        'reseller_profit': round(total_reseller_profit, 2),
        'wholeseller_earnings': round(total_wholeseller_earnings, 2),
        'platform_revenue': round(platform_revenue, 2),
        'total_shipping': round(total_shipping, 2),
        'loss_orders': loss_orders,

        'status_data': status_data,
        'payment_data': payment_data,
        'reseller_data': reseller_data,
        'top_products': top_products,
        'peak_hours': peak_hours,
    }

    return render(request, 'analytics/full_sales_dashboard.html', context)