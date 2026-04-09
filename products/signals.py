# products/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

from .models import WholesellerProduct, ResellerProduct, PriceChangeNotification


@receiver(post_save, sender=WholesellerProduct)
def notify_resellers_on_price_change(sender, instance, created, **kwargs):
    """When wholeseller updates price, notify all resellers who imported this product"""
    
    if not created and instance.has_price_changed():
        reseller_products = ResellerProduct.objects.filter(
            source_product=instance,
            source_type='imported',
            is_active=True
        )
        
        for reseller_product in reseller_products:
            old_selling_price = reseller_product.selling_price
            new_selling_price = instance.price + reseller_product.margin_rupees
            
            if instance.is_price_increased():
                notification_type = 'product_price_increase'
                message = f"""
⚠️ PRICE INCREASE ALERT

Product: {instance.name}
Store: {reseller_product.store.store_name}

The wholeseller has increased the price:
• Old Wholeseller Price: ₹{instance.previous_price}
• New Wholeseller Price: ₹{instance.price}
• Your Margin: ₹{reseller_product.margin_rupees}

Impact on your store:
• Old Selling Price: ₹{old_selling_price}
• New Selling Price (if updated): ₹{new_selling_price}
• Difference: +₹{new_selling_price - old_selling_price}

Action Required:
Please review and decide whether to update your store price.
                """
            else:
                notification_type = 'product_price_decrease'
                message = f"""
📉 PRICE DECREASE ALERT

Product: {instance.name}
Store: {reseller_product.store.store_name}

The wholeseller has decreased the price:
• Old Wholeseller Price: ₹{instance.previous_price}
• New Wholeseller Price: ₹{instance.price}
• Your Margin: ₹{reseller_product.margin_rupees}

Impact on your store:
• Old Selling Price: ₹{old_selling_price}
• New Selling Price (if updated): ₹{new_selling_price}
• Difference: {new_selling_price - old_selling_price}₹

Action Required:
You can now offer a lower price to customers or keep higher profit margin.
                """
            
            PriceChangeNotification.objects.create(
                reseller=reseller_product.reseller,
                store=reseller_product.store,
                reseller_product=reseller_product,
                notification_type=notification_type,
                old_price=instance.previous_price,
                new_price=instance.price,
                old_selling_price=old_selling_price,
                new_selling_price=new_selling_price,
                message=message,
                is_read=False,
                is_actioned=False
            )
            
            try:
                send_mail(
                    subject=f'{"⚠️ Price Increased" if instance.is_price_increased() else "📉 Price Decreased"}: {instance.name}',
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[reseller_product.reseller.email, reseller_product.store.contact_email],
                    fail_silently=True,
                )
            except Exception as e:
                print(f"Email failed: {e}")