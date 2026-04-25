from django.core.management.base import BaseCommand
from settlement.services import WithdrawalService

class Command(BaseCommand):
    help = 'Process approved withdrawal requests and send NEFT payouts via RazorpayX'
    
    def handle(self, *args, **options):
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.MIGRATE_HEADING("Processing Approved Withdrawals (NEFT)"))
        self.stdout.write("=" * 60)
        
        results = WithdrawalService.process_approved_payouts()
        
        if not results:
            self.stdout.write(self.style.WARNING("No 'APPROVED' withdrawal requests found."))
            return

        completed = [r for r in results if r['status'] == 'completed']
        failed = [r for r in results if r['status'] == 'failed']
        
        self.stdout.write(f"\n✅ Completed: {len(completed)} payouts")
        self.stdout.write(f"❌ Failed: {len(failed)} payouts")
        
        for item in results:
            if item['status'] == 'completed':
                self.stdout.write(self.style.SUCCESS(
                    f"  ✓ {item['withdrawal_id']} - NEFT Sent (Fee: ₹{item.get('fee_paid', 0)})"
                ))
            else:
                self.stdout.write(self.style.ERROR(
                    f"  ✗ {item['withdrawal_id']} - Failed: {item['error']}"
                ))
        
        self.stdout.write("\n" + "=" * 60)