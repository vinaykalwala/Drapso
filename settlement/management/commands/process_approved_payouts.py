from django.core.management.base import BaseCommand
from settlement.services import WithdrawalService
from django.conf import settings
from settlement.models import WithdrawalRequest

class Command(BaseCommand):
    help = 'Process approved withdrawal requests and send payouts via RazorpayX'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--test-mode',
            action='store_true',
            help='Run in test mode (mock payouts without real API calls)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without making actual API calls'
        )
        parser.add_argument(
            '--withdrawal-id',
            type=str,
            help='Process only a specific withdrawal ID'
        )
    
    def handle(self, *args, **options):
        test_mode = options.get('test_mode', False)
        dry_run = options.get('dry_run', False)
        specific_id = options.get('withdrawal_id')
        
        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  DRY RUN MODE - No actual payouts will be processed"))
        
        if test_mode:
            self.stdout.write(self.style.WARNING("🧪 TEST MODE - Mock payouts only"))
        
        if specific_id:
            self.stdout.write(f"🎯 Processing only withdrawal: {specific_id}")
        
        # Get withdrawals to process
        if specific_id:
            withdrawals = WithdrawalRequest.objects.filter(
                status='APPROVED', 
                id=specific_id
            )
            if not withdrawals.exists():
                self.stdout.write(self.style.ERROR(f"❌ Withdrawal {specific_id} not found or not in APPROVED status"))
                return
        else:
            withdrawals = WithdrawalRequest.objects.filter(status='APPROVED')
        
        if dry_run:
            count = withdrawals.count()
            if count > 0:
                self.stdout.write(f"\n📊 Found {count} withdrawal(s) to process")
                self.stdout.write("\n📝 Details:")
                self.stdout.write("-" * 70)
                for withdrawal in withdrawals:
                    self.stdout.write(f"\n   ID: {withdrawal.id}")
                    self.stdout.write(f"   Amount: ₹{withdrawal.amount}")
                    self.stdout.write(f"   Account: {withdrawal.account_number}")
                    self.stdout.write(f"   IFSC: {withdrawal.ifsc_code}")
                    self.stdout.write(f"   Holder: {withdrawal.account_holder_name}")
                self.stdout.write("\n" + "-" * 70)
            else:
                self.stdout.write(self.style.WARNING("\n⚠️  No approved withdrawals found"))
            return
        
        # Process actual payouts
        try:
            results = WithdrawalService.process_approved_payouts(test_mode=test_mode)
            
            if not results:
                
                return
            
            if isinstance(results, dict) and results.get('error'):
                
                return
            
            # Display results
            self.stdout.write("\n📊 Results:")
            self.stdout.write("-" * 70)
            
            success_count = 0
            failed_count = 0
            skipped_count = 0
            
            for item in results:
                wid = item['withdrawal_id']
                
                if item['status'] in ['processing', 'completed']:
                    success_count += 1
                    mode_text = f" ({item.get('mode', 'live')})" if item.get('mode') else ""
                    payout_text = f" Payout ID: {item.get('payout_id')}" if item.get('payout_id') else ""
                    self.stdout.write(
                        self.style.SUCCESS(f"  ✓ {wid} - {item['status'].upper()}{mode_text}{payout_text}")
                    )
                
                elif item['status'] == 'skipped':
                    skipped_count += 1
                    self.stdout.write(
                        self.style.WARNING(f"  ⏭️  {wid} - Skipped: {item.get('reason', 'Unknown')}")
                    )
                
                else:
                    failed_count += 1
                    error_msg = item.get('error', 'Unknown error')
                    self.stdout.write(self.style.ERROR(f"  ✗ {wid} - FAILED"))
                    self.stdout.write(f"      Error: {error_msg}")
                    if item.get('amount'):
                        self.stdout.write(f"      Amount: ₹{item['amount']}")
                        self.stdout.write(f"      Account: {item.get('account', 'N/A')}")
                        self.stdout.write(f"      IFSC: {item.get('ifsc', 'N/A')}")
            
            # Summary
            self.stdout.write("\n" + "=" * 70)
            self.stdout.write("📈 Summary:")
            self.stdout.write(f"   ✅ Success: {success_count}")
            self.stdout.write(f"   ❌ Failed: {failed_count}")
            self.stdout.write(f"   ⏭️  Skipped: {skipped_count}")
            self.stdout.write(f"   📊 Total: {len(results)}")
            self.stdout.write("=" * 70)
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Fatal error: {str(e)}"))