# orders/models.py
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
import uuid
import json

class Order(models.Model):
    """Main Order Model"""
    
    ORDER_STATUS_CHOICES = [
        ('pending', 'Pending Payment'),
        ('payment_failed', 'Payment Failed'),
        ('paid', 'Paid - Awaiting Approval'),
        ('approved', 'Approved - Processing'),
        ('shipped', 'Shipped'),
        ('out_for_delivery', 'Out for Delivery'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('return_requested', 'Return Requested'),
        ('return_approved', 'Return Approved'),
        ('return_rejected', 'Return Rejected'),
        ('refunded', 'Refunded'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    
    # Order Identification
    order_id = models.CharField(max_length=50, unique=True, editable=False)
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    
    # Customer Details
    customer_name = models.CharField(max_length=200)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=15)
    
    # Shipping Address
    shipping_address = models.TextField()
    shipping_city = models.CharField(max_length=100)
    shipping_state = models.CharField(max_length=100)
    shipping_pincode = models.CharField(max_length=10)
    shipping_country = models.CharField(max_length=100, default='India')
    
    # Product Details
    product = models.ForeignKey('products.ResellerProduct', on_delete=models.SET_NULL, null=True, related_name='orders')
    variant = models.ForeignKey('products.ResellerProductVariant', on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    quantity = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    
    # Store and Reseller
    store = models.ForeignKey('resellers.Store', on_delete=models.CASCADE, related_name='orders')
    reseller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reseller_orders')
    wholeseller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='wholeseller_orders')
    
    # Pricing
    product_price = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Status
    order_status = models.CharField(max_length=30, choices=ORDER_STATUS_CHOICES, default='pending')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    
    # Shiprocket Data
    shiprocket_order_id = models.CharField(max_length=100, blank=True, null=True)
    shipment_id = models.CharField(max_length=100, blank=True, null=True)
    awb_code = models.CharField(max_length=100, blank=True, null=True)
    courier_name = models.CharField(max_length=100, blank=True, null=True)
    tracking_url = models.URLField(blank=True, null=True)
    tracking_status = models.TextField(blank=True)
    
    # Delivery Estimates
    estimated_delivery_date = models.DateField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    # Pickup Location Details
    pickup_address_type = models.CharField(max_length=20, choices=[('wholeseller', 'Wholeseller'), ('reseller', 'Reseller')])
    pickup_address = models.TextField()
    pickup_pincode = models.CharField(max_length=10)
    
    # Webhook tracking
    webhook_received_at = models.DateTimeField(null=True, blank=True)
    last_shiprocket_status = models.CharField(max_length=100, blank=True)
    last_shiprocket_status_code = models.CharField(max_length=20, blank=True)
    status_history = models.JSONField(default=list, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order_id']),
            models.Index(fields=['store', 'order_status']),
            models.Index(fields=['reseller', 'order_status']),
            models.Index(fields=['wholeseller']),
            models.Index(fields=['awb_code']),
            models.Index(fields=['shipment_id']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.order_id:
            self.order_id = f"ORD{timezone.now().strftime('%Y%m%d')}{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.order_id} - {self.customer_name}"
    
    def add_status_history(self, status, details=None):
        """Add entry to status history"""
        history_entry = {
            'status': status,
            'timestamp': timezone.now().isoformat(),
            'details': details or {}
        }
        self.status_history.append(history_entry)
        self.save(update_fields=['status_history'])
    
    def can_cancel(self):
        """Check if order can be cancelled (before shipping)"""
        return self.order_status in ['pending', 'paid', 'approved'] and not self.shipped_at
    
    def can_request_return(self):
        """Check if return can be requested (within 7 days of delivery)"""
        if self.order_status != 'delivered':
            return False
        if not self.delivered_at:
            return False
        days_since_delivery = (timezone.now() - self.delivered_at).days
        return days_since_delivery <= 7
    
    def can_approve(self):
        """Check if reseller can approve order"""
        return self.order_status == 'paid' and self.payment_status == 'success'


class ReturnRequest(models.Model):
    """Return Request Model with Unboxing Video"""
    
    RETURN_REASON_CHOICES = [
        ('damaged', 'Product Damaged at Delivery'),
        ('wrong_product', 'Wrong Product Received'),
        ('defective', 'Product Defective'),
        ('missing_parts', 'Missing Parts/Accessories'),
    ]
    
    RETURN_STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved - Pickup Scheduled'),
        ('pickup_scheduled', 'Pickup Scheduled'),
        ('picked_up', 'Product Picked Up'),
        ('in_transit', 'In Transit to Warehouse'),
        ('delivered_to_warehouse', 'Delivered to Warehouse'),
        ('rejected', 'Rejected'),
        ('refunded', 'Refunded'),
        ('replacement_shipped', 'Replacement Shipped'),
    ]
    
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='return_requests')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    
    reason = models.CharField(max_length=30, choices=RETURN_REASON_CHOICES)
    description = models.TextField()
    
    # Unboxing Video (required)
    unboxing_video = models.FileField(upload_to='returns/unboxing_videos/')
    video_verified = models.BooleanField(default=False)
    verification_notes = models.TextField(blank=True)
    
    # Images of damaged product
    product_images = models.FileField(upload_to='returns/product_images/', blank=True, null=True)
    
    # Return Address (where to send product)
    return_address = models.TextField()
    
    # Refund Details
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Bank Details for Manual Refund
    account_holder_name = models.CharField(max_length=200, blank=True)
    account_number = models.CharField(max_length=50, blank=True)
    confirm_account_number = models.CharField(max_length=50, blank=True)
    ifsc_code = models.CharField(max_length=20, blank=True)
    bank_name = models.CharField(max_length=200, blank=True)
    upi_id = models.CharField(max_length=100, blank=True)
    
    # Shiprocket Return Shipment Fields
    return_shipment_id = models.CharField(max_length=100, blank=True, null=True)
    return_awb = models.CharField(max_length=100, blank=True, null=True)
    return_label_url = models.URLField(blank=True, null=True)
    return_courier_name = models.CharField(max_length=100, blank=True, null=True)
    return_pickup_scheduled_date = models.DateField(null=True, blank=True)
    return_pickup_completed = models.BooleanField(default=False)
    return_picked_up_at = models.DateTimeField(null=True, blank=True)
    return_delivered_at = models.DateTimeField(null=True, blank=True)
    
    # For replacements (new product shipment)
    replacement_order_id = models.CharField(max_length=50, blank=True, null=True)
    replacement_shipped = models.BooleanField(default=False)
    
    # Status
    status = models.CharField(max_length=40, choices=RETURN_STATUS_CHOICES, default='pending')
    
    # Admin/Reseller Notes
    admin_notes = models.TextField(blank=True)
    reseller_notes = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Return for {self.order.order_id} - {self.get_status_display()}"
    
    def save(self, *args, **kwargs):
        if self.account_number and self.confirm_account_number:
            if self.account_number != self.confirm_account_number:
                raise ValueError("Account numbers do not match")
        if not self.refund_amount and self.order:
            self.refund_amount = self.order.total_amount
        super().save(*args, **kwargs)
    
    def add_status_history(self, status, details=None):
        """Add to return status history"""
        history = getattr(self, 'return_status_history', [])
        history.append({
            'status': status,
            'timestamp': timezone.now().isoformat(),
            'details': details or {}
        })
        self.return_status_history = history
        self.save(update_fields=['return_status_history'])


class Refund(models.Model):
    """Manual Refund Record"""
    
    REFUND_TYPE_CHOICES = [
        ('return', 'Product Return'),
        ('cancellation', 'Order Cancellation'),
    ]
    
    REFUND_STATUS_CHOICES = [
        ('pending', 'Pending Processing'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    return_request = models.ForeignKey(ReturnRequest, on_delete=models.CASCADE, null=True, blank=True, related_name='refunds')
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='refunds')
    
    refund_type = models.CharField(max_length=20, choices=REFUND_TYPE_CHOICES)
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Customer Bank Details for Manual Refund
    account_holder_name = models.CharField(max_length=200)
    account_number = models.CharField(max_length=50)
    ifsc_code = models.CharField(max_length=20)
    bank_name = models.CharField(max_length=200)
    upi_id = models.CharField(max_length=100, blank=True)
    
    # Refund Processing
    status = models.CharField(max_length=20, choices=REFUND_STATUS_CHOICES, default='pending')
    transaction_id = models.CharField(max_length=100, blank=True)
    admin_notes = models.TextField(blank=True)
    
    # Bank Transfer Proof
    transfer_proof = models.FileField(upload_to='refunds/proofs/', blank=True, null=True)
    
    # Timestamps
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-requested_at']
    
    def __str__(self):
        return f"Refund for {self.order.order_id} - {self.get_status_display()}"