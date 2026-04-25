from django import forms
from django.core.validators import MinValueValidator
from decimal import Decimal
from .models import WithdrawalRequest

class WithdrawalRequestForm(forms.Form):
    """Form for requesting withdrawal"""
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=100,
        validators=[MinValueValidator(100)],
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter amount',
            'step': '0.01'
        })
    )
    bank_account_id = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
    
    def __init__(self, *args, **kwargs):
        bank_accounts = kwargs.pop('bank_accounts', [])
        super().__init__(*args, **kwargs)
        self.fields['bank_account_id'].choices = [
            (str(acc.id), f"{acc.bank_name} - XXXX{acc.account_number[-4:]} - {acc.account_holder_name}")
            for acc in bank_accounts
        ]


class AdminWithdrawalActionForm(forms.Form):
    """Form for admin to approve/reject withdrawal"""
    action = forms.ChoiceField(
        choices=[('approve', 'Approve'), ('reject', 'Reject')],
        widget=forms.RadioSelect
    )
    rejection_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Reason for rejection (required if rejecting)'
        })
    )
    admin_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Internal admin notes (optional)'
        })
    )
    
    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get('action')
        rejection_reason = cleaned_data.get('rejection_reason')
        
        if action == 'reject' and not rejection_reason:
            self.add_error('rejection_reason', 'Rejection reason is required when rejecting a withdrawal')
        
        return cleaned_data


class DateRangeForm(forms.Form):
    """Form for date range selection in reports"""
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )