# resellers/management/commands/check_expired_stores.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from resellers.models import Store

class Command(BaseCommand):
    help = 'Check for expired subscriptions and send notifications'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would happen without making changes'
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        self.stdout.write(f"🔍 Checking expired subscriptions at {timezone.now()}")
        
        # 1. Find and process expired stores
        expired_stores = Store.objects.filter(
            status='active',
            subscription_end__isnull=False,
            subscription_end__lte=timezone.now()
        )
        
        self.stdout.write(f"\n📊 Found {expired_stores.count()} expired stores")
        
        for store in expired_stores:
            if not dry_run:
                # Update store status
                old_status = store.status
                store.status = 'expired'
                store.is_published = False
                store.save()
                
                self.stdout.write(f"  ✓ Expired: {store.store_name} (was {old_status})")
                
                # Send expiration email
                self._send_expiration_email(store)
            else:
                self.stdout.write(f"  • Would expire: {store.store_name}")
        
        # 2. Find stores expiring in 7 days (for reminders)
        from datetime import timedelta
        expiring_soon = Store.objects.filter(
            status='active',
            subscription_end__isnull=False,
            subscription_end__gt=timezone.now(),
            subscription_end__lte=timezone.now() + timedelta(days=7)
        )
        
        self.stdout.write(f"\n📧 Found {expiring_soon.count()} stores expiring within 7 days")
        
        for store in expiring_soon:
            days_left = (store.subscription_end - timezone.now()).days
            
            if not dry_run:
                self._send_expiry_reminder(store, days_left)
                self.stdout.write(f"  ✓ Reminder sent to: {store.store_name} ({days_left} days left)")
            else:
                self.stdout.write(f"  • Would remind: {store.store_name} ({days_left} days left)")
        
        self.stdout.write(self.style.SUCCESS(f"\n✅ Subscription check completed!"))
        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  This was a DRY RUN - no changes were made"))
    
    def _send_expiration_email(self, store):
        """Send email when store expires"""
        try:
            renewal_url = f"https://yourdomain.com/resellers/manage-subscription/{store.id}/"
            
            subject = f"⚠️ Your Store '{store.store_name}' Has Expired"
            message = f"""
Dear Store Owner,

Your store "{store.store_name}" has expired on {store.subscription_end.strftime('%B %d, %Y')}.

Your store has been unpublished and is no longer visible to customers.

🔴 To reactivate your store and restore all your products:
👉 {renewal_url}

✅ What happens when you renew:
• All your products will be restored immediately
• Your store theme and settings remain intact
• Your store URL stays the same
• Your customers can access your store again

If you have any questions, please contact our support team.

Best regards,
Your Platform Team
"""
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[store.contact_email, store.reseller.email],
                fail_silently=False,
            )
        except Exception as e:
            self.stdout.write(f"  ⚠️ Failed to send email to {store.store_name}: {e}")
    
    def _send_expiry_reminder(self, store, days_left):
        """Send reminder email before expiry"""
        try:
            renewal_url = f"https://yourdomain.com/resellers/manage-subscription/{store.id}/"
            
            subject = f"📅 Your Store '{store.store_name}' Expires in {days_left} Days"
            message = f"""
Dear Store Owner,

Your store "{store.store_name}" subscription will expire in {days_left} days on {store.subscription_end.strftime('%B %d, %Y')}.

🟡 To avoid service interruption, please renew now:
👉 {renewal_url}

💡 Benefits of renewing early:
• No interruption to your store
• Keep all your products and settings
• Continue serving your customers

Don't let your store go offline!

Best regards,
Your Platform Team
"""
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[store.contact_email, store.reseller.email],
                fail_silently=False,
            )
        except Exception as e:
            self.stdout.write(f"  ⚠️ Failed to send reminder to {store.store_name}: {e}")