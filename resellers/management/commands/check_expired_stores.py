from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

from resellers.models import Store


class Command(BaseCommand):
    help = "Check store subscriptions and send expiry notifications"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would happen without making changes'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        now = timezone.now()

        stores = Store.objects.select_related('reseller', 'subscription_plan')

        for store in stores:
            # Skip lifetime plans
            if not store.subscription_end:
                continue

            days_left = (store.subscription_end - now).days

            # =========================
            # 1. EXPIRE STORE
            # =========================
            if store.subscription_end <= now and not store.expiry_notified_expired:
                
                if not dry_run:
                    store.status = 'expired'
                    store.is_published = False
                    store.expiry_notified_expired = True
                    store.save(update_fields=['status', 'is_published', 'expiry_notified_expired', 'updated_at'])

                    send_mail(
                        subject="⚠️ Your Store Has Expired",
                        message=f"""
Hi {store.reseller.first_name or store.reseller.username},

Your store "{store.store_name}" has expired.

⚠️ Your store is now unpublished and not visible to customers.

👉 Please login to your dashboard to renew your subscription and reactivate your store.

Regards,
Drapso Team
                        """,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[store.reseller.email, store.contact_email],
                        fail_silently=False,
                    )

                    self.stdout.write(f"Expired store: {store.store_name}")

            # =========================
            # 2. 7 DAYS REMINDER (between 5-10 days)
            # =========================
            elif 5 <= days_left <= 10 and not store.expiry_notified_7:
                
                if not dry_run:
                    store.expiry_notified_7 = True
                    store.save(update_fields=['expiry_notified_7', 'updated_at'])

                    send_mail(
                        subject="📅 7 Days Left - Renew Your Store",
                        message=f"""
Hi {store.reseller.first_name or store.reseller.username},

Your store "{store.store_name}" will expire in {days_left} days.

📅 Expiry Date: {store.subscription_end.strftime('%d %b %Y')}

👉 Please login to your dashboard to renew your subscription and avoid downtime.

Regards,
Drapso Team
                        """,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[store.reseller.email],
                        fail_silently=False,
                    )

                    self.stdout.write(f"7-day reminder sent: {store.store_name}")

            # =========================
            # 3. 3 DAYS REMINDER (between 1-4 days)
            # =========================
            elif 1 <= days_left <= 4 and not store.expiry_notified_3:
                
                if not dry_run:
                    store.expiry_notified_3 = True
                    store.save(update_fields=['expiry_notified_3', 'updated_at'])

                    send_mail(
                        subject="🚨 3 Days Left - Immediate Action Required",
                        message=f"""
Hi {store.reseller.first_name or store.reseller.username},

Only {days_left} days left for your store "{store.store_name}".

⚠️ Your store will be unpublished if not renewed.

👉 Login to your dashboard immediately to renew your subscription.

Regards,
Drapso Team
                        """,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[store.reseller.email],
                        fail_silently=False,
                    )

                    self.stdout.write(f"3-day reminder sent: {store.store_name}")

        self.stdout.write(self.style.SUCCESS("Subscription check completed"))