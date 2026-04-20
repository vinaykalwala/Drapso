# products/models.py
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.text import slugify
from django.utils import timezone
import random
import string
from decimal import Decimal
from django.utils.text import slugify
from django.utils import timezone

# ============ SKU DEFAULT GENERATORS FOR MIGRATION ============

def generate_default_wholeseller_sku():
    """Generate a temporary unique SKU for migration"""
    timestamp = str(int(timezone.now().timestamp()))[-6:]
    random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"WP-TEMP-{timestamp}-{random_suffix}"

def generate_default_wholeseller_variant_sku():
    """Generate a temporary unique SKU for migration"""
    timestamp = str(int(timezone.now().timestamp()))[-6:]
    random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"WV-TEMP-{timestamp}-{random_suffix}"

def generate_default_reseller_sku():
    """Generate a temporary unique SKU for migration"""
    timestamp = str(int(timezone.now().timestamp()))[-6:]
    random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"RP-TEMP-{timestamp}-{random_suffix}"

def generate_default_reseller_variant_sku():
    """Generate a temporary unique SKU for migration"""
    timestamp = str(int(timezone.now().timestamp()))[-6:]
    random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"RV-TEMP-{timestamp}-{random_suffix}"

# ============ CATEGORIES (Superuser only) ============

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='categories/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['order', 'name']
        verbose_name_plural = "Categories"
        indexes = [
            models.Index(fields=['is_active', 'order']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.name


class Subcategory(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='subcategories')
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    image = models.ImageField(upload_to='subcategories/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['order', 'name']
        unique_together = ['category', 'name']
        indexes = [
            models.Index(fields=['category', 'is_active']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.category.name}-{self.name}")
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.category.name} > {self.name}"


# ============ WHOLESELLER PRODUCTS ============

class WholesellerProduct(models.Model):
    wholeseller = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='wholeseller_products',
        limit_choices_to={'role': 'wholeseller'}
    )
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    subcategory = models.ForeignKey(Subcategory, on_delete=models.SET_NULL, null=True)
    
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField()
    specification = models.TextField(blank=True)
    
    brand = models.CharField(max_length=100, blank=True)
    model_name = models.CharField(max_length=200, blank=True)
    size = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=50, blank=True)
    material = models.CharField(max_length=100, blank=True)
    gender = models.CharField(max_length=20, blank=True, choices=[
        ('male', 'Male'), ('female', 'Female'), ('unisex', 'Unisex'), ('kids', 'Kids')
    ])
    attributes = models.JSONField(default=dict, blank=True)
    
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    previous_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price_updated_at = models.DateTimeField(null=True, blank=True)
    
    # DISCOUNT FIELDS
    discount_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Discount percentage (0-100)"
    )
    discounted_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Auto-calculated discounted price"
    )
    
    stock = models.IntegerField(default=0, validators=[MinValueValidator(0)], help_text="Independent stock for product")
    threshold_limit = models.IntegerField(default=5, validators=[MinValueValidator(0)], help_text="Alert when stock below this")
    
    sku = models.CharField(
        max_length=100, 
        blank=True, 
        default=generate_default_wholeseller_sku,
        help_text="Stock Keeping Unit - Auto-generated if left blank"
    )
    hsn_code = models.CharField(max_length=20, default='0000', help_text="HSN Code for GST classification")
    
    main_image = models.ImageField(upload_to='wholeseller/products/main/')
    
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    weight = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    length = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    breadth = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    height = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    is_shippable = models.BooleanField(default=True)

    is_returnable = models.BooleanField(default=False)
    return_window_days = models.PositiveIntegerField(default=3)

    is_replaceable = models.BooleanField(default=False)
    replacement_window_days = models.PositiveIntegerField(default=3)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['stock', 'threshold_limit']),
            models.Index(fields=['wholeseller', 'is_active']),
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['sku']),
        ]
    
    def generate_sku(self):
        """Generate unique SKU for wholeseller product"""
        wholeseller_prefix = str(self.wholeseller.id).zfill(3)
        category_code = self.category.name[:3].upper() if self.category else 'GEN'
        random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        sku = f"WP-{wholeseller_prefix}-{category_code}-{random_suffix}"
        
        while WholesellerProduct.objects.filter(sku=sku).exists():
            random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            sku = f"WP-{wholeseller_prefix}-{category_code}-{random_suffix}"
        
        return sku
    
    def calculate_discounted_price(self):
        """Calculate discounted price based on discount percentage"""
        if self.discount_percentage > 0:
            discount_amount = (self.price * self.discount_percentage) / 100
            return self.price - discount_amount
        return self.price
    
    def get_effective_price(self):
        """Get the effective price after discount (what reseller pays)"""
        if self.discounted_price:
            return self.discounted_price
        return self.calculate_discounted_price()
    
    def save(self, *args, **kwargs):
        # Calculate discounted price
        self.discounted_price = self.calculate_discounted_price()
        
        # Generate proper SKU if it's a temporary one or empty
        if not self.sku or (self.sku and 'TEMP' in self.sku):
            self.sku = self.generate_sku()
        
        # Set default HSN code if not set
        if not self.hsn_code or self.hsn_code == '0000':
            self.hsn_code = '0000'
        
        # Track stock changes before save
        if self.pk:
            old_instance = WholesellerProduct.objects.filter(pk=self.pk).first()
            if old_instance:
                self._stock_changed = old_instance.stock != self.stock
                self._old_stock = old_instance.stock
                self._discount_changed = old_instance.discount_percentage != self.discount_percentage
            else:
                self._stock_changed = False
                self._discount_changed = False
        else:
            self._stock_changed = False
            self._discount_changed = False
        
        # Handle price change tracking
        if self.pk:
            old_price = WholesellerProduct.objects.filter(pk=self.pk).values_list('price', flat=True).first()
            if old_price is not None and old_price != self.price:
                self.previous_price = old_price
                self.price_updated_at = timezone.now()
        
        if not self.slug:
            base_slug = slugify(self.name)
            self.slug = base_slug
            counter = 1
            while WholesellerProduct.objects.filter(slug=self.slug).exists():
                self.slug = f"{base_slug}-{counter}"
                counter += 1
        
        super().save(*args, **kwargs)
        
        # AFTER save - sync to all resellers if stock or discount changed
        if getattr(self, '_stock_changed', False) or getattr(self, '_discount_changed', False):
            self._sync_to_resellers()
    
    def _sync_to_resellers(self):
        """Automatically sync stock and discount to all reseller imports"""
        affected_reseller_products = ResellerProduct.objects.filter(
            source_product=self,
            source_type='imported',
            is_active=True
        ).select_related('reseller', 'store')
        
        # Bulk update for better performance
        for reseller_product in affected_reseller_products:
            update_fields = ['updated_at']
            
            if getattr(self, '_stock_changed', False):
                reseller_product.stock = self.stock
                update_fields.append('stock')
            
            if getattr(self, '_discount_changed', False):
                reseller_product.discount_percentage = self.discount_percentage
                
                # Recalculate selling price based on effective price
                source_effective_price = self.get_effective_price()
                reseller_product.selling_price = source_effective_price + reseller_product.margin_rupees
                
                # Recalculate discounted price for reseller
                if self.discount_percentage > 0:
                    discount_amount = (reseller_product.selling_price * self.discount_percentage) / 100
                    reseller_product.discounted_price = reseller_product.selling_price - discount_amount
                else:
                    reseller_product.discounted_price = reseller_product.selling_price
                
                update_fields.extend(['discount_percentage', 'selling_price', 'discounted_price'])
            
            reseller_product.save(update_fields=update_fields)
        
        # Also sync variants
        for reseller_product in affected_reseller_products:
            for variant in reseller_product.variants.filter(source_variant__isnull=False):
                if variant.source_variant:
                    variant_update_fields = ['updated_at']
                    
                    if getattr(self, '_stock_changed', False):
                        variant.stock = variant.source_variant.stock
                        variant_update_fields.append('stock')
                    
                    if getattr(self, '_discount_changed', False):
                        variant.discount_percentage = variant.source_variant.discount_percentage
                        
                        # Recalculate selling price based on effective price
                        variant_effective_price = variant.source_variant.get_effective_price()
                        variant.selling_price = variant_effective_price + variant.margin_rupees
                        
                        # Recalculate discounted price
                        if variant.discount_percentage > 0:
                            discount_amount = (variant.selling_price * variant.discount_percentage) / 100
                            variant.discounted_price = variant.selling_price - discount_amount
                        else:
                            variant.discounted_price = variant.selling_price
                        
                        variant_update_fields.extend(['discount_percentage', 'selling_price', 'discounted_price'])
                    
                    variant.save(update_fields=variant_update_fields)
        
        # Create notifications for critical changes
        if getattr(self, '_stock_changed', False):
            if self.stock == 0 and affected_reseller_products.exists():
                self._create_stock_out_notifications(affected_reseller_products)
            elif self.stock <= self.threshold_limit and getattr(self, '_old_stock', 0) > self.threshold_limit:
                self._create_low_stock_notifications(affected_reseller_products)
        
        if getattr(self, '_discount_changed', False) and self.discount_percentage > 0:
            self._create_discount_notifications(affected_reseller_products)
    
    def _create_stock_out_notifications(self, reseller_products):
        """Create notifications for stock out"""
        for rp in reseller_products:
            PriceChangeNotification.objects.create(
                reseller=rp.reseller,
                store=rp.store,
                reseller_product=rp,
                notification_type='stock_out',
                old_price=self.previous_price or self.price,
                new_price=self.price,
                old_selling_price=rp.selling_price,
                new_selling_price=rp.selling_price,
                message=f"⚠️ URGENT: '{self.name}' is now OUT OF STOCK from wholeseller! Please update your store."
            )
    
    def _create_low_stock_notifications(self, reseller_products):
        """Create notifications for low stock"""
        for rp in reseller_products:
            PriceChangeNotification.objects.create(
                reseller=rp.reseller,
                store=rp.store,
                reseller_product=rp,
                notification_type='low_stock',
                old_price=self.previous_price or self.price,
                new_price=self.price,
                old_selling_price=rp.selling_price,
                new_selling_price=rp.selling_price,
                message=f"⚠️ '{self.name}' stock is low ({self.stock} units remaining). Consider updating your inventory."
            )
    
    def _create_discount_notifications(self, reseller_products):
        """Create notifications for new discounts"""
        for rp in reseller_products:
            PriceChangeNotification.objects.create(
                reseller=rp.reseller,
                store=rp.store,
                reseller_product=rp,
                notification_type='product_price_decrease',
                old_price=self.previous_price or self.price,
                new_price=self.price,
                old_selling_price=rp.selling_price,
                new_selling_price=rp.selling_price,
                message=f"🎉 '{self.name}' now has {self.discount_percentage}% discount! Your new cost: ₹{self.get_effective_price()}"
            )
    
    def has_price_changed(self):
        return self.previous_price is not None and self.previous_price != self.price
    
    def get_price_difference(self):
        if self.previous_price:
            return self.price - self.previous_price
        return 0
    
    def is_price_increased(self):
        return self.get_price_difference() > 0
    
    def is_low_stock(self):
        return self.stock <= self.threshold_limit
    
    def get_affected_resellers(self):
        return self.reseller_products.filter(source_type='imported', is_active=True)
    
    def __str__(self):
        brand_str = f"{self.brand} " if self.brand else ""
        stock_status = " [Low Stock]" if self.is_low_stock() else ""
        discount_status = f" [{self.discount_percentage}% OFF]" if self.discount_percentage > 0 else ""
        return f"{brand_str}{self.name} - ₹{self.get_effective_price()}{discount_status}{stock_status}"


