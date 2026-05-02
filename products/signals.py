# products/signals.py
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from decimal import Decimal
from django.utils import timezone
from django.db.models import Q

from .models import (
    WholesellerProduct,
    WholesellerProductVariant,
    ResellerProduct,
    ResellerProductVariant,
    PriceChangeNotification
)

# ============ PRE-SAVE SIGNAL TO TRACK OLD DISCOUNTED PRICE ============

@receiver(pre_save, sender=WholesellerProduct)
def track_old_wholeseller_product_discounted_price(sender, instance, **kwargs):
    """Track old discounted price before save"""
    if instance.pk:
        try:
            old_instance = WholesellerProduct.objects.get(pk=instance.pk)
            old_discounted = old_instance.discounted_price or old_instance.calculate_discounted_price()
            instance._old_discounted_price = old_discounted
            instance._old_price = old_instance.price
            instance._old_discount = old_instance.discount_percentage
        except WholesellerProduct.DoesNotExist:
            instance._old_discounted_price = None
    else:
        instance._old_discounted_price = None


@receiver(pre_save, sender=WholesellerProductVariant)
def track_old_wholeseller_variant_discounted_price(sender, instance, **kwargs):
    """Track old discounted price before save"""
    if instance.pk:
        try:
            old_instance = WholesellerProductVariant.objects.get(pk=instance.pk)
            old_discounted = old_instance.discounted_price or old_instance.calculate_discounted_price()
            instance._old_discounted_price = old_discounted
            instance._old_price = old_instance.price
            instance._old_discount = old_instance.discount_percentage
        except WholesellerProductVariant.DoesNotExist:
            instance._old_discounted_price = None
    else:
        instance._old_discounted_price = None


# ============ POST-SAVE SIGNAL FOR WHOLESELLER PRODUCT ============

