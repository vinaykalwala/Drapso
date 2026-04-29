from django.core.management.base import BaseCommand
from settlement.services import DrapsoSettlementService
from orders.models import Order

class Command(BaseCommand):
    help = 'Release eligible order settlements from escrow to wallets'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be released without actually releasing',
        )
    
    def handle(self, *args, **options):
        
        
        if options['dry_run']:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made\n"))
            
            # select_related minimizes DB queries during the loop
            orders = Order.objects.filter(
                order_status='delivered', 
                settlement__status='IN_ESCROW'
            ).select_related('wholeseller', 'reseller')
            
            eligible_count = 0
            for order in orders:
                is_eligible, reason = DrapsoSettlementService.is_order_eligible_for_release(order)
                if is_eligible:
                    eligible_count += 1
                    self.stdout.write(self.style.SUCCESS(f"  ✓ {order.order_id} - Eligible"))
                else:
                    self.stdout.write(self.style.WARNING(f"  ⏳ {order.order_id} - {reason}"))
            
            self.stdout.write(f"\nTotal Eligible: {eligible_count}")
        
        else:
            # Call the updated service method
            result = DrapsoSettlementService.release_eligible_settlements()
            
            
            pending_count = result['total_processed'] - result['released_count'] - result['failed_count']
            
            # Detailed breakdown
            for res in result['results']:
                if res['status'] == 'released':
                    self.stdout.write(self.style.SUCCESS(f"  ✓ {res['order_id']} - Released"))
                elif res['status'] == 'failed':
                    self.stdout.write(self.style.ERROR(f"  ✗ {res['order_id']} - Failed: {res['error']}"))
                elif res['status'] == 'pending':
                    self.stdout.write(self.style.WARNING(f"  ⏳ {res['order_id']} - {res['reason']}"))
        
        