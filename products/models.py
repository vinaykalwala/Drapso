# products/models.py
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils.text import slugify
from django.utils import timezone
import random
import string

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
    
    stock = models.IntegerField(default=0, validators=[MinValueValidator(0)], help_text="Total stock ")
    threshold_limit = models.IntegerField(default=5, validators=[MinValueValidator(0)], help_text="Alert when stock below this")
    
    main_image = models.ImageField(upload_to='wholeseller/products/main/')
    
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def save(self, *args, **kwargs):
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
        
        if self.pk:
            total_stock = sum(variant.stock for variant in self.variants.all())
            self.stock = total_stock
        
        super().save(*args, **kwargs)
    
    def update_stock(self):
        total = sum(variant.stock for variant in self.variants.all())
        self.stock = total
        self.save(update_fields=['stock'])
    
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
        return f"{brand_str}{self.name} - ₹{self.price}{stock_status}"


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
    
    stock = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    threshold_limit = models.IntegerField(default=5, validators=[MinValueValidator(0)])
    
    sku = models.CharField(max_length=100, blank=True, unique=True)
    main_image = models.ImageField(upload_to='wholeseller/variants/main/', blank=True, null=True)
    
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'variant_name']
    
    def save(self, *args, **kwargs):
        if self.pk:
            old_price = WholesellerProductVariant.objects.filter(pk=self.pk).values_list('price', flat=True).first()
            if old_price is not None and old_price != self.price:
                self.previous_price = old_price
                self.price_updated_at = timezone.now()
        
        if not self.sku:
            random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            self.sku = f"WV{self.product.id}{random_str}"
        
        if not self.variant_name:
            parts = []
            if self.size:
                parts.append(self.size)
            if self.color:
                parts.append(self.color)
            self.variant_name = " - ".join(parts) if parts else "Default"
        
        super().save(*args, **kwargs)
        self.product.update_stock()
    
    def is_low_stock(self):
        return self.stock <= self.threshold_limit
    
    def get_display_price(self):
        return self.price
    
    def __str__(self):
        stock_status = " [Low Stock]" if self.is_low_stock() else ""
        return f"{self.product.name} - {self.variant_name} (₹{self.price}){stock_status}"


class WholesellerVariantImage(models.Model):
    variant = models.ForeignKey(WholesellerProductVariant, on_delete=models.CASCADE, related_name='additional_images')
    image = models.ImageField(upload_to='wholeseller/variants/gallery/')
    alt_text = models.CharField(max_length=200, blank=True)
    order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['order']

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
    
    last_known_source_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_status = models.CharField(max_length=30, choices=PRICE_STATUS_CHOICES, default='up_to_date')
    price_change_notified_at = models.DateTimeField(null=True, blank=True)
    price_reviewed_at = models.DateTimeField(null=True, blank=True)
    
    stock = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    threshold_limit = models.IntegerField(default=5, validators=[MinValueValidator(0)])
    
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='own')
    
    main_image = models.ImageField(upload_to='reseller/products/main/', blank=True, null=True)
    
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    is_published = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['store', 'slug']
    
    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            self.slug = base_slug
            counter = 1
            while ResellerProduct.objects.filter(store=self.store, slug=self.slug).exists():
                self.slug = f"{base_slug}-{counter}"
                counter += 1
        
        if self.source_type == 'imported' and self.source_product:
            # Check if this is a NEW product (no pk yet) or existing
            is_new = self.pk is None
            
            if not is_new:
                # Only check for price changes on existing products
                if self.source_price != self.source_product.price:
                    self.last_known_source_price = self.source_price
                    self.price_status = 'price_increased' if self.source_product.price > self.source_price else 'price_decreased'
                    self.price_change_notified_at = timezone.now()
            
            self.source_price = self.source_product.price
            self.selling_price = self.source_price + self.margin_rupees
            
            # Copy product attributes
            self.brand = self.source_product.brand
            self.model_name = self.source_product.model_name
            self.size = self.source_product.size
            self.color = self.source_product.color
            self.material = self.source_product.material
            self.gender = self.source_product.gender
            self.attributes = self.source_product.attributes
            self.specification = self.source_product.specification
            self.threshold_limit = self.source_product.threshold_limit
            
            # For new products, set price_status to up_to_date
            if is_new:
                self.price_status = 'up_to_date'
                self.last_known_source_price = self.source_price
        
        super().save(*args, **kwargs)
    
    def update_stock(self):
        total = sum(variant.stock for variant in self.variants.all())
        self.stock = total
        self.save(update_fields=['stock'])
    
    def has_price_change_pending(self):
        return self.price_status in ['price_increased', 'price_decreased']
    
    def get_price_difference(self):
        if self.last_known_source_price:
            return self.source_price - self.last_known_source_price
        return 0
    
    def get_new_selling_price(self):
        return self.source_price + self.margin_rupees
    
    def get_old_selling_price(self):
        return self.last_known_source_price + self.margin_rupees if self.last_known_source_price else self.selling_price
    
    def apply_price_update(self):
        self.selling_price = self.get_new_selling_price()
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
        return self.selling_price
        
    def __str__(self):
        brand_str = f"{self.brand} " if self.brand else ""
        status_mark = "⚠️ " if self.has_price_change_pending() else ""
        stock_status = " [Low Stock]" if self.is_low_stock() else ""
        return f"{status_mark}{brand_str}{self.name} - ₹{self.selling_price}{stock_status}"

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
    
    stock = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    threshold_limit = models.IntegerField(default=5, validators=[MinValueValidator(0)])
    
    sku = models.CharField(max_length=100, blank=True)
    main_image = models.ImageField(upload_to='reseller/variants/main/', blank=True, null=True)
    
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'variant_name']
    
    def save(self, *args, **kwargs):
        if self.source_variant:
            self.source_price = self.source_variant.price
            self.selling_price = self.source_price + self.margin_rupees
            self.size = self.source_variant.size
            self.color = self.source_variant.color
            self.variant_name = self.source_variant.variant_name
            self.threshold_limit = self.source_variant.threshold_limit
        
        if not self.sku and self.product:
            self.sku = f"RV{self.product.id}{self.order}"
        
        super().save(*args, **kwargs)
        self.product.update_stock()
    
    def is_low_stock(self):
        return self.stock <= self.threshold_limit
    
    def __str__(self):
        stock_status = " [Low Stock]" if self.is_low_stock() else ""
        return f"{self.product.name} - {self.variant_name} (₹{self.selling_price}){stock_status}"


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
    ]
    
    reseller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='price_notifications')
    store = models.ForeignKey('resellers.Store', on_delete=models.CASCADE, related_name='price_notifications')
    reseller_product = models.ForeignKey(ResellerProduct, on_delete=models.CASCADE, related_name='price_notifications')
    
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES)
    
    old_price = models.DecimalField(max_digits=10, decimal_places=2)
    new_price = models.DecimalField(max_digits=10, decimal_places=2)
    old_selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    new_selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    is_actioned = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Price change for {self.reseller_product.name} - {self.created_at}"