@receiver(post_save, sender=WholesellerProduct)
def notify_resellers_on_product_price_change(sender, instance, created, **kwargs):
    """
    Send notification to resellers when wholeseller product discounted price changes
    But DO NOT update the reseller product prices automatically
    """
    # Skip if this is a new product
    if created:
        return
    
    # Skip if we're already processing to prevent recursion
    if hasattr(instance, '_price_change_processing'):
        return
    
    # Get old discounted price (tracked in pre_save)
    old_discounted = getattr(instance, '_old_discounted_price', None)
    
    # If not tracked, calculate from old instance
    if old_discounted is None and instance.pk:
        try:
            old_instance = WholesellerProduct.objects.get(pk=instance.pk)
            old_discounted = old_instance.discounted_price or old_instance.calculate_discounted_price()
            old_price = old_instance.price
            old_discount = old_instance.discount_percentage
        except WholesellerProduct.DoesNotExist:
            return
    else:
        old_price = getattr(instance, '_old_price', None)
        old_discount = getattr(instance, '_old_discount', None)
    
    # Calculate new discounted price
    new_discounted = instance.discounted_price or instance.calculate_discounted_price()
    
    # Only proceed if discounted price changed significantly
    if old_discounted is None or abs(old_discounted - new_discounted) <= Decimal('0.01'):
        return
    
    print(f"📢 Price change detected for product {instance.id}: ₹{old_discounted} → ₹{new_discounted}")
    
    # Set flag to prevent recursion
    instance._price_change_processing = True
    
    try:
        # Get all reseller products linked to this wholeseller product
        reseller_products = ResellerProduct.objects.filter(
            source_product=instance,
            source_type='imported',
            is_active=True
        ).select_related('reseller', 'store')
        
        print(f"📢 Found {reseller_products.count()} reseller products to notify")
        
        for rp in reseller_products:
            # Calculate old and new selling prices for reseller
            old_selling = old_discounted + rp.margin_rupees
            new_selling = new_discounted + rp.margin_rupees
            
            diff = new_selling - old_selling
            is_increase = new_selling > old_selling
            
            notification_type = 'product_price_increase' if is_increase else 'product_price_decrease'
            
            # FIXED: Check for duplicate notification with SAME price change only
            # Allow new notifications if price changed again
            recent_duplicate = PriceChangeNotification.objects.filter(
                reseller=rp.reseller,
                reseller_product=rp,
                notification_type=notification_type,
                old_price=old_discounted,  # Same old price
                new_price=new_discounted,   # Same new price
                created_at__gte=timezone.now() - timezone.timedelta(minutes=5)
            ).exists()
            
            # Also check if there's an unactioned notification for this product
            # If yes, update it instead of creating new one
            existing_unactioned = PriceChangeNotification.objects.filter(
                reseller=rp.reseller,
                reseller_product=rp,
                is_actioned=False
            ).order_by('-created_at').first()
            
            if recent_duplicate:
                print(f"📢 Skipping duplicate notification for {rp.name} (same price change already notified)")
                continue
            
            # If there's an unactioned notification, update it instead of creating new
            if existing_unactioned:
                print(f"📢 Updating existing unactioned notification {existing_unactioned.id} for {rp.name}")
                existing_unactioned.old_price = old_discounted
                existing_unactioned.new_price = new_discounted
                existing_unactioned.old_selling_price = old_selling
                existing_unactioned.new_selling_price = new_selling
                existing_unactioned.notification_type = notification_type
                
                # Update message
                if is_increase:
                    message = (
                        f"⚠️ PRICE INCREASE from Wholeseller (UPDATED)\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"📦 Product: {instance.name}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"💰 Wholeseller Price Change:\n"
                        f"   • Original Price: ₹{old_price} → ₹{instance.price}\n"
                        f"   • Discount: {old_discount or 0}% → {instance.discount_percentage}%\n"
                        f"   • Your Cost (after discount): ₹{old_discounted} → ₹{new_discounted}\n\n"
                        f"💼 Your Margin: ₹{rp.margin_rupees}\n\n"
                        f"💵 Your Current Selling Price: ₹{rp.selling_price}\n"
                        f"💰 New Proposed Selling Price: ₹{new_selling}\n"
                        f"📈 Increase: +₹{diff}\n\n"
                        f"⚠️ Your price has NOT been updated automatically.\n"
                        f"👉 Action Required: Review and sync this price change from your dashboard.\n\n"
                        f"🔗 Review here: /products/reseller/store/{rp.store.id}/price-notifications/"
                    )
                else:
                    message = (
                        f"📉 PRICE DECREASE from Wholeseller (UPDATED) 🎉\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"📦 Product: {instance.name}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"💰 Wholeseller Price Change:\n"
                        f"   • Original Price: ₹{old_price} → ₹{instance.price}\n"
                        f"   • Discount: {old_discount or 0}% → {instance.discount_percentage}%\n"
                        f"   • Your Cost (after discount): ₹{old_discounted} → ₹{new_discounted}\n\n"
                        f"💼 Your Margin: ₹{rp.margin_rupees} (unchanged)\n\n"
                        f"💵 Your Current Selling Price: ₹{rp.selling_price}\n"
                        f"💰 New Proposed Selling Price: ₹{new_selling}\n"
                        f"📉 Decrease: -₹{abs(diff)}\n\n"
                        f"🎯 Opportunity: You can now reduce price or increase profit margin!\n\n"
                        f"👉 Review and sync this price change from your dashboard.\n\n"
                        f"🔗 Review here: /products/reseller/store/{rp.store.id}/price-notifications/"
                    )
                
                existing_unactioned.message = message
                existing_unactioned.created_at = timezone.now()  # Refresh timestamp
                existing_unactioned.save()
                
                # Send email for updated notification
                try:
                    send_mail(
                        subject=f"{'⚠️ Price Increase Alert (UPDATED)' if is_increase else '📉 Price Decrease Opportunity (UPDATED)'}: {instance.name}",
                        message=message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[rp.reseller.email],
                        fail_silently=False,
                    )
                    print(f"📧 Updated email sent to {rp.reseller.email}")
                except Exception as e:
                    print(f"❌ Email failed for {rp.reseller.email}: {e}")
                
            else:
                # Create new notification
                if is_increase:
                    message = (
                        f"⚠️ PRICE INCREASE from Wholeseller\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"📦 Product: {instance.name}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"💰 Wholeseller Price Change:\n"
                        f"   • Original Price: ₹{old_price} → ₹{instance.price}\n"
                        f"   • Discount: {old_discount or 0}% → {instance.discount_percentage}%\n"
                        f"   • Your Cost (after discount): ₹{old_discounted} → ₹{new_discounted}\n\n"
                        f"💼 Your Margin: ₹{rp.margin_rupees}\n\n"
                        f"💵 Your Current Selling Price: ₹{rp.selling_price}\n"
                        f"💰 New Proposed Selling Price: ₹{new_selling}\n"
                        f"📈 Increase: +₹{diff}\n\n"
                        f"⚠️ Your price has NOT been updated automatically.\n"
                        f"👉 Action Required: Review and sync this price change from your dashboard.\n\n"
                        f"🔗 Review here: /products/reseller/store/{rp.store.id}/price-notifications/"
                    )
                else:
                    message = (
                        f"📉 PRICE DECREASE from Wholeseller 🎉\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"📦 Product: {instance.name}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"💰 Wholeseller Price Change:\n"
                        f"   • Original Price: ₹{old_price} → ₹{instance.price}\n"
                        f"   • Discount: {old_discount or 0}% → {instance.discount_percentage}%\n"
                        f"   • Your Cost (after discount): ₹{old_discounted} → ₹{new_discounted}\n\n"
                        f"💼 Your Margin: ₹{rp.margin_rupees} (unchanged)\n\n"
                        f"💵 Your Current Selling Price: ₹{rp.selling_price}\n"
                        f"💰 New Proposed Selling Price: ₹{new_selling}\n"
                        f"📉 Decrease: -₹{abs(diff)}\n\n"
                        f"🎯 Opportunity: You can now:\n"
                        f"   • Sync price to reduce selling price and attract more customers, OR\n"
                        f"   • Keep current price and increase your profit margin by ₹{abs(diff)} per unit!\n\n"
                        f"👉 Review and sync this price change from your dashboard.\n\n"
                        f"🔗 Review here: /products/reseller/store/{rp.store.id}/price-notifications/"
                    )
                
                # Create notification ONLY - DO NOT update the reseller product
                notification = PriceChangeNotification.objects.create(
                    reseller=rp.reseller,
                    store=rp.store,
                    reseller_product=rp,
                    notification_type=notification_type,
                    old_price=old_discounted,
                    new_price=new_discounted,
                    old_selling_price=old_selling,
                    new_selling_price=new_selling,
                    message=message,
                )
                
                print(f"📢 Created notification {notification.id} for reseller {rp.reseller.email}")
                print(f"   ⚠️ Reseller product {rp.name} price NOT updated - pending review")
                
                # Send email notification
                try:
                    send_mail(
                        subject=f"{'⚠️ Price Increase Alert' if is_increase else '📉 Price Decrease Opportunity'}: {instance.name}",
                        message=message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[rp.reseller.email],
                        fail_silently=False,
                    )
                    print(f"📧 Email sent to {rp.reseller.email}")
                except Exception as e:
                    print(f"❌ Email failed for {rp.reseller.email}: {e}")
            
            # Update ONLY the price_status and notification time
            ResellerProduct.objects.filter(pk=rp.pk).update(
                price_status='price_increased' if is_increase else 'price_decreased',
                price_change_notified_at=timezone.now()
            )
    
    except Exception as e:
        print(f"❌ Error in signal: {e}")
    
    finally:
        # Always clear the flag
        if hasattr(instance, '_price_change_processing'):
            delattr(instance, '_price_change_processing')


