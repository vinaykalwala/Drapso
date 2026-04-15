# resellers/context_processors.py

from resellers.models import Store

def reseller_store(request):
    store = None

    if request.user.is_authenticated and getattr(request.user, "role", None) == "reseller":
        
        # create store automatically if not exists
        store, created = Store.objects.get_or_create(
            reseller=request.user
        )

    return {
        "store": store
    }