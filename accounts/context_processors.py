from accounts.models import (
    CustomerProfile,
    WholesellerProfile,
    ResellerProfile,
    AdminProfile
)

from wholesellers.models import WholesellerKYC
from products.models import PriceChangeNotification
from orders.models import Refund, Order
from settlement.models import WithdrawalRequest


def user_profile_data(request):

    profile = None
    role = None

    # ===== DEFAULT COUNTS =====
    pending_kyc_count = 0
    pending_price_notifications = 0
    pending_refund_requests = 0
    pending_withdrawal_requests = 0
    pending_reseller_orders = 0
    pending_wholeseller_orders = 0   # 🔥 ADD THIS

    if request.user.is_authenticated:

        role = request.user.get_role_display()

        # ===== CUSTOMER =====
        if request.user.role == "customer":
            profile = CustomerProfile.objects.filter(user=request.user).first()

        # ===== WHOLESELLER =====
        elif request.user.role == "wholeseller":
            profile = WholesellerProfile.objects.filter(user=request.user).first()

            # 📦 Approved → Processing Orders
            pending_wholeseller_orders = Order.objects.filter(
                wholeseller=request.user,
                order_status="approved"
            ).count()

        # ===== RESELLER =====
        elif request.user.role == "reseller":
            profile = ResellerProfile.objects.filter(user=request.user).first()

            # 🔔 Price Notifications
            pending_price_notifications = PriceChangeNotification.objects.filter(
                reseller=request.user,
                is_actioned=False
            ).count()

            # 🛒 Paid but Awaiting Approval
            pending_reseller_orders = Order.objects.filter(
                reseller=request.user,
                order_status="paid",
                payment_status="success"
            ).count()

        # ===== ADMIN =====
        elif request.user.role == "admin":
            profile = AdminProfile.objects.filter(user=request.user).first()

            # 🪪 KYC Requests
            pending_kyc_count = WholesellerKYC.objects.filter(
                status__iexact="pending"
            ).count()

            # 🔄 Refund Requests
            pending_refund_requests = Refund.objects.filter(
                status__in=["pending", "processing"]
            ).count()

            # 💸 Withdrawal Requests
            pending_withdrawal_requests = WithdrawalRequest.objects.filter(
                status__iexact="pending"
            ).count()

    return {
        "profile": profile,
        "role": role,
        "pending_kyc_count": pending_kyc_count,
        "pending_price_notifications": pending_price_notifications,
        "pending_refund_requests": pending_refund_requests,
        "pending_withdrawal_requests": pending_withdrawal_requests,
        "pending_reseller_orders": pending_reseller_orders,
        "pending_wholeseller_orders": pending_wholeseller_orders,  # 🔥 IMPORTANT
    }