# settlement/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db.models import Sum, Q
from decimal import Decimal
from .models import Wallet, WithdrawalRequest, WalletTransaction, OrderSettlement, ManualPayoutRecord, PayoutBankAccount
from .services import WithdrawalService, DrapsoSettlementService
from .forms import WithdrawalRequestForm, AdminWithdrawalActionForm, DateRangeForm, ManualPayoutForm, PayoutBankAccountForm
from accounts.models import BankAccount
import csv


def is_admin(user):
    return user.role == 'admin' or user.is_superuser


def is_reseller(user):
    return user.role == 'reseller'


def is_wholeseller(user):
    return user.role == 'wholeseller'


@login_required
def dashboard(request):
    """Main settlement dashboard for sellers"""
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    
    # Get recent transactions
    recent_transactions = WalletTransaction.objects.filter(wallet=wallet)[:10]
    
    # Get recent withdrawal requests
    recent_withdrawals = WithdrawalRequest.objects.filter(wallet=wallet).order_by('-requested_at')[:10]
    
    # Calculate weekly withdrawal total
    one_week_ago = timezone.now() - timezone.timedelta(days=7)
    weekly_withdrawn = WithdrawalRequest.objects.filter(
        wallet=wallet,
        status__in=['APPROVED', 'COMPLETED'],
        requested_at__gte=one_week_ago
    ).aggregate(total=Sum('amount'))['total'] or 0

    weekly_limit = WithdrawalService.WEEKLY_WITHDRAWAL_LIMIT
    remaining = max(0, weekly_limit - weekly_withdrawn)

    context = {
        'wallet': wallet,
        'recent_transactions': recent_transactions,
        'recent_withdrawals': recent_withdrawals,
        'weekly_withdrawn': weekly_withdrawn,
        'weekly_limit': weekly_limit,
        'remaining': remaining,
        'minimum_withdrawal': WithdrawalService.MINIMUM_WITHDRAWAL_AMOUNT,
        'neft_fee': WithdrawalService.get_neft_payout_fee(),
    }
    
    return render(request, 'settlement/dashboard.html', context)


@login_required
def withdrawal_request(request):
    """Request withdrawal from wallet"""
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    bank_accounts = WithdrawalService.get_user_bank_accounts(request.user)
    
    if not bank_accounts.exists():
        messages.warning(request, 'Please add and verify a bank account before requesting withdrawal.')
        return redirect('accounts:bank_accounts')
    
    if request.method == 'POST':
        form = WithdrawalRequestForm(request.POST, bank_accounts=bank_accounts)
        
        if form.is_valid():
            amount = form.cleaned_data['amount']
            bank_account_id = form.cleaned_data['bank_account_id']
            bank_account = get_object_or_404(BankAccount, id=bank_account_id, user=request.user)
            
            try:
                withdrawal = WithdrawalService.create_withdrawal_request(wallet, amount, bank_account)
                messages.success(request, f'Withdrawal request of ₹{amount} submitted successfully. Awaiting admin approval.')
                return redirect('settlement:withdrawal_history')
            except ValueError as e:
                messages.error(request, str(e))
    else:
        form = WithdrawalRequestForm(bank_accounts=bank_accounts)
    
    context = {
        'form': form,
        'wallet': wallet,
        'bank_accounts': bank_accounts,
        'minimum_withdrawal': WithdrawalService.MINIMUM_WITHDRAWAL_AMOUNT,
        'neft_fee': WithdrawalService.get_neft_payout_fee(),
    }
    
    return render(request, 'settlement/withdrawal_request.html', context)


@login_required
def withdrawal_history(request):
    """View withdrawal history"""
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    withdrawals = WithdrawalRequest.objects.filter(wallet=wallet).order_by('-requested_at')
    
    context = {
        'withdrawals': withdrawals,
        'wallet': wallet,
    }
    
    return render(request, 'settlement/withdrawal_history.html', context)


