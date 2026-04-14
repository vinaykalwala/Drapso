# resellers/forms.py

from django import forms
from django.core.exceptions import ValidationError
from .models import Store, SubscriptionPlan, StoreTheme

class StoreCreationForm(forms.ModelForm):
    """Step 1: Create store with basic details"""
    
    class Meta:
        model = Store
        fields = [
            'store_name', 'store_description', 'contact_email', 
            'contact_phone', 'store_address', 'store_logo', 'store_banner'
        ]
        widgets = {
            'store_description': forms.Textarea(attrs={
                'rows': 3, 
                'placeholder': 'Describe what your store sells...',
                'class': 'form-control'
            }),
            'store_address': forms.Textarea(attrs={
                'rows': 2, 
                'placeholder': 'Your business address',
                'class': 'form-control'
            }),
            'contact_email': forms.EmailInput(attrs={
                'placeholder': 'store@example.com',
                'class': 'form-control'
            }),
            'contact_phone': forms.TextInput(attrs={
                'placeholder': '+1234567890',
                'class': 'form-control'
            }),
            'store_name': forms.TextInput(attrs={
                'placeholder': 'myawesomestore',
                'class': 'form-control',
            }),
            'store_logo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'store_banner': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
        }
    
    def clean_store_name(self):
        store_name = self.cleaned_data.get('store_name')
        
        if Store.objects.filter(store_name__iexact=store_name).exists():
            raise ValidationError('This store name is already taken.')
        
        import re
        if not re.match(r'^[a-zA-Z]+$', store_name):
            raise ValidationError('Store name can only contain letters.')
        
        if len(store_name) < 3:
            raise ValidationError('Store name must be at least 3 characters long.')
        
        return store_name.lower()
    
    def clean_contact_email(self):
        email = self.cleaned_data.get('contact_email')
        if email:
            from django.core.validators import validate_email
            try:
                validate_email(email)
            except ValidationError:
                raise ValidationError('Enter a valid email address.')
        return email
# forms.py

from django import forms
from django.core.exceptions import ValidationError
from .models import Store
import re


class StoreEditForm(forms.ModelForm):
    """Edit store details ONLY (no plan/theme logic)"""

    class Meta:
        model = Store
        fields = [
            'store_name', 'store_description', 'contact_email',
            'contact_phone', 'store_address', 'store_logo', 'store_banner'
        ]

        widgets = {
            'store_description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control'
            }),
            'store_address': forms.Textarea(attrs={
                'rows': 2,
                'class': 'form-control'
            }),
            'contact_email': forms.EmailInput(attrs={
                'class': 'form-control'
            }),
            'contact_phone': forms.TextInput(attrs={
                'class': 'form-control'
            }),
            'store_name': forms.TextInput(attrs={
                'class': 'form-control',
            }),
            'store_logo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'store_banner': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
        }

    def clean_store_name(self):
        store_name = self.cleaned_data.get('store_name')

        if not store_name:
            return store_name

        # Match model validation (important consistency)
        if not re.match(r'^[a-zA-Z0-9-]+$', store_name):
            raise ValidationError(
                'Store name can only contain letters, numbers, and hyphens.'
            )

        if len(store_name) < 3:
            raise ValidationError('Store name must be at least 3 characters long.')

        # Exclude current instance (this is why separate form matters)
        qs = Store.objects.filter(store_name__iexact=store_name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise ValidationError('This store name is already taken.')

        return store_name.lower()

class PlanSelectionForm(forms.Form):
    """Step 2: Select subscription plan"""
    
    plan_id = forms.ModelChoiceField(
        queryset=SubscriptionPlan.objects.filter(is_active=True),
        widget=forms.RadioSelect,
        empty_label=None,
        label="Select Subscription Plan"
    )


class ThemeSelectionForm(forms.Form):
    """Step 3: Select theme (only 2 options)"""
    
    theme_id = forms.ModelChoiceField(
        queryset=StoreTheme.objects.filter(is_active=True),
        widget=forms.RadioSelect,
        empty_label=None,
        label="Select Store Theme"
    )