class WholesellerProductImage(models.Model):
    product = models.ForeignKey(WholesellerProduct, on_delete=models.CASCADE, related_name='additional_images')
    image = models.ImageField(upload_to='wholeseller/products/gallery/')
    alt_text = models.CharField(max_length=200, blank=True)
    order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['order']


class WholesellerProductVariant(models.Model):
    product = models.ForeignKey(WholesellerProduct, on_delete=models.CASCADE, related_name='variants')
    
    size = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=50, blank=True)
    variant_name = models.CharField(max_length=200, blank=True)
    
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    previous_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price_updated_at = models.DateTimeField(null=True, blank=True)
    
    # DISCOUNT FIELDS
    discount_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    discounted_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    
    stock = models.IntegerField(default=0, validators=[MinValueValidator(0)], help_text="Independent stock for variant")
    threshold_limit = models.IntegerField(default=5, validators=[MinValueValidator(0)])
    
    sku = models.CharField(
        max_length=100, 
        blank=True, 
        default=generate_default_wholeseller_variant_sku
    )
    hsn_code = models.CharField(max_length=20, default='0000', help_text="HSN Code for GST classification")
    main_image = models.ImageField(upload_to='wholeseller/variants/main/', blank=True, null=True)
    
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    weight = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    length = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    breadth = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    height = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    is_returnable = models.BooleanField(default=False)
    return_window_days = models.PositiveIntegerField(default=3)

    is_replaceable = models.BooleanField(default=False)
    replacement_window_days = models.PositiveIntegerField(default=3)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'variant_name']
        indexes = [
            models.Index(fields=['stock', 'threshold_limit']),
            models.Index(fields=['product', 'is_active']),
            models.Index(fields=['sku']),
        ]
    
    def generate_variant_sku(self):
        """Generate unique SKU for wholeseller variant"""
        parent_sku = self.product.sku if self.product.sku else f"WP-{self.product.id}"
        
        variant_parts = []
        if self.size:
            variant_parts.append(self.size.upper())
        if self.color:
            variant_parts.append(self.color.upper())
        
        variant_suffix = '-'.join(variant_parts) if variant_parts else 'VAR'
        random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        sku = f"{parent_sku}-{variant_suffix}-{random_suffix}"
        
        while WholesellerProductVariant.objects.filter(sku=sku).exists():
            random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            sku = f"{parent_sku}-{variant_suffix}-{random_suffix}"
        
        return sku
    
    def calculate_discounted_price(self):
        """Calculate discounted price based on discount percentage"""
        if self.discount_percentage > 0:
            discount_amount = (self.price * self.discount_percentage) / 100
            return self.price - discount_amount
        return self.price
    
    def get_effective_price(self):
        """Get the effective price after discount"""
        if self.discounted_price:
            return self.discounted_price
        return self.calculate_discounted_price()
    
    def save(self, *args, **kwargs):
        # Calculate discounted price
        self.discounted_price = self.calculate_discounted_price()
        
        # Track changes
        if self.pk:
            old_instance = WholesellerProductVariant.objects.filter(pk=self.pk).first()
            if old_instance:
                self._stock_changed = old_instance.stock != self.stock
                self._old_stock = old_instance.stock
                self._discount_changed = old_instance.discount_percentage != self.discount_percentage
            else:
                self._stock_changed = False
                self._discount_changed = False
        else:
            self._stock_changed = False
            self._discount_changed = False
        
        # Handle price change tracking
        if self.pk:
            old_price = WholesellerProductVariant.objects.filter(pk=self.pk).values_list('price', flat=True).first()
            if old_price is not None and old_price != self.price:
                self.previous_price = old_price
                self.price_updated_at = timezone.now()
        
        # Generate proper SKU if it's a temporary one or empty
        if not self.sku or (self.sku and 'TEMP' in self.sku):
            self.sku = self.generate_variant_sku()
        
        # Set default HSN code (inherit from parent if available)
        if not self.hsn_code or self.hsn_code == '0000':
            if self.product and self.product.hsn_code:
                self.hsn_code = self.product.hsn_code
            else:
                self.hsn_code = '0000'
        
        if not self.variant_name:
            parts = []
            if self.size:
                parts.append(self.size)
            if self.color:
                parts.append(self.color)
            self.variant_name = " - ".join(parts) if parts else "Default"
        
        super().save(*args, **kwargs)
        
        # AFTER save - sync variant to all resellers if stock or discount changed
        if getattr(self, '_stock_changed', False) or getattr(self, '_discount_changed', False):
            self._sync_to_resellers()
    
    def _sync_to_resellers(self):
        """Automatically sync variant stock and discount to all reseller imports"""
        affected_reseller_variants = ResellerProductVariant.objects.filter(
            source_variant=self,
            product__is_active=True,
            product__source_type='imported'
        ).select_related('product')
        
        for reseller_variant in affected_reseller_variants:
            update_fields = ['updated_at']
            
            if getattr(self, '_stock_changed', False):
                reseller_variant.stock = self.stock
                update_fields.append('stock')
            
            if getattr(self, '_discount_changed', False):
                reseller_variant.discount_percentage = self.discount_percentage
                
                # Recalculate selling price based on effective price
                variant_effective_price = self.get_effective_price()
                reseller_variant.selling_price = variant_effective_price + reseller_variant.margin_rupees
                
                # Recalculate discounted price
                if self.discount_percentage > 0:
                    discount_amount = (reseller_variant.selling_price * self.discount_percentage) / 100
                    reseller_variant.discounted_price = reseller_variant.selling_price - discount_amount
                else:
                    reseller_variant.discounted_price = reseller_variant.selling_price
                
                update_fields.extend(['discount_percentage', 'selling_price', 'discounted_price'])
            
            reseller_variant.save(update_fields=update_fields)
        
        # Create notifications for critical stock changes
        if getattr(self, '_stock_changed', False) and self.stock == 0 and affected_reseller_variants.exists():
            self._create_variant_stock_out_notifications(affected_reseller_variants)
    
    def _create_variant_stock_out_notifications(self, reseller_variants):
        """Create notifications for variant stock out"""
        for rv in reseller_variants:
            PriceChangeNotification.objects.create(
                reseller=rv.product.reseller,
                store=rv.product.store,
                reseller_product=rv.product,
                reseller_variant=rv,
                notification_type='stock_out',
                old_price=self.previous_price or self.price,
                new_price=self.price,
                old_selling_price=rv.selling_price,
                new_selling_price=rv.selling_price,
                message=f"⚠️ Variant '{rv.variant_name}' of '{rv.product.name}' is now OUT OF STOCK from wholeseller!"
            )
    
    def is_low_stock(self):
        return self.stock <= self.threshold_limit
    
    def get_display_price(self):
        return self.get_effective_price()
    
    def __str__(self):
        stock_status = " [Low Stock]" if self.is_low_stock() else ""
        discount_status = f" [{self.discount_percentage}% OFF]" if self.discount_percentage > 0 else ""
        return f"{self.product.name} - {self.variant_name} (₹{self.get_effective_price()}){discount_status}{stock_status}"


