# theme_manager/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone

class ThemeSwitchSession(models.Model):
    """Tracks theme state for each store - NO FK to avoid circular imports"""
    
    THEME_CHOICES = [
        ('single', 'Single Product Theme'),
        ('multiple', 'Multiple Products Theme'),
    ]
    
    store_id = models.IntegerField(db_index=True)
    reseller_id = models.IntegerField(db_index=True)
    
    current_theme = models.CharField(max_length=20, choices=THEME_CHOICES, default='multiple')
    active_product_id = models.IntegerField(null=True, blank=True)
    
    last_switch_at = models.DateTimeField(null=True, blank=True)
    switch_count_month = models.IntegerField(default=0)
    switch_month = models.CharField(max_length=7, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'theme_manager_session'
        indexes = [
            models.Index(fields=['store_id']),
            models.Index(fields=['reseller_id']),
        ]
    
    def __str__(self):
        return f"Store {self.store_id} - {self.current_theme}"


class ArchivedProductRecord(models.Model):
    """Archive record - just references existing product via FK"""
    
    REASON_CHOICES = [
        ('theme_switch', 'Theme Switch'),
        ('plan_limit', 'Plan Limit Exceeded'),
        ('manual', 'Manually Archived'),
    ]
    
    product = models.ForeignKey(
        'products.ResellerProduct',
        on_delete=models.CASCADE,
        related_name='archive_records'
    )
    
    store = models.ForeignKey(
        'resellers.Store',
        on_delete=models.CASCADE,
        related_name='archived_products'
    )
    
    archive_reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    archived_at = models.DateTimeField(auto_now_add=True)
    is_restorable = models.BooleanField(default=True)
    
    # Priority for restoration (higher = more important)
    restore_priority = models.IntegerField(default=0)
    
    class Meta:
        db_table = 'theme_manager_archived_products'
        unique_together = ['product', 'store']
        indexes = [
            models.Index(fields=['store', 'is_restorable']),
            models.Index(fields=['store', '-restore_priority']),
            models.Index(fields=['product', 'store']),
        ]
    
    def restore(self):
        """Restore this product - preserves all original data including published status"""
        self.product.is_active = True
        self.product.save(update_fields=['is_active', 'updated_at'])
        self.delete()
        return self.product
    
    def __str__(self):
        return f"Archived: {self.product.name} (Store: {self.store_id})"


class ThemeSwitchHistory(models.Model):
    """Audit log for theme switches"""
    
    store_id = models.IntegerField()
    reseller_id = models.IntegerField()
    
    from_theme = models.CharField(max_length=20)
    to_theme = models.CharField(max_length=20)
    
    products_active_before = models.IntegerField()
    products_active_after = models.IntegerField()
    products_archived = models.IntegerField()
    products_restored = models.IntegerField()
    
    reason = models.CharField(max_length=50)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'theme_manager_history'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['store_id']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"Store {self.store_id}: {self.from_theme} → {self.to_theme}"


class RestoreBatch(models.Model):
    """Track batch restore operations"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('partial', 'Partially Completed'),
        ('failed', 'Failed'),
    ]
    
    store = models.ForeignKey('resellers.Store', on_delete=models.CASCADE)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    selected_product_ids = models.JSONField(default=list)
    
    restored_count = models.IntegerField(default=0)
    skipped_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    
    skipped_items = models.JSONField(default=list)
    failed_items = models.JSONField(default=list)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    plan_name_at_restore = models.CharField(max_length=50, blank=True)
    plan_limit_at_restore = models.IntegerField(default=0)
    active_products_at_restore = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'theme_manager_restore_batches'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Batch {self.id} - Store {self.store_id} - {self.status}"