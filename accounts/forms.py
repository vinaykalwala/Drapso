from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.core.validators import RegexValidator
from .models import User, WholesellerProfile, ResellerProfile, AdminProfile
import re

class PhoneNumberField(forms.CharField):
    def validate(self, value):
        super().validate(value)
        if not re.match(r'^\+?1?\d{9,15}$', value):
            raise forms.ValidationError("Enter a valid phone number (10-15 digits)")

class BaseSignupForm(forms.Form):
    first_name = forms.CharField(max_length=50, widget=forms.TextInput(attrs={'class': 'form-control'}))
    middle_name = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=50, widget=forms.TextInput(attrs={'class': 'form-control'}))
    phone = PhoneNumberField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+1234567890'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))
    username = forms.CharField(max_length=50, widget=forms.TextInput(attrs={'class': 'form-control'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Email already exists")
        return email
    
    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Username already exists")
        return username
    
    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if User.objects.filter(phone=phone).exists():
            raise forms.ValidationError("Phone number already exists")
        return phone
    
    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        
        if password and confirm_password and password != confirm_password:
            raise forms.ValidationError("Passwords do not match")
        
        if password and len(password) < 8:
            raise forms.ValidationError("Password must be at least 8 characters")
        
        return cleaned_data

class WholesellerSignupForm(BaseSignupForm):
    # Business Information
    business_name = forms.CharField(max_length=200, widget=forms.TextInput(attrs={'class': 'form-control'}))
    business_type = forms.ChoiceField(
        choices=WholesellerProfile.BUSINESS_TYPES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    business_registration_number = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control'}))
    tax_id = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    gst_number = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    
    # Contact Information
    business_phone = PhoneNumberField(widget=forms.TextInput(attrs={'class': 'form-control'}))
    business_email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))
    website = forms.URLField(required=False, widget=forms.URLInput(attrs={'class': 'form-control'}))
    
    # Address
    business_address = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))
    city = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control'}))
    state = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control'}))
    country = forms.CharField(max_length=100, initial='India', widget=forms.TextInput(attrs={'class': 'form-control'}))
    postal_code = forms.CharField(max_length=20, widget=forms.TextInput(attrs={'class': 'form-control'}))
    
    # Business Details
    years_in_business = forms.IntegerField(min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    number_of_employees = forms.IntegerField(min_value=1, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    annual_turnover = forms.DecimalField(max_digits=15, decimal_places=2, required=False, 
                                        widget=forms.NumberInput(attrs={'class': 'form-control'}))
    
    description = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}), required=False)
    
    def clean_business_registration_number(self):
        reg_no = self.cleaned_data.get('business_registration_number')
        if WholesellerProfile.objects.filter(business_registration_number=reg_no).exists():
            raise forms.ValidationError("Business registration number already exists")
        return reg_no

class ResellerSignupForm(BaseSignupForm):
    # Business Information
    company_name = forms.CharField(max_length=200, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    reseller_type = forms.ChoiceField(
        choices=ResellerProfile.RESELLER_TYPES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    tax_id = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    
    # Contact Information
    business_phone = PhoneNumberField(widget=forms.TextInput(attrs={'class': 'form-control'}))
    business_email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))
    
    # Address
    business_address = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))
    city = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control'}))
    state = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control'}))
    country = forms.CharField(max_length=100, initial='India', widget=forms.TextInput(attrs={'class': 'form-control'}))
    postal_code = forms.CharField(max_length=20, widget=forms.TextInput(attrs={'class': 'form-control'}))
    
    
class AdminSignupForm(BaseSignupForm):
    # Employee Information
    employee_id = forms.CharField(max_length=50, widget=forms.TextInput(attrs={'class': 'form-control'}))
    department = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control'}))
    designation = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control'}))
    
    # Contact Information
    office_phone = PhoneNumberField(widget=forms.TextInput(attrs={'class': 'form-control'}))
    emergency_contact = PhoneNumberField(widget=forms.TextInput(attrs={'class': 'form-control'}))
    
    # Address
    office_address = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))
    city = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control'}))
    state = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control'}))
    country = forms.CharField(max_length=100, initial='India', widget=forms.TextInput(attrs={'class': 'form-control'}))
    postal_code = forms.CharField(max_length=20, widget=forms.TextInput(attrs={'class': 'form-control'}))
    
    # Permissions
    permissions_level = forms.ChoiceField(
        choices=[(1, 'Basic Admin'), (2, 'Manager'), (3, 'Super Admin')],
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    can_manage_users = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    can_manage_products = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    can_manage_orders = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    can_view_reports = forms.BooleanField(initial=True, required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    
    def clean_employee_id(self):
        emp_id = self.cleaned_data.get('employee_id')
        if AdminProfile.objects.filter(employee_id=emp_id).exists():
            raise forms.ValidationError("Employee ID already exists")
        return emp_id

class OTPVerificationForm(forms.Form):
    otp = forms.CharField(max_length=6, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter 6-digit OTP'}))

class LoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username or Email'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}))

class ForgotPasswordForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Enter your email'}))

class ResetPasswordForm(forms.Form):
    otp = forms.CharField(max_length=6, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter OTP'}))
    new_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'New Password'}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm Password'}))
    
    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')
        
        if new_password and confirm_password and new_password != confirm_password:
            raise forms.ValidationError("Passwords do not match")
        
        if new_password and len(new_password) < 8:
            raise forms.ValidationError("Password must be at least 8 characters")
        
        return cleaned_data