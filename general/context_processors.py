from django.conf import settings

def global_settings(request):
    data = {
        "MAIN_DOMAIN": settings.MAIN_DOMAIN
    }

    if request.user.is_authenticated and hasattr(request.user, "role"):
        if request.user.role == "reseller":
            from resellers.models import Store

            # ✅ FIX HERE
            store = Store.objects.filter(reseller=request.user).first()

            data["store"] = store

    return data