@login_required
def transaction_history(request):
    """View all wallet transactions"""
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    transactions = WalletTransaction.objects.filter(wallet=wallet).order_by('-created_at')
    
    # Filter by type if provided
    transaction_type = request.GET.get('type')
    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    
    context = {
        'transactions': transactions,
        'wallet': wallet,
        'current_filter': transaction_type,
        'transaction_types': WalletTransaction.TRANSACTION_TYPES,
    }
    
    return render(request, 'settlement/transaction_history.html', context)


@login_required
@user_passes_test(is_admin)
def admin_withdrawal_requests(request):
    """Admin view for managing withdrawal requests"""
    withdrawals = WithdrawalRequest.objects.select_related('wallet__user', 'bank_account').order_by('-requested_at')
    
    # Filter by status
    status_filter = request.GET.get('status')
    if status_filter:
        withdrawals = withdrawals.filter(status=status_filter)
    
    context = {
        'withdrawals': withdrawals,
        'status_filter': status_filter,
        'status_choices': WithdrawalRequest.WITHDRAWAL_STATUS,
    }
    
    return render(request, 'settlement/admin/withdrawal_requests.html', context)


@login_required
@user_passes_test(is_admin)
def admin_withdrawal_detail(request, withdrawal_id):
    """Admin view for withdrawal request details and action"""
    withdrawal = get_object_or_404(WithdrawalRequest.objects.select_related('wallet__user', 'bank_account'), id=withdrawal_id)
    
    # Get manual payout record if exists
    manual_payout = None
    if hasattr(withdrawal, 'manual_payout'):
        manual_payout = withdrawal.manual_payout
    
    if request.method == 'POST':
        form = AdminWithdrawalActionForm(request.POST)
        
        if form.is_valid():
            action = form.cleaned_data['action']
            rejection_reason = form.cleaned_data.get('rejection_reason', '')
            admin_notes = form.cleaned_data.get('admin_notes', '')
            
            try:
                if action == 'approve':
                    WithdrawalService.admin_approve_withdrawal(withdrawal.id, request.user, admin_notes)
                    messages.success(request, f'Withdrawal #{withdrawal.id} approved successfully.')
                else:
                    WithdrawalService.admin_reject_withdrawal(withdrawal.id, rejection_reason, request.user, admin_notes)
                    messages.success(request, f'Withdrawal #{withdrawal.id} rejected.')
                
                return redirect('settlement:admin_withdrawal_requests')
            except ValueError as e:
                messages.error(request, str(e))
    else:
        form = AdminWithdrawalActionForm()
    
    context = {
        'withdrawal': withdrawal,
        'form': form,
        'manual_payout': manual_payout,
    }
    
    return render(request, 'settlement/admin/withdrawal_detail.html', context)


@login_required
@user_passes_test(is_admin)
def admin_record_manual_payout(request, withdrawal_id):
    """Form for admin to record manual payout"""
    withdrawal = get_object_or_404(
        WithdrawalRequest.objects.select_related('wallet__user'), 
        id=withdrawal_id
    )
    
    # Only allow for APPROVED withdrawals
    if withdrawal.status != 'APPROVED':
        messages.error(request, f"Cannot record payout. Current status: {withdrawal.status}")
        return redirect('settlement:admin_withdrawal_detail', withdrawal_id=withdrawal_id)
    
    # Check if already paid
    if hasattr(withdrawal, 'manual_payout'):
        messages.warning(request, 'This withdrawal already has a payout record.')
        return redirect('settlement:admin_withdrawal_detail', withdrawal_id=withdrawal_id)
    
    if request.method == 'POST':
        form = ManualPayoutForm(request.POST, request.FILES, withdrawal=withdrawal)
        
        if form.is_valid():
            try:
                payment_proof = request.FILES.get('payment_proof')
                
                manual_record = WithdrawalService.admin_complete_manual_payout(
                    withdrawal_id=withdrawal_id,
                    payment_mode=form.cleaned_data['payment_mode'],
                    transaction_id=form.cleaned_data['transaction_id'],
                    amount_paid=form.cleaned_data['amount_paid'],
                    payment_proof=payment_proof,
                    processed_by=request.user,
                    notes=form.cleaned_data['processing_notes']
                )
                
                messages.success(
                    request, 
                    f'✅ Payout recorded! Seller receives ₹{manual_record.seller_amount} (full requested amount). '
                    f'Platform paid ₹{manual_record.platform_fee_paid} NEFT fee.'
                )
                return redirect('settlement:admin_withdrawal_requests')
                
            except ValueError as e:
                messages.error(request, str(e))
    else:
        expected_amount = withdrawal.amount + withdrawal.neft_fee
        form = ManualPayoutForm(withdrawal=withdrawal, initial={'amount_paid': expected_amount})
    
    context = {
        'withdrawal': withdrawal,
        'form': form,
        'bank_accounts': PayoutBankAccount.objects.filter(is_active=True),
        'expected_amount': withdrawal.amount + withdrawal.neft_fee,
    }
    
    return render(request, 'settlement/admin/record_manual_payout.html', context)