# ============ POST-SAVE SIGNAL FOR WHOLESELLER VARIANT ============

@receiver(post_save, sender=WholesellerProductVariant)
def notify_resellers_on_variant_price_change(sender, instance, created, **kwargs):
    """
    Send notification to resellers when wholeseller variant discounted price changes
    But DO NOT update the reseller variant prices automatically
    """
    # Skip if new variant
    if created:
        return
    
    # Skip if we're already processing to prevent recursion
    if hasattr(instance, '_price_change_processing'):
        return
    
    # Get old discounted price
    old_discounted = getattr(instance, '_old_discounted_price', None)
    
    # If not tracked, calculate from old instance
    if old_discounted is None and instance.pk:
        try:
            old_instance = WholesellerProductVariant.objects.get(pk=instance.pk)
            old_discounted = old_instance.discounted_price or old_instance.calculate_discounted_price()
            old_price = old_instance.price
            old_discount = old_instance.discount_percentage
        except WholesellerProductVariant.DoesNotExist:
            return
    else:
        old_price = getattr(instance, '_old_price', None)
        old_discount = getattr(instance, '_old_discount', None)
    
    # Calculate new discounted price
    new_discounted = instance.discounted_price or instance.calculate_discounted_price()
    
    # Skip if no significant change
    if old_discounted is None or abs(old_discounted - new_discounted) <= Decimal('0.01'):
        return
    
    print(f"📢 Variant price change detected for variant {instance.id}: ₹{old_discounted} → ₹{new_discounted}")
    
    # Set flag to prevent recursion
    instance._price_change_processing = True
    
    try:
        # Get all reseller variants linked to this wholeseller variant
        reseller_variants = ResellerProductVariant.objects.filter(
            source_variant=instance,
            is_active=True
        ).select_related('product', 'product__reseller', 'product__store')
        
        print(f"📢 Found {reseller_variants.count()} reseller variants to notify")
        
        for rv in reseller_variants:
            rp = rv.product
            
            # Calculate old and new selling prices
            old_selling = old_discounted + rv.margin_rupees
            new_selling = new_discounted + rv.margin_rupees
            
            is_increase = new_selling > old_selling
            notification_type = 'variant_price_increase' if is_increase else 'variant_price_decrease'
            
            # FIXED: Check for duplicate with SAME price change
            recent_duplicate = PriceChangeNotification.objects.filter(
                reseller=rp.reseller,
                reseller_variant=rv,
                notification_type=notification_type,
                old_price=old_discounted,
                new_price=new_discounted,
                created_at__gte=timezone.now() - timezone.timedelta(minutes=5)
            ).exists()
            
            # Check for existing unactioned notification
            existing_unactioned = PriceChangeNotification.objects.filter(
                reseller=rp.reseller,
                reseller_variant=rv,
                is_actioned=False
            ).order_by('-created_at').first()
            
            if recent_duplicate:
                print(f"📢 Skipping duplicate notification for variant {rv.variant_name}")
                continue
            
            if existing_unactioned:
                # Update existing notification
                print(f"📢 Updating existing unactioned notification for variant {rv.variant_name}")
                existing_unactioned.old_price = old_discounted
                existing_unactioned.new_price = new_discounted
                existing_unactioned.old_selling_price = old_selling
                existing_unactioned.new_selling_price = new_selling
                existing_unactioned.notification_type = notification_type
                
                if is_increase:
                    message = (
                        f"⚠️ VARIANT PRICE INCREASE from Wholeseller (UPDATED)\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"📦 Product: {rp.name}\n"
                        f"🔖 Variant: {rv.variant_name}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"💰 Wholeseller Price Change:\n"
                        f"   • Original Price: ₹{old_price} → ₹{instance.price}\n"
                        f"   • Discount: {old_discount or 0}% → {instance.discount_percentage}%\n"
                        f"   • Your Cost (after discount): ₹{old_discounted} → ₹{new_discounted}\n\n"
                        f"💼 Your Margin: ₹{rv.margin_rupees}\n\n"
                        f"💵 Your Current Selling Price: ₹{rv.selling_price}\n"
                        f"💰 New Proposed Selling Price: ₹{new_selling}\n"
                        f"📈 Increase: +₹{new_selling - old_selling}\n\n"
                        f"⚠️ Your price has NOT been updated automatically.\n"
                        f"👉 Action Required: Review and sync this price change from your dashboard.\n\n"
                        f"🔗 Review here: /products/reseller/store/{rp.store.id}/price-notifications/"
                    )
                else:
                    message = (
                        f"📉 VARIANT PRICE DECREASE from Wholeseller (UPDATED) 🎉\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"📦 Product: {rp.name}\n"
                        f"🔖 Variant: {rv.variant_name}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"💰 Wholeseller Price Change:\n"
                        f"   • Original Price: ₹{old_price} → ₹{instance.price}\n"
                        f"   • Discount: {old_discount or 0}% → {instance.discount_percentage}%\n"
                        f"   • Your Cost (after discount): ₹{old_discounted} → ₹{new_discounted}\n\n"
                        f"💼 Your Margin: ₹{rv.margin_rupees} (unchanged)\n\n"
                        f"💵 Your Current Selling Price: ₹{rv.selling_price}\n"
                        f"💰 New Proposed Selling Price: ₹{new_selling}\n"
                        f"📉 Decrease: -₹{old_selling - new_selling}\n\n"
                        f"🎯 Opportunity: You can now reduce price or increase profit margin!\n\n"
                        f"👉 Review and sync this price change from your dashboard.\n\n"
                        f"🔗 Review here: /products/reseller/store/{rp.store.id}/price-notifications/"
                    )
                
                existing_unactioned.message = message
                existing_unactioned.created_at = timezone.now()
                existing_unactioned.save()
                
                # Send email
                try:
                    send_mail(
                        subject=f"{'⚠️ Price Increase Alert (UPDATED)' if is_increase else '📉 Price Decrease Opportunity (UPDATED)'}: {rp.name} - {rv.variant_name}",
                        message=message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[rp.reseller.email],
                        fail_silently=False,
                    )
                except Exception as e:
                    print(f"❌ Email failed for {rp.reseller.email}: {e}")
            
            else:
                # Create new notification
                if is_increase:
                    message = (
                        f"⚠️ VARIANT PRICE INCREASE from Wholeseller\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"📦 Product: {rp.name}\n"
                        f"🔖 Variant: {rv.variant_name}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"💰 Wholeseller Price Change:\n"
                        f"   • Original Price: ₹{old_price} → ₹{instance.price}\n"
                        f"   • Discount: {old_discount or 0}% → {instance.discount_percentage}%\n"
                        f"   • Your Cost (after discount): ₹{old_discounted} → ₹{new_discounted}\n\n"
                        f"💼 Your Margin: ₹{rv.margin_rupees}\n\n"
                        f"💵 Your Current Selling Price: ₹{rv.selling_price}\n"
                        f"💰 New Proposed Selling Price: ₹{new_selling}\n"
                        f"📈 Increase: +₹{new_selling - old_selling}\n\n"
                        f"⚠️ Your price has NOT been updated automatically.\n"
                        f"👉 Action Required: Review and sync this price change from your dashboard.\n\n"
                        f"🔗 Review here: /products/reseller/store/{rp.store.id}/price-notifications/"
                    )
                else:
                    message = (
                        f"📉 VARIANT PRICE DECREASE from Wholeseller 🎉\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"📦 Product: {rp.name}\n"
                        f"🔖 Variant: {rv.variant_name}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"💰 Wholeseller Price Change:\n"
                        f"   • Original Price: ₹{old_price} → ₹{instance.price}\n"
                        f"   • Discount: {old_discount or 0}% → {instance.discount_percentage}%\n"
                        f"   • Your Cost (after discount): ₹{old_discounted} → ₹{new_discounted}\n\n"
                        f"💼 Your Margin: ₹{rv.margin_rupees} (unchanged)\n\n"
                        f"💵 Your Current Selling Price: ₹{rv.selling_price}\n"
                        f"💰 New Proposed Selling Price: ₹{new_selling}\n"
                        f"📉 Decrease: -₹{old_selling - new_selling}\n\n"
                        f"🎯 Opportunity: You can now:\n"
                        f"   • Sync price to reduce selling price and attract more customers, OR\n"
                        f"   • Keep current price and increase your profit margin!\n\n"
                        f"👉 Review and sync this price change from your dashboard.\n\n"
                        f"🔗 Review here: /products/reseller/store/{rp.store.id}/price-notifications/"
                    )
                
                notification = PriceChangeNotification.objects.create(
                    reseller=rp.reseller,
                    store=rp.store,
                    reseller_product=rp,
                    reseller_variant=rv,
                    notification_type=notification_type,
                    old_price=old_discounted,
                    new_price=new_discounted,
                    old_selling_price=old_selling,
                    new_selling_price=new_selling,
                    message=message,
                )
                
                print(f"📢 Created variant notification {notification.id} for reseller {rp.reseller.email}")
                
                # Send email notification
                try:
                    send_mail(
                        subject=f"{'⚠️ Price Increase Alert' if is_increase else '📉 Price Decrease Opportunity'}: {rp.name} - {rv.variant_name}",
                        message=message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[rp.reseller.email],
                        fail_silently=False,
                    )
                    print(f"📧 Email sent to {rp.reseller.email}")
                except Exception as e:
                    print(f"❌ Email failed for {rp.reseller.email}: {e}")
    
    except Exception as e:
        print(f"❌ Error in variant signal: {e}")
    
    finally:
        # Always clear the flag
        if hasattr(instance, '_price_change_processing'):
            delattr(instance, '_price_change_processing')