class WholesellerVariantImage(models.Model):
    variant = models.ForeignKey(WholesellerProductVariant, on_delete=models.CASCADE, related_name='additional_images')
    image = models.ImageField(upload_to='wholeseller/variants/gallery/')
    alt_text = models.CharField(max_length=200, blank=True)
    order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['order']


# ============ RESELLER PRODUCTS ============

class ResellerProduct(models.Model):
    SOURCE_CHOICES = [
        ('imported', 'Imported from Wholeseller'),
        ('own', 'Own Product'),
    ]
    
    PRICE_STATUS_CHOICES = [
        ('up_to_date', 'Up to Date'),
        ('price_increased', 'Price Increased - Needs Review'),
        ('price_decreased', 'Price Decreased - Needs Review'),
        ('reviewed', 'Reviewed'),
    ]
    
    reseller = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='reseller_products',
        limit_choices_to={'role': 'reseller'}
    )
    store = models.ForeignKey(
        'resellers.Store', 
        on_delete=models.CASCADE, 
        related_name='products'
    )
    source_product = models.ForeignKey(
        WholesellerProduct, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='reseller_products'
    )
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    subcategory = models.ForeignKey(Subcategory, on_delete=models.SET_NULL, null=True)
    
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, blank=True)
    description = models.TextField()
    specification = models.TextField(blank=True)
    
    brand = models.CharField(max_length=100, blank=True)
    model_name = models.CharField(max_length=200, blank=True)
    size = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=50, blank=True)
    material = models.CharField(max_length=100, blank=True)
    gender = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ('male', 'Male'),
            ('female', 'Female'),
            ('unisex', 'Unisex'),
            ('kids', 'Kids'),
        ]
    )
    attributes = models.JSONField(default=dict, blank=True)
    
    source_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    margin_rupees = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    
    # DISCOUNT FIELDS
    discount_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    discounted_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    
    last_known_source_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_status = models.CharField(max_length=30, choices=PRICE_STATUS_CHOICES, default='up_to_date')
    price_change_notified_at = models.DateTimeField(null=True, blank=True)
    price_reviewed_at = models.DateTimeField(null=True, blank=True)
    
    stock = models.IntegerField(default=0, validators=[MinValueValidator(0)], help_text="Auto-synced for imported products")
    threshold_limit = models.IntegerField(default=5, validators=[MinValueValidator(0)])
    
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='own')
    
    sku = models.CharField(
        max_length=100, 
        blank=True, 
        default=generate_default_reseller_sku,
        help_text="Stock Keeping Unit - Auto-generated if left blank"
    )
    hsn_code = models.CharField(max_length=20, default='0000', help_text="HSN Code for GST classification")
    
    main_image = models.ImageField(upload_to='reseller/products/main/', blank=True, null=True)
    
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    is_published = models.BooleanField(default=False)
    
    weight = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    length = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    breadth = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    height = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    is_shippable = models.BooleanField(default=True)

    is_returnable = models.BooleanField(default=False)
    return_window_days = models.PositiveIntegerField(default=3)

    is_replaceable = models.BooleanField(default=False)
    replacement_window_days = models.PositiveIntegerField(default=3)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['store', 'slug']
        indexes = [
            models.Index(fields=['source_type', 'stock']),
            models.Index(fields=['source_product', 'source_type']),
            models.Index(fields=['reseller', 'store', 'is_active']),
            models.Index(fields=['price_status']),
            models.Index(fields=['sku']),
        ]
    
    def generate_reseller_sku(self):
        """Generate unique SKU for reseller own product"""
        reseller_prefix = str(self.reseller.id).zfill(3)
        store_prefix = str(self.store.id).zfill(2)
        category_code = self.category.name[:3].upper() if self.category else 'GEN'
        random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        sku = f"RP-{reseller_prefix}-{store_prefix}-{category_code}-{random_suffix}"
        
        while ResellerProduct.objects.filter(sku=sku).exists():
            random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            sku = f"RP-{reseller_prefix}-{store_prefix}-{category_code}-{random_suffix}"
        
        return sku
    
    def calculate_discounted_price(self):
        """Calculate discounted price based on discount percentage"""
        if self.discount_percentage > 0:
            discount_amount = (self.selling_price * self.discount_percentage) / 100
            return self.selling_price - discount_amount
        return self.selling_price
    
    def get_effective_price(self):
        """Get the effective price after discount (what customer pays)"""
        if self.discounted_price:
            return self.discounted_price
        return self.calculate_discounted_price()
    
    def _update_stock_from_variants(self):
        """Update product stock based on its variants (for own products only)"""
        if self.source_type == 'own':
            total_stock = self.variants.aggregate(total=models.Sum('stock'))['total'] or 0
            if self.stock != total_stock:
                self.stock = total_stock
                self.save(update_fields=['stock', 'updated_at'])
    
    def save(self, *args, **kwargs):

    # ================= SLUG =================
            if not self.slug:
                base_slug = slugify(self.name)
                self.slug = base_slug
                counter = 1

                while ResellerProduct.objects.filter(
                    store=self.store,
                    slug=self.slug
                ).exists():

                    self.slug = f"{base_slug}-{counter}"
                    counter += 1


            # ================= IMPORTED PRODUCT =================
            if self.source_type == 'imported' and self.source_product:

                is_new = self.pk is None

                # STOCK SYNC
                self.stock = self.source_product.stock

                # SKU + HSN SYNC
                if self.source_product.sku:
                    self.sku = self.source_product.sku

                if self.source_product.hsn_code:
                    self.hsn_code = self.source_product.hsn_code


                # SOURCE EFFECTIVE PRICE (after discount)
                source_effective_price = self.source_product.get_effective_price()

                # ================= PRICE CHANGE CHECK =================
                # ONLY check wholeseller change (NOT margin change)

                if not is_new:

                    old_source_price = self.last_known_source_price
                    new_source_price = source_effective_price

                    if old_source_price is not None:

                        difference = abs(
                            Decimal(new_source_price) -
                            Decimal(old_source_price)
                        )

                        if difference > Decimal('0.01'):

                            if new_source_price > old_source_price:
                                self.price_status = 'price_increased'
                            else:
                                self.price_status = 'price_decreased'

                            self.price_change_notified_at = timezone.now()


                # ================= PRICE SYNC =================

                self.source_price = self.source_product.price

                # selling price = discounted source price + margin
                self.selling_price = (
                    source_effective_price +
                    Decimal(self.margin_rupees or 0)
                )


                # ================= DISCOUNT CALC =================

                self.discount_percentage = self.source_product.discount_percentage

                if self.discount_percentage > 0:

                    discount_amount = (
                        self.selling_price *
                        Decimal(self.discount_percentage) / 100
                    )

                    self.discounted_price = (
                        self.selling_price - discount_amount
                    )

                else:

                    self.discounted_price = self.selling_price


                # ================= ATTRIBUTE SYNC =================

                self.brand = self.source_product.brand
                self.model_name = self.source_product.model_name
                self.size = self.source_product.size
                self.color = self.source_product.color
                self.material = self.source_product.material
                self.gender = self.source_product.gender
                self.attributes = self.source_product.attributes
                self.specification = self.source_product.specification

                self.threshold_limit = self.source_product.threshold_limit


                # ================= SHIPPING SYNC =================

                self.weight = self.source_product.weight
                self.length = self.source_product.length
                self.breadth = self.source_product.breadth
                self.height = self.source_product.height

                self.is_shippable = self.source_product.is_shippable


                # ================= RETURN POLICY =================

                self.is_returnable = self.source_product.is_returnable
                self.return_window_days = self.source_product.return_window_days

                self.is_replaceable = self.source_product.is_replaceable
                self.replacement_window_days = self.source_product.replacement_window_days


                # ================= INITIAL STATE =================

                if is_new:

                    self.price_status = 'up_to_date'

                    self.last_known_source_price = source_effective_price


            # ================= OWN PRODUCT =================

            else:

                self.source_price = 0

                if not self.sku or 'TEMP' in str(self.sku):

                    self.sku = self.generate_reseller_sku()

                if not self.hsn_code:

                    self.hsn_code = '0000'


                if not self.selling_price:

                    raise ValueError("Selling price required")


                # calculate discount
                self.discounted_price = self.calculate_discounted_price()


            # ================= SAVE =================

            super().save(*args, **kwargs)

    def has_price_change_pending(self):
        return self.price_status in ['price_increased', 'price_decreased']
    
    def get_price_difference(self):
        if self.last_known_source_price:
            return self.source_price - self.last_known_source_price
        return 0
    
    def get_new_selling_price(self):
        source_effective_price = self.source_product.get_effective_price() if self.source_product else self.source_price
        return source_effective_price + self.margin_rupees
    
    def get_old_selling_price(self):
        old_source_effective = self.last_known_source_price
        return old_source_effective + self.margin_rupees if self.last_known_source_price else self.selling_price
    
    def apply_price_update(self):
        self.selling_price = self.get_new_selling_price()
        if self.discount_percentage > 0:
            discount_amount = (self.selling_price * self.discount_percentage) / 100
            self.discounted_price = self.selling_price - discount_amount
        self.last_known_source_price = self.source_price
        self.price_status = 'reviewed'
        self.price_reviewed_at = timezone.now()
        self.save()
        return True
    
    def ignore_price_update(self):
        self.price_status = 'reviewed'
        self.price_reviewed_at = timezone.now()
        self.save()
        return True
    
    def is_low_stock(self):
        return self.stock <= self.threshold_limit
    
    def can_add_more_products(self):
        current_count = ResellerProduct.objects.filter(store=self.store, is_active=True).count()
        max_allowed = self.store.get_max_products()
        return current_count < max_allowed
    
    def get_display_price(self):
        return self.get_effective_price()
        
    def __str__(self):
        brand_str = f"{self.brand} " if self.brand else ""
        status_mark = "⚠️ " if self.has_price_change_pending() else ""
        stock_status = " [Low Stock]" if self.is_low_stock() else ""
        discount_status = f" [{self.discount_percentage}% OFF]" if self.discount_percentage > 0 else ""
        return f"{status_mark}{brand_str}{self.name} - ₹{self.get_effective_price()}{discount_status}{stock_status}"