@login_required
@user_passes_test(is_admin)
def admin_cancel_approved_withdrawal(request, withdrawal_id):
    """Cancel approved withdrawal before payout"""
    withdrawal = get_object_or_404(WithdrawalRequest, id=withdrawal_id)
    
    if withdrawal.status != 'APPROVED':
        messages.error(request, f"Cannot cancel withdrawal with status: {withdrawal.status}")
        return redirect('settlement:admin_withdrawal_detail', withdrawal_id=withdrawal_id)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        
        if not reason:
            messages.error(request, 'Please provide a reason for cancellation')
            return redirect('settlement:admin_withdrawal_detail', withdrawal_id=withdrawal_id)
        
        try:
            WithdrawalService.admin_cancel_approved_withdrawal(
                withdrawal_id=withdrawal_id,
                reason=reason,
                admin_user=request.user
            )
            messages.success(request, f'Withdrawal #{withdrawal_id} cancelled. Funds returned to wallet.')
        except ValueError as e:
            messages.error(request, str(e))
    
    return redirect('settlement:admin_withdrawal_detail', withdrawal_id=withdrawal_id)


@login_required
@user_passes_test(is_admin)
def admin_payout_bank_accounts(request):
    """Manage company bank accounts for payouts"""
    accounts = PayoutBankAccount.objects.all()
    
    if request.method == 'POST':
        form = PayoutBankAccountForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Bank account added successfully.')
            return redirect('settlement:admin_payout_bank_accounts')
    else:
        form = PayoutBankAccountForm()
    
    context = {
        'accounts': accounts,
        'form': form,
    }
    
    return render(request, 'settlement/admin/payout_bank_accounts.html', context)


@login_required
@user_passes_test(is_admin)
def admin_payout_bank_account_delete(request, account_id):
    """Delete a payout bank account"""
    account = get_object_or_404(PayoutBankAccount, id=account_id)
    
    if account.is_primary:
        messages.error(request, 'Cannot delete primary bank account. Set another account as primary first.')
    else:
        account.delete()
        messages.success(request, 'Bank account deleted successfully.')
    
    return redirect('settlement:admin_payout_bank_accounts')


