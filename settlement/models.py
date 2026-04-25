from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
import uuid

class Wallet(models.Model):
    """
    Internal wallet for users (Wholeseller, Reseller, Platform)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='wallet'
    )
    
    # Balances
    available_balance = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        help_text="Money available for withdrawal"
    )
    escrow_balance = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0, 
        help_text="Funds waiting for settlement buffer period"
    )
    pending_withdrawal = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0, 
        help_text="Funds requested for withdrawal (on hold)"
    )
    
    # Lifetime stats
    total_credited = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_withdrawn = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - Available: ₹{self.available_balance}, Escrow: ₹{self.escrow_balance}"
    
    def add_to_escrow(self, amount, description, order_id=None):
        """Add funds to escrow (during buffer period)"""
        from .models import WalletTransaction
        
        self.escrow_balance += Decimal(str(amount))
        self.save()
        
        return WalletTransaction.objects.create(
            wallet=self,
            amount=amount,
            transaction_type='ESCROW_CREDIT',
            description=description,
            balance_after=self.available_balance,
            escrow_balance_after=self.escrow_balance,
            order_id=order_id
        )
    
    def release_from_escrow(self, amount, description, order_id=None):
        """Release funds from escrow to available balance"""
        from .models import WalletTransaction
        
        if self.escrow_balance < Decimal(str(amount)):
            raise ValueError(f"Insufficient escrow balance. Have: {self.escrow_balance}, Need: {amount}")
        
        self.escrow_balance -= Decimal(str(amount))
        self.available_balance += Decimal(str(amount))
        self.total_credited += Decimal(str(amount))
        self.save()
        
        return WalletTransaction.objects.create(
            wallet=self,
            amount=amount,
            transaction_type='ESCROW_RELEASE',
            description=description,
            balance_after=self.available_balance,
            escrow_balance_after=self.escrow_balance,
            order_id=order_id
        )
    
    def hold_for_withdrawal(self, amount, description, withdrawal_id=None):
        """Hold funds when withdrawal is requested (admin approval pending)"""
        from .models import WalletTransaction
        
        if self.available_balance < Decimal(str(amount)):
            raise ValueError(f"Insufficient balance. Have: {self.available_balance}, Need: {amount}")
        
        self.available_balance -= Decimal(str(amount))
        self.pending_withdrawal += Decimal(str(amount))
        self.save()
        
        return WalletTransaction.objects.create(
            wallet=self,
            amount=amount,
            transaction_type='WITHDRAWAL_HOLD',
            description=description,
            balance_after=self.available_balance,
            withdrawal_id=withdrawal_id
        )
    
    def complete_withdrawal(self, amount, description, withdrawal_id=None):
        """Complete withdrawal after admin approval"""
        from .models import WalletTransaction
        
        if self.pending_withdrawal < Decimal(str(amount)):
            raise ValueError(f"Insufficient pending withdrawal balance")
        
        self.pending_withdrawal -= Decimal(str(amount))
        self.total_withdrawn += Decimal(str(amount))
        self.save()
        
        return WalletTransaction.objects.create(
            wallet=self,
            amount=amount,
            transaction_type='WITHDRAWAL_COMPLETED',
            description=description,
            balance_after=self.available_balance,
            withdrawal_id=withdrawal_id
        )
    
    def reject_withdrawal(self, amount, description, withdrawal_id=None):
        """Return held funds to available when withdrawal is rejected"""
        from .models import WalletTransaction
        
        if self.pending_withdrawal < Decimal(str(amount)):
            raise ValueError(f"Insufficient pending withdrawal balance")
        
        self.pending_withdrawal -= Decimal(str(amount))
        self.available_balance += Decimal(str(amount))
        self.save()
        
        return WalletTransaction.objects.create(
            wallet=self,
            amount=amount,
            transaction_type='WITHDRAWAL_REJECTED',
            description=description,
            balance_after=self.available_balance,
            withdrawal_id=withdrawal_id
        )


class WalletTransaction(models.Model):
    """
    All wallet transactions history
    """
    TRANSACTION_TYPES = [
        ('ESCROW_CREDIT', 'Escrow Credit (Order Payment)'),
        ('ESCROW_RELEASE', 'Escrow Release (After Buffer)'),
        ('WITHDRAWAL_HOLD', 'Withdrawal Hold (Request Pending)'),
        ('WITHDRAWAL_COMPLETED', 'Withdrawal Completed'),
        ('WITHDRAWAL_REJECTED', 'Withdrawal Rejected'),
        ('REFUND', 'Refund'),
        ('ADJUSTMENT', 'Adjustment'),
        ('PLATFORM_COMMISSION', 'Platform Commission'),
        ('NEFT_FEE', 'NEFT Payout Fee'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=30, choices=TRANSACTION_TYPES)
    description = models.TextField()
    
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    escrow_balance_after = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    order_id = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    withdrawal_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['wallet', 'created_at']),
            models.Index(fields=['transaction_type']),
        ]
    
    def __str__(self):
        return f"{self.get_transaction_type_display()}: ₹{self.amount} - {self.wallet.user.username}"


class OrderSettlement(models.Model):
    """
    Track order settlements from escrow to wallets
    """
    SETTLEMENT_STATUS = [
        ('IN_ESCROW', 'In Escrow (Buffer Period)'),
        ('RELEASED', 'Released to Wallets'),
        ('CANCELLED', 'Cancelled'),
        ('REFUNDED', 'Refunded'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField('orders.Order', on_delete=models.CASCADE, related_name='settlement')
    
    # Order details
    order_total = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_charges = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Deductions
    razorpay_fee = models.DecimalField(max_digits=10, decimal_places=2)
    drapso_commission = models.DecimalField(max_digits=10, decimal_places=2)
    neft_settlement_cost = models.DecimalField(max_digits=10, decimal_places=2, default=4.00)
    
    # Product type
    is_imported = models.BooleanField(default=True, help_text="True if product from wholeseller, False if reseller's own product")
    
    # Seller amounts
    wholeseller_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    reseller_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Status
    status = models.CharField(max_length=20, choices=SETTLEMENT_STATUS, default='IN_ESCROW')
    escrow_released_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['order', 'status']),
        ]
    
    def __str__(self):
        product_type = "Imported" if self.is_imported else "Own Product"
        return f"{product_type} - {self.order.order_id} - {self.get_status_display()}"
    
    def release_to_wallets(self):
        """Release funds from escrow to seller wallets after buffer period"""
        from django.utils import timezone
        from .models import Wallet
        
        # Release to wholeseller (only for imported products)
        if self.is_imported and self.wholeseller_amount > 0 and self.order.wholeseller:
            wholeseller_wallet = Wallet.objects.get(user=self.order.wholeseller)
            wholeseller_wallet.release_from_escrow(
                amount=self.wholeseller_amount,
                description=f"Order {self.order.order_id} - Wholeseller settlement released after buffer period",
                order_id=self.order.order_id
            )
        
        # Release to reseller (always)
        if self.reseller_amount > 0 and self.order.reseller:
            reseller_wallet = Wallet.objects.get(user=self.order.reseller)
            reseller_wallet.release_from_escrow(
                amount=self.reseller_amount,
                description=f"Order {self.order.order_id} - {'Reseller margin' if self.is_imported else 'Reseller own product'} settlement released after buffer period",
                order_id=self.order.order_id
            )
        
        self.status = 'RELEASED'
        self.escrow_released_at = timezone.now()
        self.save()
    
    def cancel(self):
        """Cancel settlement and refund money"""
        from .models import Wallet
        
        # Remove from escrow
        if self.is_imported and self.wholeseller_amount > 0 and self.order.wholeseller:
            wholeseller_wallet = Wallet.objects.get(user=self.order.wholeseller)
            wholeseller_wallet.escrow_balance -= self.wholeseller_amount
            wholeseller_wallet.save()
        
        if self.reseller_amount > 0 and self.order.reseller:
            reseller_wallet = Wallet.objects.get(user=self.order.reseller)
            reseller_wallet.escrow_balance -= self.reseller_amount
            reseller_wallet.save()
        
        self.status = 'CANCELLED'
        self.save()


class WithdrawalRequest(models.Model):
    """
    Withdrawal request from seller to bank account
    ALL payouts via NEFT only
    """
    WITHDRAWAL_STATUS = [
        ('PENDING', 'Pending Admin Approval'),
        ('APPROVED', 'Approved - Processing'),
        ('COMPLETED', 'Completed'),
        ('REJECTED', 'Rejected'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='withdrawals')
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(100)])
    
    # Bank Account FK
    bank_account = models.ForeignKey(
        'accounts.BankAccount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='withdrawal_requests',
        limit_choices_to={'is_verified': True}
    )
    
    # Snapshot of bank details
    account_holder_name = models.CharField(max_length=200)
    account_number = models.CharField(max_length=50)
    ifsc_code = models.CharField(max_length=20)
    bank_name = models.CharField(max_length=200)
    upi_id = models.CharField(max_length=100, blank=True)
    
    # NEFT fee details
    neft_fee = models.DecimalField(max_digits=10, decimal_places=2, default=2.36)
    neft_fee_breakdown = models.JSONField(default=dict)
    
    status = models.CharField(max_length=20, choices=WITHDRAWAL_STATUS, default='PENDING')
    
    # Razorpay tracking
    razorpay_payout_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_contact_id = models.CharField(max_length=100, blank=True, null=True)
    fund_account_id = models.CharField(max_length=100, blank=True, null=True)
    
    admin_notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-requested_at']
        indexes = [
            models.Index(fields=['status', 'requested_at']),
            models.Index(fields=['wallet', 'status']),
        ]
    
    def __str__(self):
        return f"{self.wallet.user.username} - ₹{self.amount} (NEFT) - {self.get_status_display()}"
    
    def save(self, *args, **kwargs):
        if self.bank_account and not self.account_number:
            self.account_holder_name = self.bank_account.account_holder_name
            self.account_number = self.bank_account.account_number
            self.ifsc_code = self.bank_account.ifsc_code
            self.bank_name = self.bank_account.bank_name
            self.upi_id = self.bank_account.upi_id or ''
        super().save(*args, **kwargs)
    
    def approve(self, admin_user=None):
        from django.utils import timezone
        self.status = 'APPROVED'
        self.approved_at = timezone.now()
        self.save()
    
    def reject(self, reason, admin_user=None):
        self.status = 'REJECTED'
        self.rejection_reason = reason
        self.save()
        self.wallet.reject_withdrawal(
            amount=self.amount,
            description=f"Withdrawal request rejected: {reason[:200]}",
            withdrawal_id=str(self.id)
        )
    
    def complete(self):
        from django.utils import timezone
        self.status = 'COMPLETED'
        self.completed_at = timezone.now()
        self.save()
        self.wallet.complete_withdrawal(
            amount=self.amount,
            description=f"NEFT withdrawal completed - Payout ID: {self.razorpay_payout_id}",
            withdrawal_id=str(self.id)
        )