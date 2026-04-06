# resellers/models.py

from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinLengthValidator, MaxLengthValidator, RegexValidator
from django.utils.text import slugify

class SubscriptionPlan(models.Model):
    """Subscription plans for stores - Managed by Superuser"""
    
    PLAN_TYPES = [
        ('silver', 'Silver'),
        ('gold', 'Gold'),
        ('platinum', 'Platinum'),
    ]
    
    DURATION_CHOICES = [
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
        ('lifetime', 'Lifetime'),
    ]
    
    name = models.CharField(max_length=50, choices=PLAN_TYPES, unique=True)
    duration = models.CharField(max_length=20, choices=DURATION_CHOICES, default='monthly')
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)  # Added default
    multiple_theme_limit = models.IntegerField(help_text="Max products for multiple products theme", default=0)  # Added default
    features = models.TextField(help_text="Comma-separated list of features", blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['price']
    
    def get_features_list(self):
        if self.features:
            return [f.strip() for f in self.features.split(',') if f.strip()]
        return []
    
    def get_price_display(self):
        """Safe method to display price"""
        try:
            return f"${self.price:.2f}"
        except:
            return "0.00"
    
    def __str__(self):
        try:
            return f"{self.get_name_display()} - {self.get_duration_display()} (${self.price})"
        except:
            return f"{self.get_name_display()} - {self.get_duration_display()}"

class StoreTheme(models.Model):
    """Themes for stores - Only 2 themes total"""
    
    THEME_TYPES = [
        ('single', 'Single Product Theme'),
        ('multiple', 'Multiple Products Theme'),
    ]
    
    name = models.CharField(max_length=100)
    theme_type = models.CharField(max_length=20, choices=THEME_TYPES)
    preview_image = models.ImageField(upload_to='themes/previews/', blank=True, null=True)
    thumbnail = models.ImageField(upload_to='themes/thumbnails/', blank=True, null=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['theme_type', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.get_theme_type_display()})"


class Store(models.Model):
    """Store model for resellers"""
    
    STATUS_CHOICES = [
        ('pending_payment', 'Pending Payment'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('expired', 'Subscription Expired'),
    ]
    
    # Basic Information
    reseller = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='stores'
    )
    
    store_name = models.CharField(
        max_length=100,
        unique=True,
        validators=[
            MinLengthValidator(3),
            MaxLengthValidator(100),
            RegexValidator(
                regex='^[a-zA-Z0-9-]+$',
                message='Store name can only contain letters, numbers, and hyphens'
            )
        ]
    )
    
    subdomain = models.CharField(max_length=100, unique=True, blank=True)
    
    # Store Details
    store_logo = models.ImageField(upload_to='resellers/stores/logos/', blank=True, null=True)
    store_banner = models.ImageField(upload_to='resellers/stores/banners/', blank=True, null=True)
    store_description = models.TextField(blank=True, max_length=500)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=20, blank=True)
    store_address = models.TextField(blank=True)
    
    # Subscription
    subscription_plan = models.ForeignKey(
        SubscriptionPlan, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='stores'
    )
    subscription_start = models.DateTimeField(null=True, blank=True)
    subscription_end = models.DateTimeField(null=True, blank=True)
    
    # Theme
    theme = models.ForeignKey(
        StoreTheme, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='stores'
    )
    
    # Store Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending_payment')
    payment_status = models.BooleanField(default=False)
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    
    # Analytics
    total_visitors = models.IntegerField(default=0)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expiry_notified_7 = models.BooleanField(default=False)
    expiry_notified_3 = models.BooleanField(default=False)
    expiry_notified_expired = models.BooleanField(default=False)
        
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['subdomain']),
            models.Index(fields=['status']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.subdomain:
            base_subdomain = slugify(self.store_name.lower())
            self.subdomain = base_subdomain
            counter = 1
            original_subdomain = self.subdomain
            while Store.objects.filter(subdomain=self.subdomain).exclude(id=self.id).exists():
                self.subdomain = f"{original_subdomain}{counter}"
                counter += 1
        super().save(*args, **kwargs)
    
    def get_full_url(self, request=None):
        if request:
            host = request.get_host().split(':')[0]
            host_parts = host.split('.')
            if len(host_parts) >= 3:
                base_domain = '.'.join(host_parts[1:])
                return f"https://{self.subdomain}.{base_domain}"
            else:
                return f"https://{self.subdomain}.{host}"
        return f"https://{self.subdomain}.example.com"
    
    def get_max_products(self):
        """Calculate max products based on theme and plan"""
        if not self.theme or not self.subscription_plan:
            return 0
        if self.theme.theme_type == 'single':
            return 1
        else:
            return self.subscription_plan.multiple_theme_limit
    
    def increment_visitor(self):
        self.total_visitors += 1
        self.save(update_fields=['total_visitors'])
    
    def is_subscription_active(self):
        """Check if subscription is currently active"""
        if not self.subscription_end:
            # Lifetime plan - always active if status is active
            return self.status == 'active'
        
        # Check if not expired and status is active
        return self.subscription_end > timezone.now() and self.status == 'active'
    
    def days_until_expiry(self):
        """Get days until subscription expires"""
        if not self.subscription_end:
            return None  # Lifetime plan never expires
        
        if self.status == 'expired':
            return 0
            
        delta = self.subscription_end - timezone.now()
        return max(0, delta.days)
    
    def is_expiring_soon(self, days=7):
        """Check if subscription expires within X days"""
        if not self.subscription_end:
            return False
        
        days_left = self.days_until_expiry()
        return 0 < days_left <= days
    
    def can_upgrade_plan(self, new_plan):
        """Check if user can upgrade to a new plan"""
        if not self.subscription_plan:
            return True
        
        # Define plan priority (lower number = lower tier)
        plan_priority = {
            'silver': 1,
            'gold': 2, 
            'platinum': 3
        }
        
        current_priority = plan_priority.get(self.subscription_plan.name, 0)
        new_priority = plan_priority.get(new_plan.name, 0)
        
        return new_priority > current_priority
    
    def calculate_prorated_upgrade_price(self, new_plan):  # ✅ Fixed: no spaces
        """Calculate fair price for upgrading mid-subscription"""
        if not self.subscription_end or not self.subscription_start:
            # No active subscription, pay full price
            return new_plan.price
        
        # Calculate remaining days in current subscription
        remaining_seconds = (self.subscription_end - timezone.now()).total_seconds()
        remaining_days = max(0, remaining_seconds / 86400)  # 86400 seconds in a day
        
        if remaining_days <= 0:
            return new_plan.price
        
        # Calculate daily rate of current plan
        current_plan_days = self._get_plan_duration_days(self.subscription_plan.duration)
        if current_plan_days <= 0:
            return new_plan.price
            
        current_daily_rate = float(self.subscription_plan.price) / current_plan_days
        
        # Calculate remaining value of current subscription
        remaining_value = current_daily_rate * remaining_days
        
        # Calculate upgrade price (new plan price minus remaining value)
        upgrade_price = max(0, float(new_plan.price) - remaining_value)
        
        return round(upgrade_price, 2)
    
    def _get_plan_duration_days(self, duration):
        """Helper to convert duration string to days"""
        if duration == 'monthly':
            return 30
        elif duration == 'yearly':
            return 365
        else:  # lifetime
            return 0
    
    def renew_subscription(self, plan=None, duration=None):
        """
        Renew subscription with same or upgraded plan
        Preserves all store data
        """
        # Use new plan if provided, otherwise keep existing
        if plan:
            self.subscription_plan = plan
        
        if not self.subscription_plan:
            return False
        
        # Update subscription dates
        self.subscription_start = timezone.now()
        self.payment_status = True
        
        # Set end date based on duration
        duration = duration or self.subscription_plan.duration
        
        if duration == 'monthly':
            self.subscription_end = timezone.now() + timezone.timedelta(days=30)
        elif duration == 'yearly':
            self.subscription_end = timezone.now() + timezone.timedelta(days=365)
        else:  # lifetime
            self.subscription_end = None
        
        # Reactivate store
        self.status = 'active'
        self.is_published = True
        
        # If this is a renewal/upgrade, keep the published_at date
        if not self.published_at:
            self.published_at = timezone.now()
        
        self.save()
        return True
    
    def check_and_update_expiry(self):
        """Check if subscription expired and update status"""
        if self.status == 'active' and self.subscription_end:
            if self.subscription_end <= timezone.now():
                self.status = 'expired'
                self.is_published = False
                self.save()
                return True
        return False

    def __str__(self):
        return f"{self.store_name} → {self.subdomain}"


class StoreTransaction(models.Model):
    """Store transaction details from Razorpay"""
    
    TRANSACTION_STATUS = [
        ('created', 'Created'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('pending', 'Pending'),
    ]
    
    # Store Details
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='transactions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='transactions')
    
    # Plan Details
    plan_name = models.CharField(max_length=50)
    plan_price = models.DecimalField(max_digits=10, decimal_places=2)
    plan_duration = models.CharField(max_length=20)
    
    # Store Name (denormalized for quick access)
    store_name = models.CharField(max_length=100)
    
    # Razorpay Details
    razorpay_order_id = models.CharField(max_length=100, unique=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=200, blank=True, null=True)
    
    # Transaction Details
    order_id = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='INR')
    status = models.CharField(max_length=20, choices=TRANSACTION_STATUS, default='created')
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Transaction {self.order_id} - {self.store_name} - {self.status}"