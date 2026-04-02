# wholesellers/models.py

from django.db import models
from django.conf import settings

class WholesellerInventory(models.Model):
    """Model for wholeseller inventory/business info"""
    
    BUSINESS_TYPES = [
        ('manufacturer', 'Manufacturer'),
        ('distributor', 'Distributor'),
        ('wholesaler', 'Wholesaler'),
        ('importer', 'Importer'),
        ('retailer', 'Retailer'),
    ]
    
    wholeseller = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='inventory')
    
    # Business Information
    business_name = models.CharField(max_length=200)
    business_type = models.CharField(max_length=100, choices=BUSINESS_TYPES)
    
    # Inventory Location
    warehouse_name = models.CharField(max_length=200)
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default='India')
    postal_code = models.CharField(max_length=20)
    
    # Contact Details
    contact_person = models.CharField(max_length=100)
    contact_phone = models.CharField(max_length=15)
    contact_email = models.EmailField()
    
    # Status
    is_kyc_submitted = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.business_name} - {self.wholeseller.username}"
    
    @property
    def can_add_products(self):
        """Check if wholeseller can add products"""
        return self.is_verified
    
    @property
    def full_address(self):
        """Return full address as string"""
        address = f"{self.address_line1}"
        if self.address_line2:
            address += f", {self.address_line2}"
        address += f", {self.city}, {self.state} - {self.postal_code}, {self.country}"
        return address


class WholesellerKYC(models.Model):
    """Model for wholeseller KYC documents"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('not_submitted', 'Not Submitted'),
    ]
    
    wholeseller = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='kyc')
    
    # Required Documents
    gst_certificate = models.FileField(upload_to='wholeseller/kyc/gst/', verbose_name="GST Certificate", blank=True, null=True)
    pan_card = models.FileField(upload_to='wholeseller/kyc/pan/', verbose_name="PAN Card", blank=True, null=True)
    address_proof = models.FileField(upload_to='wholeseller/kyc/address/', verbose_name="Address Proof", blank=True, null=True)
    business_registration = models.FileField(upload_to='wholeseller/kyc/registration/', verbose_name="Business Registration Certificate", blank=True, null=True)
    warehouse_photo = models.ImageField(upload_to='wholeseller/kyc/warehouse/', verbose_name="Warehouse Photograph", blank=True, null=True)
    
    # Document Numbers (for verification)
    gst_number = models.CharField(max_length=50, blank=True)
    pan_number = models.CharField(max_length=20, blank=True)
    
    # Additional Info
    years_in_business = models.IntegerField(default=1)
    annual_turnover = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    
    # Verification Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_submitted')
    rejection_reason = models.TextField(blank=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_kyc')
    verified_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.wholeseller.username} - {self.get_status_display()}"
    
    def save(self, *args, **kwargs):
        # When KYC is approved, update the inventory verification status
        if self.status == 'approved' and not self.wholeseller.inventory.is_verified:
            self.wholeseller.inventory.is_verified = True
            self.wholeseller.inventory.save()
        super().save(*args, **kwargs)
    
    def get_documents_count(self):
        """Count uploaded documents"""
        count = 0
        if self.gst_certificate: count += 1
        if self.pan_card: count += 1
        if self.address_proof: count += 1
        if self.business_registration: count += 1
        if self.warehouse_photo: count += 1
        return count