# management/commands/sync_shiprocket.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from orders.models import Order 
from settlement.services import DrapsoSettlementService
from shiprocket.services import ShiprocketService
from orders.webhook_views import map_shiprocket_status 
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Syncs active orders with Shiprocket to update status and actual freight charges'

    def add_arguments(self, parser):
        parser.add_argument(
            '--order-id',
            type=str,
            help='Sync only a specific order by ID',
        )
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Enable verbose debug output',
        )

    def handle(self, *args, **options):
        self.stdout.write("=" * 60)
        self.stdout.write("SHIPROCKET SYNC STARTED")
        self.stdout.write("=" * 60)
        
        self.stdout.write(f"Current time: {timezone.now()}")
        
        # Sync all orders that have a Shiprocket ID and are not delivered AND not cancelled
        if options['order_id']:
            orders = Order.objects.filter(order_id=options['order_id'])
            self.stdout.write(f"🔍 Filtering to specific order: {options['order_id']}")
        else:
            # Only sync orders that are still active (not delivered, not cancelled)
            orders = Order.objects.filter(
                shiprocket_order_id__isnull=False
            ).exclude(
                order_status='delivered'
            ).exclude(
                order_status='cancelled'
            )
        
        self.stdout.write(f"\n📊 Found {orders.count()} active orders to sync")
        
        if orders.count() == 0:
            self.stdout.write(self.style.WARNING("\n⚠️ No active orders found!"))
            return

        sr = ShiprocketService()
        self.stdout.write("\n🔄 Starting sync process...")

        success_count = 0
        error_count = 0
        skipped_count = 0
        status_updated_count = 0
        freight_updated_count = 0
        
        for order in orders:
            self.stdout.write(f"\n{'=' * 50}")
            self.stdout.write(f"Processing Order: {order.order_id}")
            self.stdout.write(f"  Current Status: {order.order_status}")
            self.stdout.write(f"  Shiprocket ID: {order.shiprocket_order_id}")
            
            if not order.shiprocket_order_id:
                self.stdout.write(self.style.WARNING(f"  ⚠️ No Shiprocket Order ID! Skipping..."))
                skipped_count += 1
                continue
            
            try:
                response = sr.get_order_by_shiprocket_id(order.shiprocket_order_id)
                
                if options['debug']:
                    self.stdout.write(f"  📄 API Response received")
                
                if not response:
                    self.stdout.write(self.style.WARNING(f"  ⚠️ No response from Shiprocket API"))
                    error_count += 1
                    continue
                
                if response.get("success") is False:
                    self.stdout.write(self.style.WARNING(f"  ⚠️ API returned error: {response.get('message', 'No message')}"))
                    error_count += 1
                    continue

                order_data = response.get("order", response.get("data", {}))
                
                if not order_data:
                    self.stdout.write(self.style.WARNING(f"  ⚠️ No order data in response"))
                    error_count += 1
                    continue

                # --- STEP 1: STATUS UPDATE ---
                sr_raw_status = order_data.get("status")
                self.stdout.write(f"  📍 Shiprocket Status: {sr_raw_status}")
                
                new_internal_status = map_shiprocket_status(sr_raw_status)
                self.stdout.write(f"  🔄 Mapped to internal status: {new_internal_status}")
                
                status_changed = False
                
                if new_internal_status and order.order_status != new_internal_status:
                    old_status = order.order_status
                    order.order_status = new_internal_status
                    status_updated_count += 1
                    status_changed = True
                    
                    if new_internal_status == 'delivered':
                        order.delivered_at = timezone.now()
                        self.stdout.write(self.style.SUCCESS(f"  ✅ Order DELIVERED at {order.delivered_at}"))
                    elif new_internal_status == 'cancelled':
                        self.stdout.write(self.style.SUCCESS(f"  ✅ Order CANCELLED"))
                    
                    self.stdout.write(self.style.SUCCESS(
                        f"  ✅ Status updated: {old_status} → {new_internal_status}"
                    ))
                else:
                    self.stdout.write(f"  ℹ️ No status change needed")

                # --- STEP 2: FREIGHT UPDATE (ONLY FOR DELIVERED ORDERS) ---
                # Only update shipping cost if order is delivered (final cost)
                # OR if we're just updating status to delivered
                update_freight = False
                
                if new_internal_status == 'delivered':
                    # Order is being marked as delivered now
                    update_freight = True
                    self.stdout.write(f"  📦 Order delivered - updating final shipping cost")
                elif order.order_status == 'delivered' and not order.actual_shipping_cost:
                    # Order was already delivered but no shipping cost recorded
                    update_freight = True
                    self.stdout.write(f"  📦 Order already delivered - updating missing shipping cost")
                else:
                    self.stdout.write(f"  ℹ️ Skipping freight update - order not delivered yet")
                
                if update_freight:
                    # Try to get freight charges from different locations
                    freight = None
                    
                    shipments = order_data.get("shipments", {})
                    
                    if isinstance(shipments, dict):
                        awb_data = shipments.get("awb_data", {})
                        charges = awb_data.get("charges", {})
                        freight = charges.get("freight_charges")
                        
                        if not freight:
                            freight = awb_data.get("freight_charges")
                            
                    elif isinstance(shipments, list) and len(shipments) > 0:
                        shipment = shipments[0]
                        awb_data = shipment.get("awb_data", {})
                        charges = awb_data.get("charges", {})
                        freight = charges.get("freight_charges")
                        
                        if not freight:
                            freight = awb_data.get("freight_charges")
                    
                    if not freight:
                        awb_data = order_data.get("awb_data", {})
                        charges = awb_data.get("charges", {})
                        freight = charges.get("freight_charges")
                    
                    self.stdout.write(f"  💰 Final freight charges from API: {freight}")
                    
                    if freight and float(freight) > 0:
                        old_freight = order.actual_shipping_cost
                        order.actual_shipping_cost = float(freight)
                        freight_updated_count += 1
                        self.stdout.write(f"  💰 Freight updated: {old_freight} → {order.actual_shipping_cost}")
                        
                        # Only recalculate settlement if order is delivered
                        if order.order_status == 'delivered':
                            self.stdout.write(f"  🔄 Recalculating settlement with final shipping cost...")
                            try:
                                DrapsoSettlementService.recalculate_after_shipping(order)
                                self.stdout.write(self.style.SUCCESS(f"  ✅ Settlement recalculated with final cost"))
                            except Exception as e:
                                self.stdout.write(self.style.WARNING(f"  ⚠️ Settlement recalculation error: {e}"))
                    else:
                        self.stdout.write(f"  ⚠️ No valid freight charge found for delivered order")
                else:
                    # For non-delivered orders, don't update freight
                    pass

                order.save()
                success_count += 1
                self.stdout.write(self.style.SUCCESS(f"  ✅ Order {order.order_id} synced successfully"))

            except Exception as e:
                error_type = e.__class__.__name__
                error_msg = str(e)
                logger.error(f"Sync error for {order.order_id}: {error_type} - {error_msg}")
                self.stdout.write(self.style.ERROR(
                    f"  ❌ ERROR on {order.order_id}: {error_type} - {error_msg}"
                ))
                error_count += 1
                
                if options['debug']:
                    import traceback
                    traceback.print_exc()

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("SYNC COMPLETE")
        self.stdout.write("=" * 60)
        self.stdout.write(f"✅ Success: {success_count} orders")
        self.stdout.write(f"🔄 Status updated: {status_updated_count} orders")
        self.stdout.write(f"💰 Freight updated: {freight_updated_count} orders")
        self.stdout.write(f"❌ Errors: {error_count} orders")
        self.stdout.write(f"⏭️ Skipped: {skipped_count} orders")
        self.stdout.write(f"📊 Total processed: {success_count + error_count + skipped_count} orders")