@login_required
@user_passes_test(is_admin)
def admin_settlement_report(request):
    """Admin view for settlement reports with CSV export"""
    
    form = DateRangeForm(request.GET or None)
    
    settlements = OrderSettlement.objects.select_related('order').all()
    
    if form.is_valid() and form.cleaned_data:
        start_date = form.cleaned_data.get('start_date')
        end_date = form.cleaned_data.get('end_date')
        if start_date:
            settlements = settlements.filter(created_at__date__gte=start_date)
        if end_date:
            settlements = settlements.filter(created_at__date__lte=end_date)
    
    # Summary statistics
    total_settled = settlements.aggregate(
        total_order_value=Sum('order_total'),
        total_razorpay_fee=Sum('razorpay_fee'),
        total_drapso_commission=Sum('drapso_commission'),
        total_wholeseller=Sum('wholeseller_amount'),
        total_reseller=Sum('reseller_amount'),
        total_neft_cost=Sum('neft_settlement_cost'),
    )
    
    def format_k(value):
        try:
            value = float(value or 0)
            if value >= 1000:
                return f"{value/1000:.1f}".rstrip('0').rstrip('.') + "K"
            return str(int(value))
        except:
            return value

    net_to_sellers = (total_settled.get('total_wholeseller') or 0) + (total_settled.get('total_reseller') or 0)
    total_settled['total_order_value_short'] = format_k(total_settled.get('total_order_value'))
    total_settled['net_to_sellers_short'] = format_k(net_to_sellers)
    total_settled['total_reseller_short'] = format_k(total_settled.get('total_reseller'))
    
    # Check for CSV export
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="settlement_report.csv"'
        
        writer = csv.writer(response)
        
        writer.writerow([
            'Order ID', 'Shiprocket ID', 'Date', 'Order Total', 'Delivery Charges', 
            'Razorpay Fee', 'Drapso Commission', 'NEFT Cost', 'Wholeseller Amount',
            'Reseller Amount', 'Status', 'Created At'
        ])
        
        for settlement in settlements:
            created_at_date = ""
            created_at_datetime = ""
            
            if settlement.created_at:
                created_at_date = settlement.created_at.strftime('%Y-%m-%d')
                created_at_datetime = settlement.created_at.strftime('%Y-%m-%d %H:%M:%S')
            
            writer.writerow([
                settlement.order.order_id if settlement.order else '',
                settlement.order.shiprocket_order_id if settlement.order and settlement.order.shiprocket_order_id else '',
                created_at_date,
                float(settlement.order_total) if settlement.order_total else 0,
                float(settlement.delivery_charges) if settlement.delivery_charges else 0,
                float(settlement.razorpay_fee) if settlement.razorpay_fee else 0,
                float(settlement.drapso_commission) if settlement.drapso_commission else 0,
                float(settlement.neft_settlement_cost) if settlement.neft_settlement_cost else 0,
                float(settlement.wholeseller_amount) if settlement.wholeseller_amount else 0,
                float(settlement.reseller_amount) if settlement.reseller_amount else 0,
                settlement.status if settlement.status else '',
                created_at_datetime,
            ])
        
        return response
    
    context = {
        'form': form,
        'settlements': settlements,
        'summary': total_settled,
    }
    
    return render(request, 'settlement/admin/settlement_report.html', context)


@login_required
@user_passes_test(is_admin)
def admin_platform_earnings(request):
    """
    Detailed view for Drapso platform revenue with strictly separated 
    Commission, Shipping, and Gateway metrics.
    """
    form = DateRangeForm(request.GET or None)
    
    # Base queryset
    settlements = OrderSettlement.objects.select_related('order', 'order__reseller').all()
    
    # Apply date filters
    if form.is_valid():
        start_date = form.cleaned_data.get('start_date')
        end_date = form.cleaned_data.get('end_date')
        if start_date:
            settlements = settlements.filter(created_at__date__gte=start_date)
        if end_date:
            settlements = settlements.filter(created_at__date__lte=end_date)
    
    # 1. Aggregate the distinct buckets
    stats_raw = settlements.aggregate(
        total_revenue=Sum('order_total'),
        total_commissions=Sum('drapso_commission'),
        total_gateway_fees=Sum('razorpay_fee'),
        total_shipping=Sum('delivery_charges'),
        total_neft_buffer=Sum('neft_settlement_cost'),
    )

    # 2. Extract values with fallbacks to 0
    total_revenue = stats_raw.get('total_revenue') or Decimal('0')
    gross_commission = stats_raw.get('total_commissions') or Decimal('0')
    gateway_fees_paid = stats_raw.get('total_gateway_fees') or Decimal('0')
    total_shipping = stats_raw.get('total_shipping') or Decimal('0')
    neft_buffer = stats_raw.get('total_neft_buffer') or Decimal('0')

    # 3. Simple Profit Logic
    payout_fee_data = WithdrawalService.get_neft_payout_fee()
    fee_per_payout = Decimal(str(payout_fee_data.get('total', 2.36)))
    estimated_payout_costs = settlements.count() * fee_per_payout
    
    net_platform_profit = (gross_commission + neft_buffer) - estimated_payout_costs

    context = {
        'form': form,
        'settlements': settlements.order_by('-created_at'),
        'total_orders': settlements.count(),
        'stats': {
            'total_revenue': total_revenue,
            'gross_commission': gross_commission,
            'total_shipping': total_shipping,
            'gateway_fees_paid': gateway_fees_paid,
            'neft_buffer_collected': neft_buffer,
            'estimated_payout_costs': estimated_payout_costs,
        },
        'net_platform_profit': net_platform_profit,
    }
    
    return render(request, 'settlement/admin/platform_earnings.html', context)


