# orders/forms.py
from django import forms
from .models import Order, ReturnRequest, Refund

class CheckoutForm(forms.Form):
    """Checkout form for customer order creation"""
    customer_name = forms.CharField(max_length=200, widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': 'Full Name'
    }))
    customer_email = forms.EmailField(widget=forms.EmailInput(attrs={
        'class': 'form-control', 'placeholder': 'Email Address'
    }))
    customer_phone = forms.CharField(max_length=15, widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': 'Phone Number'
    }))
    shipping_address = forms.CharField(widget=forms.Textarea(attrs={
        'class': 'form-control', 'placeholder': 'Street Address', 'rows': 2
    }))
    shipping_city = forms.CharField(max_length=100, widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': 'City'
    }))
    shipping_state = forms.CharField(max_length=100, widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': 'State'
    }))
    shipping_pincode = forms.CharField(max_length=10, widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': 'Pincode'
    }))
    quantity = forms.IntegerField(min_value=1, initial=1, widget=forms.NumberInput(attrs={
        'class': 'form-control', 'min': 1
    }))


class ReturnRequestForm(forms.ModelForm):
    """Form for customers to request return"""
    
    class Meta:
        model = ReturnRequest
        fields = ['reason', 'description', 'unboxing_video', 'product_images', 
                  'account_holder_name', 'account_number', 'confirm_account_number', 
                  'ifsc_code', 'bank_name', 'upi_id']
        widgets = {
            'reason': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'unboxing_video': forms.FileInput(attrs={'class': 'form-control', 'accept': 'video/*'}),
            'product_images': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'account_holder_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Account Holder Name'}),
            'account_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Account Number'}),
            'confirm_account_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Confirm Account Number'}),
            'ifsc_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'IFSC Code'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Bank Name'}),
            'upi_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'UPI ID (Optional)'}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        account_number = cleaned_data.get('account_number')
        confirm_account_number = cleaned_data.get('confirm_account_number')
        
        if account_number and confirm_account_number:
            if account_number != confirm_account_number:
                self.add_error('confirm_account_number', 'Account numbers do not match')
        
        return cleaned_data


class RefundForm(forms.Form):
    """Admin form for processing refunds"""
    refund_amount = forms.DecimalField(max_digits=10, decimal_places=2, widget=forms.NumberInput(attrs={
        'class': 'form-control', 'step': '0.01'
    }))
    transaction_id = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': 'Transaction Reference (Optional)'
    }))
    admin_notes = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}), required=False)
    transfer_proof = forms.FileField(required=False, widget=forms.FileInput(attrs={'class': 'form-control'}))
    account_holder_name = forms.CharField(max_length=200, required=False, widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': 'Account Holder Name'
    }))
    account_number = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': 'Account Number'
    }))
    ifsc_code = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': 'IFSC Code'
    }))
    bank_name = forms.CharField(max_length=200, required=False, widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': 'Bank Name'
    }))
    upi_id = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': 'UPI ID'
    }))