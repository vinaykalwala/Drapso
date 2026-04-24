from accounts.models import (
    CustomerProfile,
    WholesellerProfile,
    ResellerProfile,
    AdminProfile
)

from wholesellers.models import WholesellerKYC
from products.models import PriceChangeNotification
from orders.models import Refund


def user_profile_data(request):

    profile = None
    role = None
    pending_kyc_count = 0
    pending_price_notifications = 0
    pending_refund_requests = 0

    if request.user.is_authenticated:

        role = request.user.get_role_display()

        if request.user.role == "customer":
            profile = CustomerProfile.objects.filter(user=request.user).first()

        elif request.user.role == "wholeseller":
            profile = WholesellerProfile.objects.filter(user=request.user).first()

        elif request.user.role == "reseller":
            profile = ResellerProfile.objects.filter(user=request.user).first()

            pending_price_notifications = PriceChangeNotification.objects.filter(
                reseller=request.user,
                is_actioned=False
            ).count()

        elif request.user.role == "admin":
            profile = AdminProfile.objects.filter(user=request.user).first()

            # KYC count
            pending_kyc_count = WholesellerKYC.objects.filter(
                status__iexact="pending"
            ).count()

            # 🔥 REFUND COUNT (ROBUST FIX)
            pending_refund_requests = Refund.objects.filter(
                status__in=["pending", "requested", "processing"]
            ).count()

    return {
        "profile": profile,
        "role": role,
        "pending_kyc_count": pending_kyc_count,
        "pending_price_notifications": pending_price_notifications,
        "pending_refund_requests": pending_refund_requests
    }