class ResellerProductImage(models.Model):
    product = models.ForeignKey(ResellerProduct, on_delete=models.CASCADE, related_name='additional_images')
    image = models.ImageField(upload_to='reseller/products/gallery/')
    alt_text = models.CharField(max_length=200, blank=True)
    order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['order']


class ResellerProductVariant(models.Model):
    product = models.ForeignKey(ResellerProduct, on_delete=models.CASCADE, related_name='variants')
    source_variant = models.ForeignKey(WholesellerProductVariant, on_delete=models.SET_NULL, null=True, blank=True)
    
    size = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=50, blank=True)
    variant_name = models.CharField(max_length=200, blank=True)
    
    source_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    margin_rupees = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    
    # DISCOUNT FIELDS
    discount_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    discounted_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    
    stock = models.IntegerField(default=0, validators=[MinValueValidator(0)], help_text="Auto-synced for imported variants")
    threshold_limit = models.IntegerField(default=5, validators=[MinValueValidator(0)])
    
    sku = models.CharField(
        max_length=100, 
        blank=True, 
        default=generate_default_reseller_variant_sku
    )
    hsn_code = models.CharField(max_length=20, default='0000', help_text="HSN Code for GST classification")
    main_image = models.ImageField(upload_to='reseller/variants/main/', blank=True, null=True)
    
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    weight = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    length = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    breadth = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    height = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    is_returnable = models.BooleanField(default=False)
    return_window_days = models.PositiveIntegerField(default=3)

    is_replaceable = models.BooleanField(default=False)
    replacement_window_days = models.PositiveIntegerField(default=3)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'variant_name']
        indexes = [
            models.Index(fields=['source_variant', 'stock']),
            models.Index(fields=['product', 'is_active']),
            models.Index(fields=['sku']),
        ]
    
    def generate_reseller_variant_sku(self):
        """Generate unique SKU for reseller variant"""
        parent_sku = self.product.sku if self.product.sku else f"RP-{self.product.id}"
        
        variant_parts = []
        if self.size:
            variant_parts.append(self.size.upper())
        if self.color:
            variant_parts.append(self.color.upper())
        
        variant_suffix = '-'.join(variant_parts) if variant_parts else 'VAR'
        random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        sku = f"{parent_sku}-{variant_suffix}-{random_suffix}"
        
        while ResellerProductVariant.objects.filter(sku=sku).exists():
            random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            sku = f"{parent_sku}-{variant_suffix}-{random_suffix}"
        
        return sku
    
    def calculate_discounted_price(self):
        """Calculate discounted price based on discount percentage"""
        if self.discount_percentage > 0:
            discount_amount = (self.selling_price * self.discount_percentage) / 100
            return self.selling_price - discount_amount
        return self.selling_price
    
    def get_effective_price(self):
        """Get the effective price after discount"""
        if self.discounted_price:
            return self.discounted_price
        return self.calculate_discounted_price()
    
    def save(self, *args, **kwargs):
        # ================= VARIANT NAME =================
        if not self.variant_name:
            parts = []
            if self.size:
                parts.append(self.size)
            if self.color:
                parts.append(self.color)
            self.variant_name = " - ".join(parts) if parts else "Default"

        # ================= IMPORTED VARIANT =================
        if self.source_variant and self.product.source_type == 'imported':
            is_new = self.pk is None

            # STOCK SYNC
            self.stock = self.source_variant.stock
            
            # SYNC SKU AND HSN FROM SOURCE VARIANT
            if self.source_variant.sku:
                self.sku = self.source_variant.sku
            if self.source_variant.hsn_code:
                self.hsn_code = self.source_variant.hsn_code

            # SYNC DISCOUNT FIELDS
            self.discount_percentage = self.source_variant.discount_percentage

            # IMPORTANT: Get effective price (after discount) from source variant
            variant_effective_price = self.source_variant.get_effective_price()
            
            # PRICE SYNC - Store original price for reference
            self.source_price = self.source_variant.price
            # Selling price = effective price (after discount) + margin
            self.selling_price = variant_effective_price + self.margin_rupees

            # RECALCULATE DISCOUNTED PRICE
            if self.discount_percentage > 0:
                discount_amount = (self.selling_price * self.discount_percentage) / 100
                self.discounted_price = self.selling_price - discount_amount
            else:
                self.discounted_price = self.selling_price

            # SHIPPING SYNC
            self.weight = self.source_variant.weight
            self.length = self.source_variant.length
            self.breadth = self.source_variant.breadth
            self.height = self.source_variant.height

            # RETURN SYNC
            self.is_returnable = self.source_variant.is_returnable
            self.return_window_days = self.source_variant.return_window_days
            self.is_replaceable = self.source_variant.is_replaceable
            self.replacement_window_days = self.source_variant.replacement_window_days

        # ================= OWN VARIANT =================
        else:
            # Own variant must have selling price
            if not self.selling_price:
                raise ValueError("Selling price is required for own variants")
            
            # Generate proper SKU only for own variants
            if not self.sku or (self.sku and 'TEMP' in self.sku):
                self.sku = self.generate_reseller_variant_sku()
            
            # Set default HSN code (inherit from parent if available)
            if not self.hsn_code or self.hsn_code == '0000':
                if self.product and self.product.hsn_code:
                    self.hsn_code = self.product.hsn_code
                else:
                    self.hsn_code = '0000'
            
            # Calculate discounted price for own variant
            self.discounted_price = self.calculate_discounted_price()

        # ================= FINAL SAVE =================
        super().save(*args, **kwargs)

        # ================= POST SAVE STOCK UPDATE =================
        if self.product.source_type == 'own':
            self.product._update_stock_from_variants()
        
    def is_low_stock(self):
        return self.stock <= self.threshold_limit
    
    def __str__(self):
        stock_status = " [Low Stock]" if self.is_low_stock() else ""
        discount_status = f" [{self.discount_percentage}% OFF]" if self.discount_percentage > 0 else ""
        return f"{self.product.name} - {self.variant_name} (₹{self.get_effective_price()}){discount_status}{stock_status}"


