from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
import random
import string

class UserManager(BaseUserManager):
    def create_user(self, email, username, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        if not username:
            raise ValueError('Username is required')
        
        email = self.normalize_email(email)
        user = self.model(email=email, username=username, **extra_fields)
        if password:
            user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_verified', True)
        extra_fields.setdefault('role', User.Role.ADMIN)
        
        return self.create_user(email, username, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        CUSTOMER = 'customer', 'Customer'
        WHOLESELLER = 'wholeseller', 'Wholeseller'
        RESELLER = 'reseller', 'Reseller'
        ADMIN = 'admin', 'Admin'
    
    # Basic Information
    first_name = models.CharField(max_length=50)
    middle_name = models.CharField(max_length=50, blank=True, null=True)
    last_name = models.CharField(max_length=50)
    phone = models.CharField(max_length=15, unique=True)
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=50, unique=True)
    
    # Role
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)
    
    # Status
    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(null=True, blank=True)
    
    # OTP Fields
    otp = models.CharField(max_length=6, blank=True, null=True)
    otp_created_at = models.DateTimeField(blank=True, null=True)
    
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email', 'first_name', 'last_name', 'phone']
    
    objects = UserManager()
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
    
    def generate_otp(self):
        self.otp = ''.join(random.choices(string.digits, k=6))
        self.otp_created_at = timezone.now()
        self.save()
        return self.otp
    
    def verify_otp(self, otp):
        if self.otp and self.otp == otp:
            if self.otp_created_at:
                time_diff = timezone.now() - self.otp_created_at
                if time_diff.total_seconds() <= 600:
                    return True
        return False
    
    def clear_otp(self):
        self.otp = None
        self.otp_created_at = None
        self.save()
    
    @property
    def full_name(self):
        if self.middle_name:
            return f"{self.first_name} {self.middle_name} {self.last_name}"
        return f"{self.first_name} {self.last_name}"

class CustomerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='customer_profile')
    
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=[
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other')
    ], blank=True)
    billing_address = models.TextField(blank=True)
    shipping_address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default='India')
    postal_code = models.CharField(max_length=20, blank=True)
    newsletter_subscribed = models.BooleanField(default=False)
    preferred_language = models.CharField(max_length=10, default='en')
    avatar = models.ImageField(upload_to='customers/avatars/', blank=True, null=True)
    loyalty_points = models.IntegerField(default=0)
    total_orders = models.IntegerField(default=0)
    total_spent = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Customer Profile: {self.user.username}"

class WholesellerProfile(models.Model):
    BUSINESS_TYPES = [
        ('retail', 'Retail Store'),
        ('distributor', 'Distributor'),
        ('manufacturer', 'Manufacturer'),
        ('importer', 'Importer'),
        ('exporter', 'Exporter'),
        ('other', 'Other')
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wholeseller_profile')
    
    business_name = models.CharField(max_length=200)
    business_type = models.CharField(max_length=20, choices=BUSINESS_TYPES)
    business_registration_number = models.CharField(max_length=100, unique=True)
    tax_id = models.CharField(max_length=100, blank=True)
    gst_number = models.CharField(max_length=50, blank=True)
    business_phone = models.CharField(max_length=15)
    business_email = models.EmailField()
    website = models.URLField(blank=True)
    business_address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default='India')
    postal_code = models.CharField(max_length=20)
    registration_certificate = models.FileField(upload_to='wholeseller/documents/', blank=True)
    years_in_business = models.IntegerField(default=0)
    number_of_employees = models.IntegerField(default=0)
    annual_turnover = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    is_approved = models.BooleanField(default=False)
    approved_at = models.DateTimeField(null=True, blank=True)
    avatar = models.ImageField(upload_to='wholeseller/avatars/', blank=True, null=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Wholeseller: {self.business_name}"

class ResellerProfile(models.Model):
    RESELLER_TYPES = [
        ('individual', 'Individual Reseller'),
        ('company', 'Reseller Company'),
        ('affiliate', 'Affiliate Marketer'),
        ('distributor', 'Distributor')
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='reseller_profile')
    
    company_name = models.CharField(max_length=200, blank=True)
    reseller_type = models.CharField(max_length=20, choices=RESELLER_TYPES)
    reseller_code = models.CharField(max_length=50, unique=True, blank=True)
    tax_id = models.CharField(max_length=100, blank=True)
    business_phone = models.CharField(max_length=15)
    business_email = models.EmailField()
    business_address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default='India')
    postal_code = models.CharField(max_length=20)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total_sales = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_commission_earned = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    number_of_referrals = models.IntegerField(default=0)
    is_approved = models.BooleanField(default=False)
    approved_at = models.DateTimeField(null=True, blank=True)
    avatar = models.ImageField(upload_to='reseller/avatars/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        if not self.reseller_code:
            self.reseller_code = f"RES{timezone.now().strftime('%Y%m%d')}{random.randint(1000, 9999)}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Reseller: {self.company_name or self.user.username}"

class AdminProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='admin_profile')
    
    employee_id = models.CharField(max_length=50, unique=True)
    department = models.CharField(max_length=100)
    designation = models.CharField(max_length=100)
    office_phone = models.CharField(max_length=15)
    emergency_contact = models.CharField(max_length=15)
    office_address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default='India')
    postal_code = models.CharField(max_length=20)
    permissions_level = models.IntegerField(default=1)
    can_manage_users = models.BooleanField(default=False)
    can_manage_products = models.BooleanField(default=False)
    can_manage_orders = models.BooleanField(default=False)
    can_view_reports = models.BooleanField(default=True)
    id_proof = models.FileField(upload_to='admin/documents/', blank=True)
    avatar = models.ImageField(upload_to='admin/avatars/', blank=True, null=True)
    joining_date = models.DateField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Admin: {self.user.username} ({self.designation})"