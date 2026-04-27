# analytics/services.py
from django.db import models
from django.db.models import Sum, Count, Avg, F, Q, DecimalField, FloatField, Value, IntegerField, OuterRef, Subquery
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth, TruncYear, Coalesce
from django.utils import timezone
from datetime import datetime, timedelta, date
from decimal import Decimal
from accounts.models import User, WholesellerProfile, ResellerProfile
from orders.models import Order, ReturnRequest
from products.models import ResellerProduct, WholesellerProduct, ResellerProductVariant
from settlement.models import OrderSettlement, WithdrawalRequest, Wallet
from resellers.models import Store
from wholesellers.models import WholesellerKYC
import logging

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Core analytics service - No additional models needed"""

    @staticmethod
    def get_date_range(period_type, custom_start=None, custom_end=None):
        """Get date range based on period type"""
        today = timezone.now().date()
        
        if custom_start and custom_end:
            return custom_start, custom_end
        
        if period_type == 'daily':
            start = today
            end = today
        elif period_type == 'weekly':
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=6)
        elif period_type == 'monthly':
            start = today.replace(day=1)
            if start.month == 12:
                end = start.replace(year=start.year+1, month=1) - timedelta(days=1)
            else:
                end = start.replace(month=start.month+1) - timedelta(days=1)
        elif period_type == 'quarterly':
            quarter = (today.month - 1) // 3
            start = today.replace(month=quarter*3+1, day=1)
            if start.month == 10:
                end = start.replace(year=start.year+1, month=1) - timedelta(days=1)
            elif start.month == 7:
                end = start.replace(month=10, day=1) - timedelta(days=1)
            elif start.month == 4:
                end = start.replace(month=7, day=1) - timedelta(days=1)
            else:
                end = start.replace(month=4, day=1) - timedelta(days=1)
        elif period_type == 'yearly':
            start = today.replace(month=1, day=1)
            end = today.replace(month=12, day=31)
        else:
            start = today
            end = today
        
        return start, end

    @staticmethod
    def get_previous_period(start_date, end_date):
        """Calculate previous period for comparison"""
        duration = (end_date - start_date).days
        prev_end = start_date - timedelta(days=1)
        prev_start = prev_end - timedelta(days=duration)
        return prev_start, prev_end

    @staticmethod
    def get_revenue_stats(period_type='monthly', custom_start=None, custom_end=None, user=None):
        """Get revenue statistics for given period"""
        start_date, end_date = AnalyticsService.get_date_range(period_type, custom_start, custom_end)
        
        # Base queryset for delivered orders - using correct field names
        orders = Order.objects.filter(
            order_status='delivered',
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )
        
        # Apply user filter
        if user:
            if user.role == 'wholeseller':
                orders = orders.filter(wholeseller=user)
            elif user.role == 'reseller':
                orders = orders.filter(reseller=user)
        
        # Get settlements for commission data (only released settlements)
        settlements = OrderSettlement.objects.filter(
            order__in=orders, 
            status='RELEASED'
        )
        
        # Basic order stats - using total_amount (customer paid amount)
        stats = orders.aggregate(
            total_revenue=Coalesce(Sum('total_amount'), Decimal('0')),
            total_orders=Coalesce(Count('id', distinct=True), 0),
            total_shipping=Coalesce(Sum('shipping_charge'), Decimal('0')),
            avg_order_value=Coalesce(Avg('total_amount'), Decimal('0')),
            total_quantity=Coalesce(Sum('quantity'), 0)
        )
        
        # Settlement stats
        settlement_stats = settlements.aggregate(
            platform_commission=Coalesce(Sum('drapso_commission'), Decimal('0')),
            wholeseller_payout=Coalesce(Sum('wholeseller_amount'), Decimal('0')),
            reseller_payout=Coalesce(Sum('reseller_amount'), Decimal('0'))
        )
        
        # Previous period for growth calculation
        prev_start, prev_end = AnalyticsService.get_previous_period(start_date, end_date)
        prev_orders = Order.objects.filter(
            order_status='delivered',
            created_at__date__gte=prev_start,
            created_at__date__lte=prev_end
        )
        
        if user:
            if user.role == 'wholeseller':
                prev_orders = prev_orders.filter(wholeseller=user)
            elif user.role == 'reseller':
                prev_orders = prev_orders.filter(reseller=user)
        
        prev_revenue = prev_orders.aggregate(total=Coalesce(Sum('total_amount'), Decimal('0')))['total']
        current_revenue = stats['total_revenue']
        
        # Calculate growth percentages
        revenue_growth = 0
        if prev_revenue > 0:
            revenue_growth = float(((current_revenue - prev_revenue) / prev_revenue * 100))
        elif current_revenue > 0:
            revenue_growth = 100
        
        prev_order_count = prev_orders.count()
        current_order_count = stats['total_orders']
        
        order_growth = 0
        if prev_order_count > 0:
            order_growth = float(((current_order_count - prev_order_count) / prev_order_count * 100))
        elif current_order_count > 0:
            order_growth = 100
        
        # Time-series data points
        data_points = []
        if period_type == 'daily':
            # Group by date
            daily_data = orders.annotate(
                date=TruncDate('created_at')
            ).values('date').annotate(
                revenue=Coalesce(Sum('total_amount'), Decimal('0')),
                count=Coalesce(Count('id'), 0),
                avg_value=Coalesce(Avg('total_amount'), Decimal('0'))
            ).order_by('date')
            
            # Create dict for quick lookup
            daily_dict = {item['date']: item for item in daily_data if item['date']}
            
            # Fill all dates in range
            current_date = start_date
            while current_date <= end_date:
                point = daily_dict.get(current_date)
                data_points.append({
                    'date': current_date.isoformat(),
                    'revenue': float(point['revenue']) if point else 0,
                    'orders': point['count'] if point else 0,
                    'avg_order_value': float(point['avg_value']) if point else 0
                })
                current_date += timedelta(days=1)
                
        elif period_type == 'weekly':
            # Group by week
            weekly_data = orders.annotate(
                week_start=TruncWeek('created_at')
            ).values('week_start').annotate(
                revenue=Coalesce(Sum('total_amount'), Decimal('0')),
                count=Coalesce(Count('id'), 0)
            ).order_by('week_start')
            
            weekly_dict = {}
            for item in weekly_data:
                if item['week_start']:
                    weekly_dict[item['week_start'].date()] = item
            
            current = start_date
            while current <= end_date:
                week_start = current - timedelta(days=current.weekday())
                point = weekly_dict.get(week_start)
                data_points.append({
                    'week_start': week_start.isoformat(),
                    'week_end': (week_start + timedelta(days=6)).isoformat(),
                    'revenue': float(point['revenue']) if point else 0,
                    'orders': point['count'] if point else 0
                })
                current += timedelta(days=7)
                
        elif period_type == 'monthly':
            # Group by month
            monthly_data = orders.annotate(
                month=TruncMonth('created_at')
            ).values('month').annotate(
                revenue=Coalesce(Sum('total_amount'), Decimal('0')),
                count=Coalesce(Count('id'), 0)
            ).order_by('month')
            
            monthly_dict = {}
            for item in monthly_data:
                if item['month']:
                    monthly_dict[item['month'].date()] = item
            
            current = start_date
            while current <= end_date:
                month_start = current.replace(day=1)
                point = monthly_dict.get(month_start)
                data_points.append({
                    'month': month_start.strftime('%Y-%m'),
                    'month_start': month_start.isoformat(),
                    'revenue': float(point['revenue']) if point else 0,
                    'orders': point['count'] if point else 0
                })
                # Move to next month
                if current.month == 12:
                    current = current.replace(year=current.year+1, month=1)
                else:
                    current = current.replace(month=current.month+1)
                    
        else:  # yearly
            yearly_data = orders.annotate(
                year=TruncYear('created_at')
            ).values('year').annotate(
                revenue=Coalesce(Sum('total_amount'), Decimal('0')),
                count=Coalesce(Count('id'), 0)
            ).order_by('year')
            
            yearly_dict = {}
            for item in yearly_data:
                if item['year']:
                    yearly_dict[item['year'].year] = item
            
            for year in range(start_date.year, end_date.year + 1):
                point = yearly_dict.get(year)
                data_points.append({
                    'year': year,
                    'revenue': float(point['revenue']) if point else 0,
                    'orders': point['count'] if point else 0
                })
        
        return {
            'period': {
                'type': period_type, 
                'start_date': start_date.isoformat(), 
                'end_date': end_date.isoformat()
            },
            'total_revenue': float(stats['total_revenue']),
            'platform_commission': float(settlement_stats['platform_commission']),
            'wholeseller_payout': float(settlement_stats['wholeseller_payout']),
            'reseller_payout': float(settlement_stats['reseller_payout']),
            'order_count': stats['total_orders'],
            'total_quantity': stats['total_quantity'],
            'total_shipping': float(stats['total_shipping']),
            'avg_order_value': float(stats['avg_order_value']),
            'revenue_growth': round(revenue_growth, 2),
            'order_growth': round(order_growth, 2),
            'data_points': data_points
        }

    @staticmethod
    def get_user_growth(period_type='monthly', custom_start=None, custom_end=None):
        """Get user growth statistics (Admin only)"""
        start_date, end_date = AnalyticsService.get_date_range(period_type, custom_start, custom_end)
        
        # Current period new users
        current_new_users = User.objects.filter(
            date_joined__date__gte=start_date, 
            date_joined__date__lte=end_date
        )
        
        # Previous period for comparison
        prev_start, prev_end = AnalyticsService.get_previous_period(start_date, end_date)
        prev_new_users = User.objects.filter(
            date_joined__date__gte=prev_start, 
            date_joined__date__lte=prev_end
        )
        
        # Role counts
        current_wholesellers = current_new_users.filter(role='wholeseller').count()
        current_resellers = current_new_users.filter(role='reseller').count()
        prev_wholesellers = prev_new_users.filter(role='wholeseller').count()
        prev_resellers = prev_new_users.filter(role='reseller').count()
        
        # Calculate growth rates
        total_growth = 0
        if prev_new_users.count() > 0:
            total_growth = ((current_new_users.count() - prev_new_users.count()) / prev_new_users.count() * 100)
        elif current_new_users.count() > 0:
            total_growth = 100
            
        wholeseller_growth = 0
        if prev_wholesellers > 0:
            wholeseller_growth = ((current_wholesellers - prev_wholesellers) / prev_wholesellers * 100)
        elif current_wholesellers > 0:
            wholeseller_growth = 100
            
        reseller_growth = 0
        if prev_resellers > 0:
            reseller_growth = ((current_resellers - prev_resellers) / prev_resellers * 100)
        elif current_resellers > 0:
            reseller_growth = 100
        
        # Current totals
        total_users = User.objects.count()
        total_wholesellers = User.objects.filter(role='wholeseller').count()
        total_resellers = User.objects.filter(role='reseller').count()
        
        # FIXED: Wholeseller Verification Logic
        # A wholeseller is verified if:
        # 1. Their KYC status is 'approved' AND
        # 2. Their inventory is verified (is_verified=True)
        from wholesellers.models import WholesellerKYC, WholesellerInventory
        
        # Get all wholeseller users
        wholeseller_users = User.objects.filter(role='wholeseller')
        
        # Count verified wholesellers (KYC approved AND inventory verified)
        verified_wholesellers = 0
        kyced_wholesellers = 0
        
        for wholeseller in wholeseller_users:
            try:
                # Check KYC status
                kyc = WholesellerKYC.objects.get(wholeseller=wholeseller)
                if kyc.status == 'approved':
                    kyced_wholesellers += 1
                    
                    # Check if inventory is also verified
                    if hasattr(wholeseller, 'inventory') and wholeseller.inventory.is_verified:
                        verified_wholesellers += 1
            except WholesellerKYC.DoesNotExist:
                pass
        
        # FIXED: Reseller Verification Logic
        # A reseller is verified if:
        # 1. They have at least one store that is 'active' AND
        # 2. The store has payment_status = True (subscription paid)
        reseller_users = User.objects.filter(role='reseller')
        
        verified_resellers = 0
        for reseller in reseller_users:
            # Check if reseller has any active store with payment completed
            has_active_store = Store.objects.filter(
                reseller=reseller,
                status='active',
                payment_status=True,
                is_published=True
            ).exists()
            
            if has_active_store:
                verified_resellers += 1
        
        # Store stats
        total_stores = Store.objects.count()
        active_stores = Store.objects.filter(status='active', payment_status=True).count()
        current_new_stores = Store.objects.filter(
            created_at__date__gte=start_date, 
            created_at__date__lte=end_date
        ).count()
        prev_new_stores = Store.objects.filter(
            created_at__date__gte=prev_start, 
            created_at__date__lte=prev_end
        ).count()
        
        store_growth = 0
        if prev_new_stores > 0:
            store_growth = ((current_new_stores - prev_new_stores) / prev_new_stores * 100)
        elif current_new_stores > 0:
            store_growth = 100
        
        # Time series data points
        data_points = []
        if period_type == 'daily':
            daily_data = User.objects.filter(
                date_joined__date__gte=start_date, 
                date_joined__date__lte=end_date
            ).annotate(
                date=TruncDate('date_joined')
            ).values('date').annotate(
                total=Coalesce(Count('id'), 0),
                wholesellers=Coalesce(Count('id', filter=Q(role='wholeseller')), 0),
                resellers=Coalesce(Count('id', filter=Q(role='reseller')), 0),
                customers=Coalesce(Count('id', filter=Q(role='customer')), 0)
            ).order_by('date')
            
            daily_dict = {item['date']: item for item in daily_data if item['date']}
            
            current_date = start_date
            while current_date <= end_date:
                point = daily_dict.get(current_date)
                data_points.append({
                    'date': current_date.isoformat(),
                    'total': point['total'] if point else 0,
                    'wholesellers': point['wholesellers'] if point else 0,
                    'resellers': point['resellers'] if point else 0,
                    'customers': point['customers'] if point else 0
                })
                current_date += timedelta(days=1)
                
        elif period_type == 'monthly':
            monthly_data = User.objects.filter(
                date_joined__date__gte=start_date, 
                date_joined__date__lte=end_date
            ).annotate(
                month=TruncMonth('date_joined')
            ).values('month').annotate(
                total=Coalesce(Count('id'), 0),
                wholesellers=Coalesce(Count('id', filter=Q(role='wholeseller')), 0),
                resellers=Coalesce(Count('id', filter=Q(role='reseller')), 0),
                customers=Coalesce(Count('id', filter=Q(role='customer')), 0)
            ).order_by('month')
            
            monthly_dict = {}
            for item in monthly_data:
                if item['month']:
                    monthly_dict[item['month'].date()] = item
            
            current = start_date
            while current <= end_date:
                month_start = current.replace(day=1)
                point = monthly_dict.get(month_start)
                data_points.append({
                    'month': month_start.strftime('%Y-%m'),
                    'total': point['total'] if point else 0,
                    'wholesellers': point['wholesellers'] if point else 0,
                    'resellers': point['resellers'] if point else 0,
                    'customers': point['customers'] if point else 0
                })
                if current.month == 12:
                    current = current.replace(year=current.year+1, month=1)
                else:
                    current = current.replace(month=current.month+1)
        
        return {
            'period': {
                'type': period_type, 
                'start_date': start_date.isoformat(), 
                'end_date': end_date.isoformat()
            },
            'total_users': total_users,
            'total_wholesellers': total_wholesellers,
            'total_resellers': total_resellers,
            'total_stores': total_stores,
            'active_stores': active_stores,
            'verified_wholesellers': verified_wholesellers,
            'verified_resellers': verified_resellers,
            'kyced_wholesellers': kyced_wholesellers,
            'current_period_new': current_new_users.count(),
            'previous_period_new': prev_new_users.count(),
            'total_growth': round(total_growth, 2),
            'wholeseller_growth': round(wholeseller_growth, 2),
            'reseller_growth': round(reseller_growth, 2),
            'store_growth': round(store_growth, 2),
            'data_points': data_points
        }

    @staticmethod
    def get_top_selling_products(scope='platform', limit=10, period_type='monthly', 
                                   custom_start=None, custom_end=None, user=None):
        """Get top selling products"""
        start_date, end_date = AnalyticsService.get_date_range(period_type, custom_start, custom_end)
        
        orders = Order.objects.filter(
            order_status='delivered', 
            created_at__date__gte=start_date, 
            created_at__date__lte=end_date,
            product__isnull=False  # Only orders with products
        )
        
        # Apply scope filters
        if scope == 'wholeseller' and user and user.role == 'wholeseller':
            orders = orders.filter(wholeseller=user)
        elif scope == 'reseller' and user and user.role == 'reseller':
            orders = orders.filter(reseller=user)
        elif user and user.role in ['wholeseller', 'reseller']:
            # For platform view with user filter
            if user.role == 'wholeseller':
                orders = orders.filter(wholeseller=user)
            else:
                orders = orders.filter(reseller=user)
        
        # Aggregate by product
        top_products = orders.values(
            'product_id', 
            'product__name', 
            'product__sku'
        ).annotate(
            total_quantity=Coalesce(Sum('quantity'), 0),
            total_revenue=Coalesce(Sum('total_amount'), Decimal('0'))
        ).order_by('-total_quantity')[:limit]
        
        total_quantity_all = orders.aggregate(total=Coalesce(Sum('quantity'), 0))['total']
        
        result = []
        for idx, product in enumerate(top_products, 1):
            sales_percentage = (product['total_quantity'] / total_quantity_all * 100) if total_quantity_all > 0 else 0
            result.append({
                'rank': idx,
                'product_id': product['product_id'],
                'product_name': product['product__name'] or 'Unknown',
                'sku': product['product__sku'] or 'N/A',
                'total_quantity_sold': product['total_quantity'],
                'total_revenue': float(product['total_revenue']),
                'sales_percentage': round(sales_percentage, 2)
            })
        
        return {
            'scope': scope,
            'period': {'start_date': start_date.isoformat(), 'end_date': end_date.isoformat()},
            'limit': limit,
            'total_products_sold': total_quantity_all,
            'products': result
        }

    @staticmethod
    def get_settlement_analytics(period_type='monthly', custom_start=None, custom_end=None, user=None):
        """Get settlement and withdrawal analytics"""
        from settlement.services import WithdrawalService
        
        start_date, end_date = AnalyticsService.get_date_range(period_type, custom_start, custom_end)
        
        settlements = OrderSettlement.objects.filter(
            created_at__date__gte=start_date, 
            created_at__date__lte=end_date
        )
        
        if user:
            if user.role == 'wholeseller':
                settlements = settlements.filter(order__wholeseller=user)
            elif user.role == 'reseller':
                settlements = settlements.filter(order__reseller=user)
        
        released_settlements = settlements.filter(status='RELEASED')
        in_escrow_settlements = settlements.filter(status='IN_ESCROW')
        cancelled_settlements = settlements.filter(status='CANCELLED')
        
        # Fee breakdown
        fee_breakdown = settlements.aggregate(
            total_razorpay_fee=Coalesce(Sum('razorpay_fee'), Decimal('0')),
            total_drapso_commission=Coalesce(Sum('drapso_commission'), Decimal('0')),
            total_neft_cost=Coalesce(Sum('neft_settlement_cost'), Decimal('0')),
            total_delivery_charges=Coalesce(Sum('delivery_charges'), Decimal('0'))
        )
        
        # Settlement stats - using order_total from settlement model
        stats = {
            'total_settled_amount': released_settlements.aggregate(
                total=Coalesce(Sum('order_total'), Decimal('0'))
            )['total'],
            'total_escrow_amount': in_escrow_settlements.aggregate(
                total=Coalesce(Sum('order_total'), Decimal('0'))
            )['total'],
            'total_released': released_settlements.count(),
            'total_in_escrow': in_escrow_settlements.count(),
            'total_cancelled': cancelled_settlements.count(),
            'total_refunded': settlements.filter(status='REFUNDED').count(),
        }
        
        # Average settlement time
        avg_settlement_time = released_settlements.filter(
            escrow_released_at__isnull=False, 
            delivered_at__isnull=False
        ).annotate(
            days_diff=models.ExpressionWrapper(
                models.F('escrow_released_at') - models.F('delivered_at'),
                output_field=models.DurationField()
            )
        ).aggregate(avg_days=Avg('days_diff'))
        
        avg_days = 0
        if avg_settlement_time['avg_days']:
            avg_days = avg_settlement_time['avg_days'].days + (avg_settlement_time['avg_days'].seconds / 86400)
        
        total_processed = stats['total_released'] + stats['total_cancelled'] + stats['total_refunded']
        settlement_rate = (stats['total_released'] / total_processed * 100) if total_processed > 0 else 0
        
        # Withdrawal statistics
        withdrawals = WithdrawalRequest.objects.filter(
            requested_at__date__gte=start_date, 
            requested_at__date__lte=end_date
        )
        if user:
            withdrawals = withdrawals.filter(wallet__user=user)
        
        withdrawal_stats = withdrawals.aggregate(
            total_requested=Coalesce(Sum('amount'), Decimal('0')),
            total_completed=Coalesce(Sum('amount', filter=Q(status='COMPLETED')), Decimal('0')),
            total_pending=Coalesce(Sum('amount', filter=Q(status='PENDING')), Decimal('0')),
            total_rejected=Coalesce(Sum('amount', filter=Q(status='REJECTED')), Decimal('0')),
            request_count=Coalesce(Count('id'), 0),
            completed_count=Coalesce(Count('id', filter=Q(status='COMPLETED')), 0),
            pending_count=Coalesce(Count('id', filter=Q(status='PENDING')), 0),
            rejected_count=Coalesce(Count('id', filter=Q(status='REJECTED')), 0)
        )
        
        # Wallet balance for user
        wallet_balance = None
        if user and hasattr(user, 'wallet'):
            wallet = user.wallet
            wallet_balance = {
                'available': float(wallet.available_balance),
                'escrow': float(wallet.escrow_balance),
                'pending_withdrawal': float(wallet.pending_withdrawal),
                'total_credited': float(wallet.total_credited),
                'total_withdrawn': float(wallet.total_withdrawn)
            }
            try:
                is_eligible, eligibility_message = WithdrawalService.can_request_withdrawal(wallet, 100)
                wallet_balance['can_withdraw'] = is_eligible
                wallet_balance['withdrawal_message'] = eligibility_message
            except:
                wallet_balance['can_withdraw'] = True
                wallet_balance['withdrawal_message'] = 'Eligible for withdrawal'
        
        # Time series data
        data_points = released_settlements.annotate(
            date=TruncDate('escrow_released_at')
        ).values('date').annotate(
            amount=Coalesce(Sum('order_total'), Decimal('0')),
            count=Coalesce(Count('id'), 0)
        ).order_by('date')
        
        return {
            'period': {'type': period_type, 'start_date': start_date.isoformat(), 'end_date': end_date.isoformat()},
            'settlements': {
                'total_settled_amount': float(stats['total_settled_amount']),
                'total_escrow_amount': float(stats['total_escrow_amount']),
                'total_released': stats['total_released'],
                'total_in_escrow': stats['total_in_escrow'],
                'total_cancelled': stats['total_cancelled'],
                'total_refunded': stats['total_refunded'],
                'average_settlement_days': round(avg_days, 1),
                'settlement_rate': round(settlement_rate, 2)
            },
            'fee_breakdown': {
                'total_razorpay_fee': float(fee_breakdown['total_razorpay_fee']),
                'total_drapso_commission': float(fee_breakdown['total_drapso_commission']),
                'total_neft_cost': float(fee_breakdown['total_neft_cost']),
                'total_delivery_charges': float(fee_breakdown['total_delivery_charges'])
            },
            'withdrawal_stats': {
                'total_requested': float(withdrawal_stats['total_requested']),
                'total_completed': float(withdrawal_stats['total_completed']),
                'total_pending': float(withdrawal_stats['total_pending']),
                'total_rejected': float(withdrawal_stats['total_rejected']),
                'request_count': withdrawal_stats['request_count'],
                'completed_count': withdrawal_stats['completed_count'],
                'pending_count': withdrawal_stats['pending_count'],
                'rejected_count': withdrawal_stats['rejected_count'],
                'completion_rate': round((withdrawal_stats['completed_count'] / withdrawal_stats['request_count'] * 100), 2) if withdrawal_stats['request_count'] > 0 else 0
            },
            'wallet_balance': wallet_balance,
            'data_points': list(data_points)
        }

    @staticmethod
    def get_product_performance(period_type='monthly', custom_start=None, custom_end=None, user=None):
        """Get product performance metrics"""
        start_date, end_date = AnalyticsService.get_date_range(period_type, custom_start, custom_end)
        
        # Base querysets
        reseller_products = ResellerProduct.objects.all()
        wholeseller_products = WholesellerProduct.objects.all()
        
        if user:
            if user.role == 'wholeseller':
                wholeseller_products = wholeseller_products.filter(wholeseller=user)
                reseller_products = reseller_products.filter(source_product__wholeseller=user)
            elif user.role == 'reseller':
                reseller_products = reseller_products.filter(reseller=user)
        
        # New products in period
        new_reseller_products = reseller_products.filter(
            created_at__date__gte=start_date, 
            created_at__date__lte=end_date
        )
        new_wholeseller_products = wholeseller_products.filter(
            created_at__date__gte=start_date, 
            created_at__date__lte=end_date
        )
        
        # Stock statistics
        low_stock_products = reseller_products.filter(
            stock__lte=F('threshold_limit'), 
            stock__gt=0, 
            is_active=True
        ).count()
        
        out_of_stock_products = reseller_products.filter(
            stock=0, 
            is_active=True
        ).count()
        
        # Category distribution
        category_distribution = reseller_products.filter(
            is_active=True, 
            category__isnull=False
        ).values('category__name').annotate(
            count=Coalesce(Count('id'), 0)
        ).order_by('-count')[:10]
        
        # Variant statistics
        total_variants = ResellerProductVariant.objects.filter(
            product__in=reseller_products, 
            is_active=True
        ).count()
        
        active_products_count = reseller_products.filter(is_active=True).count()
        avg_variants = round(total_variants / active_products_count, 2) if active_products_count > 0 else 0
        
        return {
            'period': {'start_date': start_date.isoformat(), 'end_date': end_date.isoformat()},
            'wholeseller_products': {
                'total': wholeseller_products.count(),
                'active': wholeseller_products.filter(is_active=True).count(),
                'new_in_period': new_wholeseller_products.count(),
                'with_variants': wholeseller_products.filter(variants__isnull=False).distinct().count()
            },
            'reseller_products': {
                'total': reseller_products.count(),
                'active': active_products_count,
                'published': reseller_products.filter(is_published=True).count(),
                'new_in_period': new_reseller_products.count(),
                'imported': reseller_products.filter(source_type='imported').count(),
                'own': reseller_products.filter(source_type='own').count(),
                'low_stock': low_stock_products,
                'out_of_stock': out_of_stock_products
            },
            'variants': {
                'total': total_variants,
                'avg_per_product': avg_variants
            },
            'top_categories': list(category_distribution)
        }

    @staticmethod
    def get_store_performance(period_type='monthly', custom_start=None, custom_end=None, reseller_user=None):
        """Get store performance metrics for resellers"""
        start_date, end_date = AnalyticsService.get_date_range(period_type, custom_start, custom_end)
        
        stores = Store.objects.all()
        if reseller_user:
            stores = stores.filter(reseller=reseller_user)
        
        # Active stores are those with status='active' AND payment_status=True
        active_stores = stores.filter(status='active', payment_status=True)
        # Published stores are active stores that are published
        published_stores = active_stores.filter(is_published=True)
        new_stores = stores.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)
        
        store_performance = []
        for store in stores:
            orders = Order.objects.filter(
                store=store, 
                order_status='delivered', 
                created_at__date__gte=start_date, 
                created_at__date__lte=end_date
            )
            
            # Check if store is considered verified (active + payment complete)
            is_verified = store.status == 'active' and store.payment_status
            
            store_performance.append({
                'store_id': store.id,
                'store_name': store.store_name,
                'status': store.status,
                'is_verified': is_verified,
                'payment_status': store.payment_status,
                'subscription_plan': store.subscription_plan.name if store.subscription_plan else None,
                'total_orders': orders.count(),
                'total_revenue': float(orders.aggregate(total=Coalesce(Sum('total_amount'), Decimal('0')))['total']),
                'total_products': store.products.filter(is_active=True).count(),
                'avg_order_value': float(orders.aggregate(avg=Coalesce(Avg('total_amount'), Decimal('0')))['avg']),
                'total_visitors': store.total_visitors
            })
        
        store_performance.sort(key=lambda x: x['total_revenue'], reverse=True)
        
        return {
            'period': {'start_date': start_date.isoformat(), 'end_date': end_date.isoformat()},
            'summary': {
                'total_stores': stores.count(),
                'active_stores': active_stores.count(),
                'published_stores': published_stores.count(),
                'verified_stores': active_stores.count(),  # Active stores are verified
                'inactive_stores': stores.filter(status='suspended').count(),
                'expired_stores': stores.filter(status='expired').count(),
                'pending_payment_stores': stores.filter(status='pending_payment').count(),
                'new_stores': new_stores.count(),
                'stores_with_products': stores.filter(products__isnull=False).distinct().count()
            },
            'store_performance': store_performance[:20]
        }
    @staticmethod
    def get_dashboard_summary(period_type='monthly', custom_start=None, custom_end=None, user=None):
        """Get complete dashboard summary"""
        start_date, end_date = AnalyticsService.get_date_range(period_type, custom_start, custom_end)
        
        # Get all required stats
        revenue_stats = AnalyticsService.get_revenue_stats(period_type, custom_start, custom_end, user)
        settlement_stats = AnalyticsService.get_settlement_analytics(period_type, custom_start, custom_end, user)
        top_products = AnalyticsService.get_top_selling_products('platform', 10, period_type, custom_start, custom_end, user)
        
        # User growth only for admin
        user_growth = None
        if not user or user.role == 'admin':
            user_growth = AnalyticsService.get_user_growth(period_type, custom_start, custom_end)
        
        product_performance = AnalyticsService.get_product_performance(period_type, custom_start, custom_end, user)
        
        # Quick stats
        orders = Order.objects.filter(
            order_status='delivered', 
            created_at__date__gte=start_date, 
            created_at__date__lte=end_date
        )
        if user:
            if user.role == 'wholeseller':
                orders = orders.filter(wholeseller=user)
            elif user.role == 'reseller':
                orders = orders.filter(reseller=user)
        
        total_orders_in_period = Order.objects.filter(
            created_at__date__gte=start_date, 
            created_at__date__lte=end_date
        ).count()
        
        completion_rate = (orders.count() / total_orders_in_period * 100) if total_orders_in_period > 0 else 0
        
        quick_stats = {
            'total_orders': orders.count(),
            'total_customers': orders.values('customer_email').distinct().count(),
            'avg_order_value': float(orders.aggregate(avg=Coalesce(Avg('total_amount'), Decimal('0')))['avg']),
            'total_products_sold': orders.aggregate(total=Coalesce(Sum('quantity'), 0))['total'],
            'completion_rate': round(completion_rate, 2)
        }
        
        return {
            'period': {'type': period_type, 'start_date': start_date.isoformat(), 'end_date': end_date.isoformat()},
            'quick_stats': quick_stats,
            'revenue': revenue_stats,
            'settlements': settlement_stats,
            'top_products': top_products,
            'user_growth': user_growth,
            'product_performance': product_performance
        }


def get_profit_analytics(period_type='monthly', custom_start=None, custom_end=None):
    """Get platform profit analytics (Admin only)"""
    start_date, end_date = AnalyticsService.get_date_range(period_type, custom_start, custom_end)
    
    settlements = OrderSettlement.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
        status='RELEASED'
    )
    
    # Calculate platform profit
    platform_stats = settlements.aggregate(
        total_commission=Coalesce(Sum('drapso_commission'), Decimal('0')),
        total_razorpay_fees=Coalesce(Sum('razorpay_fee'), Decimal('0')),
        total_neft_fees=Coalesce(Sum('neft_settlement_cost'), Decimal('0')),
        total_revenue=Coalesce(Sum('order_total'), Decimal('0'))
    )
    
    total_platform_income = (
        platform_stats['total_commission'] + 
        platform_stats['total_razorpay_fees'] + 
        platform_stats['total_neft_fees']
    )
    
    total_revenue = platform_stats['total_revenue']
    profit_margin = (total_platform_income / total_revenue * 100) if total_revenue > 0 else 0
    
    # Seller payouts
    seller_payouts = settlements.aggregate(
        wholeseller_payout=Coalesce(Sum('wholeseller_amount'), Decimal('0')),
        reseller_payout=Coalesce(Sum('reseller_amount'), Decimal('0'))
    )
    
    total_seller_payout = seller_payouts['wholeseller_payout'] + seller_payouts['reseller_payout']
    
    # Separate imported vs own products
    imported_settlements = settlements.filter(is_imported=True)
    own_settlements = settlements.filter(is_imported=False)
    
    imported_stats = {
        'total_revenue': float(imported_settlements.aggregate(total=Coalesce(Sum('order_total'), Decimal('0')))['total']),
        'platform_commission': float(imported_settlements.aggregate(total=Coalesce(Sum('drapso_commission'), Decimal('0')))['total']),
        'wholeseller_payout': float(imported_settlements.aggregate(total=Coalesce(Sum('wholeseller_amount'), Decimal('0')))['total']),
        'reseller_payout': float(imported_settlements.aggregate(total=Coalesce(Sum('reseller_amount'), Decimal('0')))['total'])
    }
    
    own_stats = {
        'total_revenue': float(own_settlements.aggregate(total=Coalesce(Sum('order_total'), Decimal('0')))['total']),
        'platform_commission': float(own_settlements.aggregate(total=Coalesce(Sum('drapso_commission'), Decimal('0')))['total']),
        'reseller_payout': float(own_settlements.aggregate(total=Coalesce(Sum('reseller_amount'), Decimal('0')))['total'])
    }
    
    # Time-series profit data
    profit_trend = settlements.annotate(
        month=TruncMonth('created_at')
    ).values('month').annotate(
        revenue=Coalesce(Sum('order_total'), Decimal('0')),
        commission=Coalesce(Sum('drapso_commission'), Decimal('0')),
        fees=Coalesce(Sum('razorpay_fee'), Decimal('0'))
    ).order_by('month')
    
    profit_trend_list = []
    for item in profit_trend:
        if item['month']:
            profit_trend_list.append({
                'month': item['month'].strftime('%Y-%m'),
                'revenue': float(item['revenue']),
                'commission': float(item['commission']),
                'fees': float(item['fees']),
                'profit': float(item['commission'] + item['fees'])
            })
    
    return {
        'period': {'start_date': start_date.isoformat(), 'end_date': end_date.isoformat()},
        'platform_profit': {
            'total_revenue': float(total_revenue),
            'total_commission': float(platform_stats['total_commission']),
            'total_razorpay_fees': float(platform_stats['total_razorpay_fees']),
            'total_neft_fees': float(platform_stats['total_neft_fees']),
            'total_platform_income': float(total_platform_income),
            'profit_margin': round(profit_margin, 2)
        },
        'seller_payouts': {
            'total_wholeseller_payout': float(seller_payouts['wholeseller_payout']),
            'total_reseller_payout': float(seller_payouts['reseller_payout']),
            'total_seller_payout': float(total_seller_payout)
        },
        'product_type_breakdown': {
            'imported': imported_stats,
            'own': own_stats
        },
        'profit_trend': profit_trend_list
    }