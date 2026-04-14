from resellers.models import Store

def reseller_store(request):

    store = None

    if request.user.is_authenticated and request.user.role == "reseller":

        store = Store.objects.filter(reseller=request.user).first()

    return {
        "store": store
    }