class ResellerVariantImage(models.Model):
    variant = models.ForeignKey(ResellerProductVariant, on_delete=models.CASCADE, related_name='additional_images')
    image = models.ImageField(upload_to='reseller/variants/gallery/')
    alt_text = models.CharField(max_length=200, blank=True)
    order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['order']


class PriceChangeNotification(models.Model):
    NOTIFICATION_TYPES = [
        ('product_price_increase', 'Product Price Increased'),
        ('product_price_decrease', 'Product Price Decreased'),
        ('variant_price_increase', 'Variant Price Increased'),
        ('variant_price_decrease', 'Variant Price Decreased'),
        ('stock_out', 'Product Out of Stock'),
        ('low_stock', 'Product Low on Stock'),
    ]

    reseller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    store = models.ForeignKey('resellers.Store', on_delete=models.CASCADE)

    reseller_product = models.ForeignKey(
        ResellerProduct, on_delete=models.CASCADE, related_name='price_notifications'
    )

    reseller_variant = models.ForeignKey(
        ResellerProductVariant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='price_notifications'
    )

    notification_type = models.CharField(max_length=40, choices=NOTIFICATION_TYPES)

    old_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    new_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    old_selling_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    new_selling_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    message = models.TextField()

    is_read = models.BooleanField(default=False)
    is_actioned = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['reseller', 'is_read']),
            models.Index(fields=['store', 'created_at']),
        ]

    def is_increase(self):
        if self.old_price and self.new_price:
            return self.new_price > self.old_price
        return False

    def get_difference(self):
        if self.old_selling_price and self.new_selling_price:
            return self.new_selling_price - self.old_selling_price
        return 0
    
    def __str__(self):
        return f"Price change for {self.reseller_product.name} - {self.created_at}"