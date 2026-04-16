# orders/management/commands/setup_shiprocket_webhook.py
from django.core.management.base import BaseCommand
from django.conf import settings
from shiprocket.services import ShiprocketService

class Command(BaseCommand):
    help = 'Setup Shiprocket webhook for automatic status updates'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--webhook-url',
            type=str,
            help='Webhook URL (default: SITE_URL + /orders/webhook/shiprocket/)'
        )
    
    def handle(self, *args, **options):
        webhook_url = options.get('webhook_url')
        
        if not webhook_url:
            site_url = getattr(settings, 'SITE_URL', 'https://yourdomain.com')
            webhook_url = f"{site_url}/orders/webhook/shiprocket/"
        
        self.stdout.write(f"Setting up webhook at: {webhook_url}")
        
        shiprocket = ShiprocketService()
        
        existing = shiprocket.get_webhooks()
        if existing and existing.get('data'):
            self.stdout.write("Existing webhooks found:")
            for webhook in existing['data']:
                self.stdout.write(f"  - {webhook.get('webhook_url')} (ID: {webhook.get('id')})")
        
        result = shiprocket.register_webhook(webhook_url)
        
        if result:
            self.stdout.write(self.style.SUCCESS(f"Webhook registered successfully: {result}"))
        else:
            self.stdout.write(self.style.ERROR("Failed to register webhook"))