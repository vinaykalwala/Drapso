# settlement/services.py

from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
import razorpay
from django.conf import settings
import logging
import re
from requests.auth import HTTPBasicAuth
import requests

logger = logging.getLogger(__name__)


class DrapsoSettlementService:
    """
    Settlement process for Drapso
    """
    
    # Fee structure
    RAZORPAY_PERCENTAGE = Decimal('0.02')  # 2%
    GST_ON_RAZORPAY = Decimal('0.18')      # 18% GST on the fee
    DRAPSO_COMMISSION_PERCENT = Decimal('0.05')  # 5% Platform fee
    NEFT_SETTLEMENT_COST = Decimal('5.00') # ₹5 buffer for NEFT
    
    @classmethod
    def calculate_settlement(cls, order):
        """Calculate complete settlement breakdown using product lineage."""
        from decimal import Decimal
        
        # Get values from order
        customer_payment = Decimal(str(order.total_amount))
        delivery_charges = order.actual_shipping_cost or Decimal('0')
        
        # Check if this is an imported product
        is_imported = order.wholeseller is not None
        
        # --- PRODUCT LINEAGE TRACING ---
        wholeseller_base_price = Decimal('0')
        if is_imported:
            # Check for Variant first, then Product to get the original wholesale price
            if order.variant and hasattr(order.variant, 'source_variant') and order.variant.source_variant:
                wholeseller_base_price = Decimal(str(order.variant.source_variant.discounted_price))
            elif order.product and hasattr(order.product, 'source_product') and order.product.source_product:
                wholeseller_base_price = Decimal(str(order.product.source_product.discounted_price))
            else:
                # Fallback to order's recorded price if relationship is missing (Safety)
                wholeseller_base_price = Decimal(str(order.product_price))

        # --- FEE CALCULATIONS ---
        # 1. Razorpay gateway fee (2% + GST)
        gateway_fee = customer_payment * cls.RAZORPAY_PERCENTAGE
        gateway_gst = gateway_fee * cls.GST_ON_RAZORPAY
        total_gateway_fee = gateway_fee + gateway_gst
        
        # 2. Drapso commission (5% of customer payment)
        drapso_commission = customer_payment * cls.DRAPSO_COMMISSION_PERCENT
        
        # 3. NEFT settlement cost
        neft_cost = cls.NEFT_SETTLEMENT_COST
        
        # 4. Total deductions to be absorbed by Reseller
        total_deductions = total_gateway_fee + drapso_commission + neft_cost + delivery_charges
        
        # --- PAYOUT DISTRIBUTION ---
        if is_imported:
            # Wholesaler gets exactly their base price
            wholeseller_amount = wholeseller_base_price
            
            # Reseller gets: (Customer Paid) - (Wholesaler Base) - (All Platform Fees)
            reseller_amount = customer_payment - wholeseller_amount - total_deductions
            
            if reseller_amount < 0:
                reseller_amount = Decimal('0')
            
            sellers_payout = {
                'wholeseller': {
                    'amount': round(wholeseller_amount, 2),
                    'note': 'Wholesaler base (source discounted_price)'
                },
                'reseller': {
                    'amount': round(reseller_amount, 2),
                    'note': 'Reseller margin after all fees'
                }
            }
        else:
            # OWN PRODUCT: Reseller handles entire amount
            wholeseller_amount = Decimal('0')
            reseller_amount = customer_payment - total_deductions
            
            if reseller_amount < 0:
                reseller_amount = Decimal('0')
            
            sellers_payout = {
                'wholeseller': {'amount': 0, 'note': 'N/A'},
                'reseller': {'amount': round(reseller_amount, 2), 'note': 'Full amount minus fees'}
            }
        
        return {
            'customer_payment': round(customer_payment, 2),
            'delivery_charges': round(delivery_charges, 2),
            'is_imported': is_imported,
            'deductions': {
                'razorpay_fee': round(total_gateway_fee, 2),
                'drapso_commission': round(drapso_commission, 2),
                'neft_cost': round(neft_cost, 2),
                'shipping': round(delivery_charges, 2)
            },
            'total_deductions': round(total_deductions, 2),
            'sellers_payout': sellers_payout
        }

    @classmethod
    @transaction.atomic
    def process_order_payment(cls, order):
        """Process order payment and create settlement records."""
        from .models import OrderSettlement, Wallet, WalletTransaction
        from accounts.models import User
        
        settlement_data = cls.calculate_settlement(order)
        
        # 1. Create settlement record
        settlement = OrderSettlement.objects.create(
            order=order,
            order_total=settlement_data['customer_payment'],
            delivery_charges=settlement_data['delivery_charges'],
            razorpay_fee=settlement_data['deductions']['razorpay_fee'],
            drapso_commission=settlement_data['deductions']['drapso_commission'],
            neft_settlement_cost=settlement_data['deductions']['neft_cost'],
            is_imported=settlement_data['is_imported'],
            wholeseller_amount=settlement_data['sellers_payout']['wholeseller']['amount'],
            reseller_amount=settlement_data['sellers_payout']['reseller']['amount'],
            status='IN_ESCROW'
        )
        
        # 2. Update Wholesaler Escrow (Imported Only)
        if settlement_data['is_imported'] and order.wholeseller:
            wh_wallet, _ = Wallet.objects.get_or_create(user=order.wholeseller)
            wh_wallet.add_to_escrow(
                amount=settlement_data['sellers_payout']['wholeseller']['amount'],
                description=f"Order {order.order_id} - Wholesaler Base",
                order_id=order.order_id
            )
        
        # 3. Update Reseller Escrow
        if order.reseller:
            res_wallet, _ = Wallet.objects.get_or_create(user=order.reseller)
            res_wallet.add_to_escrow(
                amount=settlement_data['sellers_payout']['reseller']['amount'],
                description=f"Order {order.order_id} - Reseller Margin",
                order_id=order.order_id
            )
        
        # 4. Update Platform Commission (Sent to Superuser)
        platform_owner = User.objects.filter(is_superuser=True).first()
        
        if platform_owner:
            plat_wallet, _ = Wallet.objects.get_or_create(user=platform_owner)
            comm = settlement_data['deductions']['drapso_commission']
            
            # Crediting directly to available_balance as platform commission usually isn't held in escrow
            plat_wallet.available_balance += comm
            plat_wallet.total_credited += comm
            plat_wallet.save()
            
            # Create a transaction record for the platform owner
            WalletTransaction.objects.create(
                wallet=plat_wallet,
                amount=comm,
                transaction_type='PLATFORM_COMMISSION',
                description=f"Commission from Order {order.order_id}",
                balance_after=plat_wallet.available_balance,
                order_id=order.order_id
            )
        
        return settlement_data, settlement

    @classmethod
    def recalculate_after_shipping(cls, order):
        """Recalculate settlement once actual shipping is known."""
        from .models import OrderSettlement, Wallet, WalletTransaction
        from django.db import transaction

        with transaction.atomic():
            try:
                settlement = OrderSettlement.objects.select_for_update().get(order=order)
            except OrderSettlement.DoesNotExist:
                return None

            # 1. New calculation
            new_data = cls.calculate_settlement(order)
            new_wh_amount = new_data['sellers_payout']['wholeseller']['amount']
            new_res_amount = new_data['sellers_payout']['reseller']['amount']
            new_delivery_charge = new_data['delivery_charges']

            # 2. Safety Check
            if (settlement.delivery_charges == new_delivery_charge and 
                settlement.wholeseller_amount == new_wh_amount and 
                settlement.reseller_amount == new_res_amount):
                return new_data

            # 3. Calculate Differences
            wh_diff = new_wh_amount - settlement.wholeseller_amount
            res_diff = new_res_amount - settlement.reseller_amount
            old_delivery_charge = settlement.delivery_charges

            # 4. Update the Settlement Record
            settlement.delivery_charges = new_delivery_charge
            settlement.wholeseller_amount = new_wh_amount
            settlement.reseller_amount = new_res_amount
            settlement.save()

            # 5. Adjust Wholesaler Wallet
            if order.wholeseller and wh_diff != 0:
                wh_wallet, _ = Wallet.objects.get_or_create(user=order.wholeseller)
                wh_wallet.escrow_balance += wh_diff
                wh_wallet.save()
                
                WalletTransaction.objects.create(
                    wallet=wh_wallet,
                    transaction_type='ESCROW_CREDIT', 
                    amount=wh_diff,
                    description=(
                        f"Shipping adjustment for Order {order.order_id}. "
                        f"Shipping changed from ₹{old_delivery_charge} to ₹{new_delivery_charge}."
                    ),
                    balance_after=wh_wallet.available_balance,
                    escrow_balance_after=wh_wallet.escrow_balance,
                    order_id=order.order_id
                )
                
            # 6. Adjust Reseller Wallet
            if order.reseller and res_diff != 0:
                res_wallet, _ = Wallet.objects.get_or_create(user=order.reseller)
                res_wallet.escrow_balance += res_diff
                res_wallet.save()

                WalletTransaction.objects.create(
                    wallet=res_wallet,
                    transaction_type='ESCROW_CREDIT',
                    amount=res_diff,
                    description=(
                        f"Shipping adjustment for Order {order.order_id}. "
                        f"Shipping changed from ₹{old_delivery_charge} to ₹{new_delivery_charge}."
                    ),
                    balance_after=res_wallet.available_balance,
                    escrow_balance_after=res_wallet.escrow_balance,
                    order_id=order.order_id
                )

        return new_data

    @classmethod
    def is_order_eligible_for_release(cls, order):
        """Check if order is delivered and 3-day buffer has passed"""
        if order.order_status != 'delivered' or not order.delivered_at:
            return False, "Not delivered"
        
        if timezone.now() < (order.delivered_at + timedelta(days=3)):
            return False, "Buffer active"
        
        if hasattr(order, 'return_requests'):
            if order.return_requests.filter(status__in=['pending', 'approved']).exists():
                return False, "Active return request"
                
        return True, "Eligible"

    @classmethod
    @transaction.atomic
    def release_eligible_settlements(cls):
        """Release funds from escrow to available balance."""
        from .models import OrderSettlement
        
        settlements = OrderSettlement.objects.filter(status='IN_ESCROW').select_related('order')
        
        results = []
        released_count = 0
        failed_count = 0

        for s in settlements:
            eligible, reason = cls.is_order_eligible_for_release(s.order)
            
            if eligible:
                try:
                    s.release_to_wallets() 
                    released_count += 1
                    results.append({
                        'order_id': s.order.order_id, 
                        'status': 'released'
                    })
                except Exception as e:
                    failed_count += 1
                    results.append({
                        'order_id': s.order.order_id, 
                        'status': 'failed', 
                        'error': str(e)
                    })
            else:
                results.append({
                    'order_id': s.order.order_id, 
                    'status': 'pending', 
                    'reason': reason
                })

        return {
            'results': results,
            'released_count': released_count,
            'failed_count': failed_count,
            'total_processed': len(results)
        }


