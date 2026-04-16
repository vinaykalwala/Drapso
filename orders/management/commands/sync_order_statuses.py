# orders/management/commands/sync_order_statuses.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from orders.models import Order
from shiprocket.services import ShiprocketService
import time

class Command(BaseCommand):
    help = 'Sync order statuses from Shiprocket for orders without recent updates'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Sync orders updated more than N hours ago (default: 24)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Maximum number of orders to sync (default: 50)'
        )
    
    def handle(self, *args, **options):
        hours = options['hours']
        limit = options['limit']
        
        cutoff_time = timezone.now() - timezone.timedelta(hours=hours)
        
        orders = Order.objects.filter(
            awb_code__isnull=False,
            order_status__in=['approved', 'shipped', 'out_for_delivery'],
            updated_at__lt=cutoff_time
        ).exclude(
            order_status='delivered'
        ).exclude(
            order_status='cancelled'
        )[:limit]
        
        self.stdout.write(f"Found {orders.count()} orders to sync")
        
        shiprocket = ShiprocketService()
        synced_count = 0
        
        for order in orders:
            try:
                tracking_info = shiprocket.track_shipment(order.awb_code)
                
                if tracking_info and tracking_info.get('data'):
                    current_status = tracking_info['data'].get('current_status', '')
                    
                    if current_status == 'Delivered' and order.order_status != 'delivered':
                        order.order_status = 'delivered'
                        order.delivered_at = timezone.now()
                        order.save()
                        synced_count += 1
                        self.stdout.write(f"✓ Order {order.order_id} marked as delivered")
                        
                    elif current_status == 'Out for Delivery' and order.order_status != 'out_for_delivery':
                        order.order_status = 'out_for_delivery'
                        order.save()
                        synced_count += 1
                        self.stdout.write(f"✓ Order {order.order_id} out for delivery")
                        
                    elif current_status == 'In Transit' and order.order_status == 'approved':
                        order.order_status = 'shipped'
                        order.shipped_at = timezone.now()
                        order.save()
                        synced_count += 1
                        self.stdout.write(f"✓ Order {order.order_id} shipped")
                
                time.sleep(0.5)
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to sync order {order.order_id}: {e}"))
        
        self.stdout.write(self.style.SUCCESS(f"Synced {synced_count} orders"))