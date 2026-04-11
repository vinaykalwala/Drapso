
from django import forms
from .models import WholesellerInventory, WholesellerKYC

# accounts/forms.py - Add these at the end

from .models import WholesellerInventory, WholesellerKYC

class WholesellerInventoryForm(forms.ModelForm):
    """Form for creating inventory/business info"""
    
    class Meta:
        model = WholesellerInventory
        fields = [
            'business_name', 'business_type',
            'warehouse_name', 'address_line1', 'address_line2', 
            'city', 'state', 'country', 'postal_code',
            'contact_person', 'contact_phone', 'contact_email','delivery_type'
        ]
        widgets = {
            'business_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your Business Name'}),
            'warehouse_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Main Warehouse'}),
            'address_line1': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Street address'}),
            'address_line2': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Apartment, suite, etc. (optional)'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City'}),
            'state': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'State'}),
            'country': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Country'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Postal Code'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contact Person Name'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'}),
            'contact_email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'}),
            'delivery_type': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add form-control class to all fields
        for field in self.fields:
            if 'class' not in self.fields[field].widget.attrs:
                self.fields[field].widget.attrs.update({'class': 'form-control'})
    
    def clean_contact_phone(self):
        phone = self.cleaned_data.get('contact_phone')
        if phone and len(phone) < 10:
            raise forms.ValidationError("Phone number must be at least 10 digits")
        return phone


class WholesellerKYCForm(forms.ModelForm):
    """Form for submitting KYC documents"""
    
    class Meta:
        model = WholesellerKYC
        fields = [
            'gst_certificate', 'pan_card', 'address_proof', 
            'business_registration', 'warehouse_photo',
            'gst_number', 'pan_number', 'years_in_business', 'annual_turnover'
        ]
        widgets = {
            'years_in_business': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Number of years in business'}),
            'annual_turnover': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Annual turnover in INR'}),
            'gst_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '15-character GST number'}),
            'pan_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '10-character PAN number'}),
        }
    
    def clean_gst_number(self):
        gst = self.cleaned_data.get('gst_number')
        if gst:
            gst = gst.upper().strip()
            if len(gst) != 15:
                raise forms.ValidationError("GST number must be 15 characters")
        return gst
    
    def clean_pan_number(self):
        pan = self.cleaned_data.get('pan_number')
        if pan:
            pan = pan.upper().strip()
            if len(pan) != 10:
                raise forms.ValidationError("PAN number must be 10 characters")
        return pan
    
    def clean(self):
        cleaned_data = super().clean()
        # Ensure all required documents are uploaded for submission
        required_docs = ['gst_certificate', 'pan_card', 'address_proof', 'business_registration', 'warehouse_photo']
        missing_docs = []
        
        for doc in required_docs:
            if not cleaned_data.get(doc):
                missing_docs.append(doc.replace('_', ' ').title())
        
        if missing_docs:
            raise forms.ValidationError(f"Please upload the following documents: {', '.join(missing_docs)}")
        
        return cleaned_data
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            if hasattr(self.fields[field], 'widget'):
                self.fields[field].widget.attrs.update({'class': 'form-control'})