class WithdrawalService:
    """Handles withdrawal requests with manual payout processing"""
    
    MINIMUM_WITHDRAWAL_AMOUNT = 1000
    WEEKLY_WITHDRAWAL_LIMIT = 50000
    
    @classmethod
    def get_neft_payout_fee(cls):
        """Calculate total NEFT payout fee with GST (borne by platform)"""
        fee = Decimal('2.00')
        gst = fee * Decimal('0.18')
        return {
            'fee': float(fee),
            'gst': float(gst),
            'total': float(fee + gst)  # Platform pays this
        }
    
    @classmethod
    def can_request_withdrawal(cls, wallet, amount):
        """Check if user can request withdrawal"""
        from .models import WithdrawalRequest
        from django.db.models import Sum
        
        if amount < cls.MINIMUM_WITHDRAWAL_AMOUNT:
            return False, f"Minimum withdrawal amount is ₹{cls.MINIMUM_WITHDRAWAL_AMOUNT}"
        
        if wallet.available_balance < amount:
            return False, f"Insufficient balance. Available: ₹{wallet.available_balance}"
        
        one_week_ago = timezone.now() - timedelta(days=7)
        weekly_withdrawn = WithdrawalRequest.objects.filter(
            wallet=wallet,
            status__in=['APPROVED', 'COMPLETED'],
            requested_at__gte=one_week_ago
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        if weekly_withdrawn + amount > cls.WEEKLY_WITHDRAWAL_LIMIT:
            remaining = cls.WEEKLY_WITHDRAWAL_LIMIT - weekly_withdrawn
            return False, f"Weekly withdrawal limit exceeded. You can withdraw up to ₹{remaining} this week"
        
        return True, "Eligible for withdrawal"
    
    @classmethod
    @transaction.atomic
    def create_withdrawal_request(cls, wallet, amount, bank_account):
        """Create a withdrawal request - seller requests exact amount they want"""
        from .models import WithdrawalRequest
        
        if bank_account.user != wallet.user:
            raise ValueError("Bank account does not belong to this user")
        
        if not bank_account.is_verified:
            raise ValueError("Bank account must be verified before withdrawal")
        
        is_eligible, message = cls.can_request_withdrawal(wallet, amount)
        if not is_eligible:
            raise ValueError(message)
        
        neft_fee_data = cls.get_neft_payout_fee()
        neft_fee = Decimal(str(neft_fee_data['total']))
        
        withdrawal = WithdrawalRequest.objects.create(
            wallet=wallet,
            amount=amount,  # This is what seller receives
            bank_account=bank_account,
            account_holder_name=bank_account.account_holder_name,
            account_number=bank_account.account_number,
            ifsc_code=bank_account.ifsc_code,
            bank_name=bank_account.bank_name,
            upi_id=bank_account.upi_id or '',
            neft_fee=neft_fee,  # Fee borne by platform
            platform_payout_cost=amount + neft_fee,  # Total platform cost
            neft_fee_breakdown=neft_fee_data,
            status='PENDING'
        )
        
        # Hold the exact amount seller requested from their wallet
        wallet.hold_for_withdrawal(
            amount=amount,
            description=f"Withdrawal request #{withdrawal.id} - pending admin approval",
            withdrawal_id=str(withdrawal.id)
        )
        
        return withdrawal
    
    @classmethod
    def get_user_bank_accounts(cls, user):
        """Get all verified bank accounts for a user"""
        from accounts.models import BankAccount
        return BankAccount.objects.filter(user=user, is_verified=True)
    
    @classmethod
    @transaction.atomic
    def admin_approve_withdrawal(cls, withdrawal_id, admin_user=None, admin_notes=''):
        """Admin approves a withdrawal request"""
        from .models import WithdrawalRequest
        
        withdrawal = WithdrawalRequest.objects.get(id=withdrawal_id)
        
        if withdrawal.status != 'PENDING':
            raise ValueError(f"Cannot approve withdrawal with status: {withdrawal.status}")
        
        withdrawal.admin_notes = admin_notes
        withdrawal.approve(admin_user)
        return withdrawal
    
    @classmethod
    @transaction.atomic
    def admin_reject_withdrawal(cls, withdrawal_id, reason, admin_user=None, admin_notes=''):
        """Admin rejects a withdrawal request"""
        from .models import WithdrawalRequest
        
        withdrawal = WithdrawalRequest.objects.get(id=withdrawal_id)
        
        if withdrawal.status != 'PENDING':
            raise ValueError(f"Cannot reject withdrawal with status: {withdrawal.status}")
        
        withdrawal.admin_notes = admin_notes
        withdrawal.reject(reason, admin_user)
        return withdrawal
    
    @classmethod
    @transaction.atomic
    def admin_complete_manual_payout(cls, withdrawal_id, payment_mode, transaction_id, 
                                     amount_paid, payment_proof=None, processed_by=None, 
                                     notes=''):
        """
        Complete withdrawal with manual payout record
        amount_paid should be the TOTAL amount platform paid (seller amount + NEFT fee)
        Seller receives their requested amount in full
        """
        from .models import WithdrawalRequest, ManualPayoutRecord
        from django.utils import timezone
        
        withdrawal = WithdrawalRequest.objects.select_for_update().get(id=withdrawal_id)
        
        if withdrawal.status != 'APPROVED':
            raise ValueError(f"Cannot process manual payout. Status: {withdrawal.status}")
        
        # Calculate amounts
        seller_gets = withdrawal.amount  # What seller requested (they get this full amount)
        platform_fee = withdrawal.neft_fee  # Fee borne by platform
        total_platform_cost = seller_gets + platform_fee  # What platform actually pays
        
        # Validate amount paid matches total platform cost
        if Decimal(str(amount_paid)) != total_platform_cost:
            raise ValueError(
                f"Amount paid (₹{amount_paid}) must equal total platform cost: "
                f"₹{seller_gets} (seller amount) + ₹{platform_fee} (NEFT fee) = ₹{total_platform_cost}"
            )
        
        # Create manual payout record
        manual_record = ManualPayoutRecord.objects.create(
            withdrawal=withdrawal,
            payment_mode=payment_mode,
            transaction_id=transaction_id,
            transaction_date=timezone.now(),
            seller_amount=seller_gets,
            platform_fee_paid=platform_fee,
            total_platform_cost=total_platform_cost,
            beneficiary_name=withdrawal.account_holder_name,
            beneficiary_account=withdrawal.account_number,
            beneficiary_ifsc=withdrawal.ifsc_code,
            beneficiary_bank=withdrawal.bank_name,
            payment_proof=payment_proof,
            processed_by=processed_by,
            status='COMPLETED',
            processing_notes=notes
        )
        
        # Update withdrawal status
        withdrawal.status = 'COMPLETED'
        withdrawal.completed_at = timezone.now()
        withdrawal.save()
        
        # Complete wallet transaction - deduct the seller's requested amount
        withdrawal.wallet.complete_withdrawal(
            amount=seller_gets,
            description=f"Manual {payment_mode} payout completed - Ref: {transaction_id} (Platform paid ₹{platform_fee} fee)",
            withdrawal_id=str(withdrawal.id)
        )
        
        return manual_record
    
    @classmethod
    @transaction.atomic
    def admin_cancel_approved_withdrawal(cls, withdrawal_id, reason, admin_user=None):
        """Cancel approved withdrawal and return funds"""
        from .models import WithdrawalRequest
        
        withdrawal = WithdrawalRequest.objects.select_for_update().get(id=withdrawal_id)
        
        if withdrawal.status != 'APPROVED':
            raise ValueError(f"Cannot cancel. Status: {withdrawal.status}")
        
        withdrawal.cancel(reason, admin_user)
        return withdrawal
    
    # Keep RazorpayX method as optional (if PAYOUT_MODE == 'RAZORPAYX')
    @classmethod
    def process_approved_payouts(cls, test_mode=False):
        """Process approved payouts via RazorpayX (if enabled)"""
        from django.conf import settings
        from .models import WithdrawalRequest
        
        # If manual mode is enabled, don't process automatically
        if getattr(settings, 'PAYOUT_MODE', 'MANUAL') == 'MANUAL':
            logger.info("Manual payout mode enabled. Skipping auto-processing.")
            return [{'status': 'skipped', 'reason': 'Manual payout mode'}]
        
        approved_withdrawals = WithdrawalRequest.objects.filter(status='APPROVED')
        results = []
        
        if not test_mode and not getattr(settings, 'RAZORPAYX_ACCOUNT_NUMBER', None):
            error_msg = "RAZORPAYX_ACCOUNT_NUMBER is not configured in settings"
            logger.error(error_msg)
            return [{'error': error_msg, 'status': 'failed'}]
        
        # Setup authentication for direct requests
        auth = HTTPBasicAuth(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        base_url = "https://api.razorpay.com/v1"
        
        for withdrawal in approved_withdrawals:
            try:
                if withdrawal.razorpay_payout_id:
                    results.append({
                        'withdrawal_id': str(withdrawal.id),
                        'status': 'skipped',
                        'reason': 'Already processed'
                    })
                    continue
                
                if test_mode:
                    withdrawal.razorpay_payout_id = f"TEST_{withdrawal.id}"
                    withdrawal.status = "COMPLETED"
                    withdrawal.save(update_fields=["razorpay_payout_id", "status"])
                    results.append({
                        'withdrawal_id': str(withdrawal.id),
                        'status': 'completed',
                        'mode': 'test'
                    })
                    continue
                
                # Prepare data
                amount_paisa = int(round(float(withdrawal.amount) * 100))
                phone = str(withdrawal.wallet.user.phone)[-10:] if withdrawal.wallet.user.phone else "9999999999"
                email = withdrawal.wallet.user.email or f"user{withdrawal.wallet.user.id}@example.com"
                
                # Step 1: Create Contact (if not exists)
                if not withdrawal.razorpay_contact_id:
                    contact_data = {
                        "name": withdrawal.account_holder_name[:100],
                        "email": email[:100],
                        "contact": "91" + phone,
                        "type": "vendor",
                        "reference_id": str(withdrawal.wallet.user.id)
                    }
                    
                    response = requests.post(f"{base_url}/contacts", json=contact_data, auth=auth)
                    
                    if response.status_code not in [200, 201]:
                        raise Exception(f"Contact creation failed: {response.text}")
                    
                    contact = response.json()
                    withdrawal.razorpay_contact_id = contact['id']
                    withdrawal.save(update_fields=['razorpay_contact_id'])
                    
                
                # Step 2: Create Fund Account (if not exists)
                if not withdrawal.fund_account_id:
                    fund_data = {
                        "contact_id": withdrawal.razorpay_contact_id,
                        "account_type": "bank_account",
                        "bank_account": {
                            "name": withdrawal.account_holder_name[:100],
                            "ifsc": withdrawal.ifsc_code,
                            "account_number": str(withdrawal.account_number)
                        }
                    }
                    
                    response = requests.post(f"{base_url}/fund_accounts", json=fund_data, auth=auth)
                    
                    if response.status_code not in [200, 201]:
                        raise Exception(f"Fund account creation failed: {response.text}")
                    
                    fund_account = response.json()
                    withdrawal.fund_account_id = fund_account['id']
                    withdrawal.save(update_fields=['fund_account_id'])
                    
                
                # Step 3: Create Payout
                short_id = str(withdrawal.id)[:20]
                narration = "Payout"
                
                payout_data = {
                    "account_number": str(settings.RAZORPAYX_ACCOUNT_NUMBER),
                    "fund_account_id": withdrawal.fund_account_id,
                    "amount": amount_paisa,
                    "currency": "INR",
                    "mode": "NEFT",
                    "purpose": "payout",
                    "reference_id": str(withdrawal.id) + "_" + str(int(withdrawal.created_at.timestamp())) if hasattr(withdrawal, 'created_at') else str(withdrawal.id),
                    "narration": narration,
                    "queue_if_low_balance": True,
                    "notes": {
                        "withdrawal_id": str(withdrawal.id),
                        "user_id": str(withdrawal.wallet.user.id)
                    }
                }
                
                response = requests.post(f"{base_url}/payouts", json=payout_data, auth=auth)
                
                if response.status_code not in [200, 201]:
                    raise Exception(f"Payout creation failed: {response.text}")
                
                payout = response.json()
                
                withdrawal.razorpay_payout_id = payout['id']
                withdrawal.status = "COMPLETED"
                withdrawal.save(update_fields=["razorpay_payout_id", "status"])
                
                results.append({
                    'withdrawal_id': str(withdrawal.id),
                    'status': 'processing',
                    'payout_id': payout['id']
                })
                
            except Exception as e:
                error_msg = str(e)
                
                results.append({
                    'withdrawal_id': str(withdrawal.id),
                    'status': 'failed',
                    'error': error_msg,
                    'amount': str(withdrawal.amount),
                    'account': withdrawal.account_number,
                    'ifsc': withdrawal.ifsc_code
                })
        
        return results