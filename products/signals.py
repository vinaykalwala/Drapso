from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from decimal import Decimal
from django.utils import timezone

from .models import (
    WholesellerProduct,
    WholesellerProductVariant,
    ResellerProduct,
    ResellerProductVariant,
    PriceChangeNotification
)

# ============ SIGNALS ============

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings

@receiver(post_save, sender=WholesellerProduct)
def notify_resellers_on_product_price_change(sender, instance, created, **kwargs):
    # Skip if this is a new product
    if created:
        return
    
    # Check if price or discount actually changed from wholeseller
    price_changed = getattr(instance, '_price_changed', False)
    discount_changed = getattr(instance, '_discount_changed', False)
    
    if not price_changed and not discount_changed:
        return
    
    # Get the old values
    old_price = getattr(instance, '_old_price', None)
    old_discount = getattr(instance, '_old_discount', None)
    
    if old_price is None:
        # If not tracked, try to get from database
        try:
            old_instance = WholesellerProduct.objects.get(pk=instance.pk)
            old_price = old_instance.price
            old_discount = old_instance.discount_percentage
        except WholesellerProduct.DoesNotExist:
            return
    
    # Calculate old and new effective prices
    old_effective = old_price
    if old_discount and old_discount > 0:
        old_discount_amount = (old_price * old_discount) / 100
        old_effective = old_price - old_discount_amount
    
    new_effective = instance.get_effective_price()
    
    # Only proceed if effective price changed significantly
    if abs(old_effective - new_effective) <= Decimal('0.01'):
        return
    
    reseller_products = ResellerProduct.objects.filter(
        source_product=instance,
        source_type='imported',
        is_active=True
    )
    
    for rp in reseller_products:
        old_selling = old_effective + rp.margin_rupees
        new_selling = new_effective + rp.margin_rupees
        
        diff = new_selling - old_selling
        is_increase = new_selling > old_selling
        
        notification_type = 'product_price_increase' if is_increase else 'product_price_decrease'
        
        # Prevent duplicate notifications (within last 5 minutes)
        recent_exists = PriceChangeNotification.objects.filter(
            reseller=rp.reseller,
            reseller_product=rp,
            created_at__gte=timezone.now() - timezone.timedelta(minutes=5)
        ).exists()
        
        if recent_exists:
            continue
        
        # Create message
        if is_increase:
            message = (
                f"⚠️ PRICE INCREASE from Wholeseller\n\n"
                f"Product: {instance.name}\n\n"
                f"Wholeseller Price: ₹{old_price} → ₹{instance.price}\n"
                f"Wholeseller Discount: {old_discount}% → {instance.discount_percentage}%\n"
                f"Your Margin: ₹{rp.margin_rupees}\n\n"
                f"Your Selling Price: ₹{old_selling} → ₹{new_selling}\n"
                f"Increase: +₹{diff}\n\n"
                f"👉 Visit your dashboard to review this price change."
            )
        else:
            message = (
                f"📉 PRICE DECREASE from Wholeseller 🎉\n\n"
                f"Product: {instance.name}\n\n"
                f"Wholeseller Price: ₹{old_price} → ₹{instance.price}\n"
                f"Wholeseller Discount: {old_discount}% → {instance.discount_percentage}%\n"
                f"Your Margin: ₹{rp.margin_rupees}\n\n"
                f"Your Selling Price: ₹{old_selling} → ₹{new_selling}\n"
                f"Decrease: ₹{abs(diff)}\n\n"
                f"👉 You can now reduce your selling price or increase your profit!"
            )
        
        PriceChangeNotification.objects.create(
            reseller=rp.reseller,
            store=rp.store,
            reseller_product=rp,
            notification_type=notification_type,
            old_price=old_price,
            new_price=instance.price,
            old_selling_price=old_selling,
            new_selling_price=new_selling,
            message=message,
        )
        
        # Update ResellerProduct price status
        rp.source_price = instance.price
        rp.last_known_source_price = old_effective
        rp.price_status = 'price_increased' if is_increase else 'price_decreased'
        rp.price_change_notified_at = timezone.now()
        rp.save(update_fields=['source_price', 'last_known_source_price', 'price_status', 'price_change_notified_at'])
        
        # Send email notification
        try:
            send_mail(
                subject=f"{'⚠️ Price Increased' if is_increase else '📉 Price Decreased'}: {instance.name}",
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[rp.reseller.email],
                fail_silently=True,
            )
        except Exception as e:
            print(f"Email failed: {e}")


