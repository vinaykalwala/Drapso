from django.db.models.signals import post_save
from django.dispatch import receiver
from orders.models import Order
from .services import DrapsoSettlementService

@receiver(post_save, sender=Order)
def handle_order_settlement(sender, instance, created, **kwargs):
    """Handle settlement when order becomes paid"""
    
    # Process settlement when order is paid
    if instance.order_status == 'paid' and instance.payment_status == 'success':
        if not hasattr(instance, 'settlement'):
            DrapsoSettlementService.process_order_payment(instance)
    
    # Update settlement when shipping cost is known
    elif instance.actual_shipping_cost and hasattr(instance, 'settlement'):
        if instance.settlement.status == 'IN_ESCROW':
            DrapsoSettlementService.recalculate_after_shipping(instance)
    
    # Cancel settlement when order is cancelled
    elif instance.order_status == 'cancelled' and hasattr(instance, 'settlement'):
        if instance.settlement.status == 'IN_ESCROW':
            instance.settlement.cancel()