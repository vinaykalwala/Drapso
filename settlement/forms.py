# settlement/forms.py

from django import forms
from .models import ManualPayoutRecord, PayoutBankAccount
from decimal import Decimal


class WithdrawalRequestForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=100,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter amount',
            'step': '0.01'
        })
    )
    bank_account_id = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    def __init__(self, *args, **kwargs):
        bank_accounts = kwargs.pop('bank_accounts', None)
        super().__init__(*args, **kwargs)
        
        if bank_accounts:
            choices = [(str(acc.id), f"{acc.bank_name} - XXXX{acc.account_number[-4:]}") for acc in bank_accounts]
            self.fields['bank_account_id'].choices = choices


class AdminWithdrawalActionForm(forms.Form):
    ACTION_CHOICES = [
        ('approve', 'Approve Withdrawal'),
        ('reject', 'Reject Withdrawal'),
    ]
    
    action = forms.ChoiceField(choices=ACTION_CHOICES, widget=forms.RadioSelect)
    rejection_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        help_text="Required if rejecting"
    )
    admin_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        help_text="Internal notes (optional)"
    )
    
    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get('action')
        rejection_reason = cleaned_data.get('rejection_reason')
        
        if action == 'reject' and not rejection_reason:
            self.add_error('rejection_reason', 'Rejection reason is required when rejecting a withdrawal')
        
        return cleaned_data


class ManualPayoutForm(forms.Form):
    payment_mode = forms.ChoiceField(
        choices=ManualPayoutRecord.PAYMENT_MODES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    transaction_id = forms.CharField(
        max_length=100,
        required=False,
        help_text="UTR/Transaction ID/Reference Number (required for NEFT/IMPS/RTGS)",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., NEFT1234567890'})
    )
    amount_paid = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        help_text="Enter TOTAL amount paid from platform bank account (seller amount + NEFT fee)"
    )
    payment_proof = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*,.pdf'})
    )
    processing_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        help_text="Any additional notes about this payout"
    )
    
    def __init__(self, *args, **kwargs):
        self.withdrawal = kwargs.pop('withdrawal', None)
        super().__init__(*args, **kwargs)
    
    def clean_transaction_id(self):
        mode = self.cleaned_data.get('payment_mode')
        trans_id = self.cleaned_data.get('transaction_id')
        
        # For NEFT/IMPS/RTGS, transaction ID is required
        if mode in ['NEFT', 'IMPS', 'RTGS'] and not trans_id:
            raise forms.ValidationError("Transaction ID/UTR is required for bank transfers")
        
        return trans_id
    
    def clean_amount_paid(self):
        amount = self.cleaned_data.get('amount_paid')
        
        if amount and amount <= 0:
            raise forms.ValidationError("Amount must be greater than 0")
        
        # Validate against expected platform cost
        if self.withdrawal:
            expected_amount = self.withdrawal.amount + self.withdrawal.neft_fee
            if amount != expected_amount:
                raise forms.ValidationError(
                    f"Amount paid must be ₹{expected_amount} (₹{self.withdrawal.amount} seller amount + "
                    f"₹{self.withdrawal.neft_fee} NEFT fee). Platform bears the NEFT fee."
                )
        
        return amount


class PayoutBankAccountForm(forms.ModelForm):
    class Meta:
        model = PayoutBankAccount
        fields = [
            'account_holder_name', 'bank_name', 'branch_name', 
            'account_number', 'ifsc_code', 'account_type', 
            'is_active', 'is_primary', 'upi_id', 'notes'
        ]
        widgets = {
            'account_holder_name': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'branch_name': forms.TextInput(attrs={'class': 'form-control'}),
            'account_number': forms.TextInput(attrs={'class': 'form-control'}),
            'ifsc_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., HDFC0001234'}),
            'account_type': forms.Select(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_primary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'upi_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., company@hdfcbank'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class DateRangeForm(forms.Form):
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )