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


# In forms.py - Add these forms

class UserProfileForm(forms.ModelForm):
    """Form for editing base user information"""
    class Meta:
        model = User
        fields = ['first_name', 'middle_name', 'last_name', 'phone']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'middle_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make all fields optional for display
        for field in self.fields:
            self.fields[field].required = False

class WholesellerFullProfileForm(forms.ModelForm):
    """Complete form for wholeseller profile"""
    class Meta:
        model = WholesellerProfile
        exclude = ['user', 'created_at', 'updated_at', 'is_approved', 'approved_at']
        widgets = {
            'business_name': forms.TextInput(attrs={'class': 'form-control'}),
            'business_type': forms.Select(attrs={'class': 'form-control'}),
            'business_registration_number': forms.TextInput(attrs={'class': 'form-control'}),
            'tax_id': forms.TextInput(attrs={'class': 'form-control'}),
            'gst_number': forms.TextInput(attrs={'class': 'form-control'}),
            'business_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'business_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'website': forms.URLInput(attrs={'class': 'form-control'}),
            'business_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'state': forms.TextInput(attrs={'class': 'form-control'}),
            'country': forms.TextInput(attrs={'class': 'form-control'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'years_in_business': forms.NumberInput(attrs={'class': 'form-control'}),
            'number_of_employees': forms.NumberInput(attrs={'class': 'form-control'}),
            'annual_turnover': forms.NumberInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'avatar': forms.FileInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make all fields optional for display
        for field in self.fields:
            self.fields[field].required = False

class ResellerFullProfileForm(forms.ModelForm):
    """Complete form for reseller profile"""
    class Meta:
        model = ResellerProfile
        exclude = ['user', 'created_at', 'updated_at', 'is_approved', 'approved_at', 'reseller_code']
        widgets = {
            'company_name': forms.TextInput(attrs={'class': 'form-control'}),
            'reseller_type': forms.Select(attrs={'class': 'form-control'}),
            'tax_id': forms.TextInput(attrs={'class': 'form-control'}),
            'business_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'business_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'business_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'state': forms.TextInput(attrs={'class': 'form-control'}),
            'country': forms.TextInput(attrs={'class': 'form-control'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'commission_rate': forms.NumberInput(attrs={'class': 'form-control'}),
            'avatar': forms.FileInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make all fields optional for display
        for field in self.fields:
            self.fields[field].required = False

class AdminFullProfileForm(forms.ModelForm):
    """Complete form for admin profile"""
    class Meta:
        model = AdminProfile
        exclude = ['user', 'created_at', 'updated_at', 'joining_date']
        widgets = {
            'employee_id': forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
            'department': forms.TextInput(attrs={'class': 'form-control'}),
            'designation': forms.TextInput(attrs={'class': 'form-control'}),
            'office_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'emergency_contact': forms.TextInput(attrs={'class': 'form-control'}),
            'office_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'state': forms.TextInput(attrs={'class': 'form-control'}),
            'country': forms.TextInput(attrs={'class': 'form-control'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'avatar': forms.FileInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make all fields optional for display
        for field in self.fields:
            self.fields[field].required = False

from .models import BankAccount, WholesellerAddress, ResellerAddress

class BankAccountForm(forms.ModelForm):
    """Form for adding/editing bank account"""
    class Meta:
        model = BankAccount
        fields = ['account_holder_name', 'account_number', 'confirm_account_number', 
                  'bank_name', 'ifsc_code', 'branch_name', 'account_type', 'upi_id', 'is_primary']
        widgets = {
            'account_holder_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Name as in bank account'}),
            'account_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Account number'}),
            'confirm_account_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Confirm account number'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Bank name'}),
            'ifsc_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'IFSC code'}),
            'branch_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Branch name'}),
            'account_type': forms.Select(attrs={'class': 'form-control'}),
            'upi_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'UPI ID (optional)'}),
            'is_primary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def clean_account_number(self):
        account_number = self.cleaned_data.get('account_number')
        if account_number:
            account_number = account_number.replace(' ', '')
            if not account_number.isdigit():
                raise forms.ValidationError('Account number must contain only digits')
            if len(account_number) < 9 or len(account_number) > 18:
                raise forms.ValidationError('Account number must be between 9 and 18 digits')
        return account_number
    
    def clean_ifsc_code(self):
        ifsc = self.cleaned_data.get('ifsc_code')
        if ifsc:
            ifsc = ifsc.upper().replace(' ', '')
            if len(ifsc) != 11:
                raise forms.ValidationError('IFSC code must be 11 characters')
        return ifsc
    
    def clean(self):
        cleaned_data = super().clean()
        account_number = cleaned_data.get('account_number')
        confirm_account_number = cleaned_data.get('confirm_account_number')
        
        if account_number and confirm_account_number and account_number != confirm_account_number:
            raise forms.ValidationError('Account numbers do not match')
        
        return cleaned_data

class WholesellerAddressForm(forms.ModelForm):
    """Form for wholeseller address"""
    class Meta:
        model = WholesellerAddress
        fields = ['address_name', 'address_line1', 'address_line2', 'city', 'state', 
                  'country', 'postal_code', 'contact_person', 'contact_phone', 'is_primary', 'is_active']
        widgets = {
            'address_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Main Warehouse'}),
            'address_line1': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Street address'}),
            'address_line2': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Apartment, suite, etc. (optional)'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City'}),
            'state': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'State'}),
            'country': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Country'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Postal code'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contact person name'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contact phone number'}),
            'is_primary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ResellerAddressForm(forms.ModelForm):
    """Form for reseller address"""
    class Meta:
        model = ResellerAddress
        fields = ['address_line1', 'address_line2', 'city', 'state', 'country', 
                  'postal_code', 'contact_person', 'contact_phone', 'is_primary']
        widgets = {
            'address_line1': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Street address'}),
            'address_line2': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Apartment, suite, etc. (optional)'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City'}),
            'state': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'State'}),
            'country': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Country'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Postal code'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contact person name'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contact phone number'}),
            'is_primary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }