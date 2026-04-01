from accounts.models import (
    CustomerProfile,
    WholesellerProfile,
    ResellerProfile,
    AdminProfile
)

def user_profile_data(request):

    profile = None
    role = None

    if request.user.is_authenticated:

        role = request.user.get_role_display()

        if request.user.role == "customer":
            profile = CustomerProfile.objects.filter(user=request.user).first()

        elif request.user.role == "wholeseller":
            profile = WholesellerProfile.objects.filter(user=request.user).first()

        elif request.user.role == "reseller":
            profile = ResellerProfile.objects.filter(user=request.user).first()

        elif request.user.role == "admin":
            profile = AdminProfile.objects.filter(user=request.user).first()

    return {
        "profile": profile,
        "role": role
    }