@receiver(post_save, sender=WholesellerProductVariant)
def notify_resellers_on_variant_price_change(sender, instance, created, **kwargs):
    # Skip if new variant
    if created:
        return
    
    # Check if price or discount changed
    price_changed = getattr(instance, '_price_changed', False)
    discount_changed = getattr(instance, '_discount_changed', False)
    
    if not price_changed and not discount_changed:
        return
    
    # Get old values
    old_price = getattr(instance, '_old_price', None)
    old_discount = getattr(instance, '_old_discount', None)
    
    if old_price is None:
        try:
            old_instance = WholesellerProductVariant.objects.get(pk=instance.pk)
            old_price = old_instance.price
            old_discount = old_instance.discount_percentage
        except WholesellerProductVariant.DoesNotExist:
            return
    
    # Calculate effective prices
    old_effective = old_price
    if old_discount and old_discount > 0:
        old_discount_amount = (old_price * old_discount) / 100
        old_effective = old_price - old_discount_amount
    
    new_effective = instance.get_effective_price()
    
    # Skip if no significant change
    if abs(old_effective - new_effective) <= Decimal('0.01'):
        return
    
    reseller_variants = ResellerProductVariant.objects.filter(
        source_variant=instance,
        is_active=True
    )
    
    for rv in reseller_variants:
        rp = rv.product
        
        old_selling = old_effective + rv.margin_rupees
        new_selling = new_effective + rv.margin_rupees
        
        is_increase = new_selling > old_selling
        notification_type = 'variant_price_increase' if is_increase else 'variant_price_decrease'
        
        # Prevent duplicate
        recent_exists = PriceChangeNotification.objects.filter(
            reseller=rp.reseller,
            reseller_variant=rv,
            created_at__gte=timezone.now() - timezone.timedelta(minutes=5)
        ).exists()
        
        if recent_exists:
            continue
        
        if is_increase:
            message = (
                f"⚠️ VARIANT PRICE INCREASE from Wholeseller\n\n"
                f"Product: {rp.name} - {rv.variant_name}\n\n"
                f"Wholeseller Price: ₹{old_price} → ₹{instance.price}\n"
                f"Wholeseller Discount: {old_discount}% → {instance.discount_percentage}%\n"
                f"Your Margin: ₹{rv.margin_rupees}\n\n"
                f"Your Selling Price: ₹{old_selling} → ₹{new_selling}\n"
                f"Increase: +₹{new_selling - old_selling}\n\n"
                f"👉 Visit your dashboard to review this price change."
            )
        else:
            message = (
                f"📉 VARIANT PRICE DECREASE from Wholeseller 🎉\n\n"
                f"Product: {rp.name} - {rv.variant_name}\n\n"
                f"Wholeseller Price: ₹{old_price} → ₹{instance.price}\n"
                f"Wholeseller Discount: {old_discount}% → {instance.discount_percentage}%\n"
                f"Your Margin: ₹{rv.margin_rupees}\n\n"
                f"Your Selling Price: ₹{old_selling} → ₹{new_selling}\n"
                f"Decrease: ₹{old_selling - new_selling}\n\n"
                f"👉 You can now reduce your selling price or increase your profit!"
            )
        
        PriceChangeNotification.objects.create(
            reseller=rp.reseller,
            store=rp.store,
            reseller_product=rp,
            reseller_variant=rv,
            notification_type=notification_type,
            old_price=old_price,
            new_price=instance.price,
            old_selling_price=old_selling,
            new_selling_price=new_selling,
            message=message,
        )
        
        # Send email
        try:
            send_mail(
                subject=f"{'⚠️ Price Increased' if is_increase else '📉 Price Decreased'}: {rp.name} - {rv.variant_name}",
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[rp.reseller.email],
                fail_silently=True,
            )
        except Exception as e:
            print(f"Email failed: {e}")