from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings

from .models import (
    WholesellerProduct,
    WholesellerProductVariant,
    ResellerProduct,
    ResellerProductVariant,
    PriceChangeNotification
)
@receiver(post_save, sender=WholesellerProduct)
def notify_resellers_on_product_price_change(sender, instance, created, **kwargs):

    if created or not instance.has_price_changed():
        return

    reseller_products = ResellerProduct.objects.filter(
        source_product=instance,
        source_type='imported',
        is_active=True
    )

    for rp in reseller_products:

        old_selling = rp.selling_price
        new_selling = instance.price + rp.margin_rupees
        diff = new_selling - old_selling

        is_increase = instance.price > instance.previous_price

        notification_type = (
            'product_price_increase' if is_increase else 'product_price_decrease'
        )

        # 🚫 Prevent duplicate spam
        exists = PriceChangeNotification.objects.filter(
            reseller=rp.reseller,
            reseller_product=rp,
            old_price=instance.previous_price,
            new_price=instance.price
        ).exists()

        if exists:
            continue

        # ✅ CLEAN MESSAGE
        if is_increase:
            message = (
                f"⚠️ PRICE INCREASE\n\n"
                f"{instance.name}\n\n"
                f"Base: ₹{instance.previous_price} → ₹{instance.price}\n"
                f"Your Margin: ₹{rp.margin_rupees}\n\n"
                f"Selling: ₹{old_selling} → ₹{new_selling}\n"
                f"Increase: +₹{diff}\n\n"
                f"⚠️ If ignored, you must still pay ₹{instance.price}"
            )
        else:
            message = (
                f"📉 PRICE DECREASE\n\n"
                f"{instance.name}\n\n"
                f"Base: ₹{instance.previous_price} → ₹{instance.price}\n"
                f"Your Margin: ₹{rp.margin_rupees}\n\n"
                f"Selling: ₹{old_selling} → ₹{new_selling}\n"
                f"Change: ₹{diff}\n\n"
                f"You can reduce price or increase profit"
            )

        PriceChangeNotification.objects.create(
            reseller=rp.reseller,
            store=rp.store,
            reseller_product=rp,
            notification_type=notification_type,
            old_price=instance.previous_price,
            new_price=instance.price,
            old_selling_price=old_selling,
            new_selling_price=new_selling,
            message=message,
        )

        # 📧 EMAIL
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

    if created or instance.previous_price == instance.price:
        return

    reseller_variants = ResellerProductVariant.objects.filter(
        source_variant=instance,
        is_active=True
    )

    for rv in reseller_variants:

        rp = rv.product

        old_selling = rv.selling_price
        new_selling = instance.price + rv.margin_rupees
        diff = new_selling - old_selling

        is_increase = instance.price > instance.previous_price

        notification_type = (
            'variant_price_increase' if is_increase else 'variant_price_decrease'
        )

        # 🚫 Prevent duplicate spam
        exists = PriceChangeNotification.objects.filter(
            reseller=rp.reseller,
            reseller_variant=rv,
            old_price=instance.previous_price,
            new_price=instance.price
        ).exists()

        if exists:
            continue

        # ✅ MESSAGE
        if is_increase:
            message = (
                f"⚠️ VARIANT PRICE INCREASE\n\n"
                f"{rp.name} - {rv.variant_name}\n\n"
                f"Base: ₹{instance.previous_price} → ₹{instance.price}\n"
                f"Margin: ₹{rv.margin_rupees}\n\n"
                f"Selling: ₹{old_selling} → ₹{new_selling}\n"
                f"Increase: +₹{diff}"
            )
        else:
            message = (
                f"📉 VARIANT PRICE DECREASE\n\n"
                f"{rp.name} - {rv.variant_name}\n\n"
                f"Base: ₹{instance.previous_price} → ₹{instance.price}\n"
                f"Margin: ₹{rv.margin_rupees}\n\n"
                f"Selling: ₹{old_selling} → ₹{new_selling}\n"
                f"Change: ₹{diff}"
            )

        PriceChangeNotification.objects.create(
            reseller=rp.reseller,
            store=rp.store,
            reseller_product=rp,
            reseller_variant=rv,
            notification_type=notification_type,
            old_price=instance.previous_price,
            new_price=instance.price,
            old_selling_price=old_selling,
            new_selling_price=new_selling,
            message=message,
        )