@login_required
def api_wallet_balance(request):
    """API endpoint for wallet balance"""
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    return JsonResponse({
        'available_balance': float(wallet.available_balance),
        'escrow_balance': float(wallet.escrow_balance),
        'pending_withdrawal': float(wallet.pending_withdrawal),
        'total_credited': float(wallet.total_credited),
        'total_withdrawn': float(wallet.total_withdrawn),
    })


@login_required
def api_bank_accounts(request):
    """API endpoint for user's bank accounts"""
    bank_accounts = WithdrawalService.get_user_bank_accounts(request.user)
    return JsonResponse({
        'bank_accounts': [
            {
                'id': str(acc.id),
                'account_holder_name': acc.account_holder_name,
                'bank_name': acc.bank_name,
                'account_number': f"XXXX{acc.account_number[-4:]}",
                'ifsc_code': acc.ifsc_code,
                'is_primary': acc.is_primary,
            }
            for acc in bank_accounts
        ]
    })


@login_required
@user_passes_test(is_admin)
def admin_manual_payouts_report(request):
    """Report view for all manual payouts"""
    payouts = ManualPayoutRecord.objects.select_related('withdrawal__wallet__user', 'processed_by').all()
    
    # Filter by date range
    form = DateRangeForm(request.GET or None)
    if form.is_valid() and form.cleaned_data:
        start_date = form.cleaned_data.get('start_date')
        end_date = form.cleaned_data.get('end_date')
        if start_date:
            payouts = payouts.filter(transaction_date__date__gte=start_date)
        if end_date:
            payouts = payouts.filter(transaction_date__date__lte=end_date)
    
    # Summary statistics
    summary = payouts.aggregate(
        total_paid=Sum('total_platform_cost'),
        total_fees=Sum('platform_fee_paid'),
        total_net=Sum('seller_amount'),
        total_count=Sum('id')
    )
    
    context = {
        'form': form,
        'payouts': payouts,
        'summary': summary,
    }
    
    return render(request, 'settlement/admin/manual_payouts_report.html', context)

# settlement/views.py - Add this new view

@login_required
def my_payouts(request):
    """
    View for sellers to see their payouts (withdrawals) processed by admin
    """
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    
    # Get all withdrawal requests for this user
    withdrawals = WithdrawalRequest.objects.filter(wallet=wallet).order_by('-requested_at')
    
    # Filter by status if provided
    status_filter = request.GET.get('status')
    if status_filter:
        withdrawals = withdrawals.filter(status=status_filter)
    
    # Get summary statistics
    total_withdrawn = withdrawals.filter(status='COMPLETED').aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    
    total_pending = withdrawals.filter(status='PENDING').aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    
    total_approved = withdrawals.filter(status='APPROVED').aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    
    total_rejected = withdrawals.filter(status='REJECTED').aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    
    # Get recent payouts (last 5 completed)
    recent_payouts = withdrawals.filter(status='COMPLETED')[:5]
    
    context = {
        'wallet': wallet,
        'withdrawals': withdrawals,
        'status_filter': status_filter,
        'status_choices': WithdrawalRequest.WITHDRAWAL_STATUS,
        'total_withdrawn': total_withdrawn,
        'total_pending': total_pending,
        'total_approved': total_approved,
        'total_rejected': total_rejected,
        'recent_payouts': recent_payouts,
    }
    
    return render(request, 'settlement/my_payouts.html', context)