from theme_manager.models import ThemeSwitchSession
from resellers.models import Store

def dynamic_base_template(request):
    base_template = "includes/multitheme_base.html"

    try:
        store = None

        # ✅ 1. Try from URL (MOST IMPORTANT)
        store_id = request.resolver_match.kwargs.get("store_id") if request.resolver_match else None

        if store_id:
            store = Store.objects.filter(id=store_id).first()

        # ✅ 2. Try from GET (for checkout/payment)
        if not store:
            store_id = request.GET.get("store_id")
            if store_id:
                store = Store.objects.filter(id=store_id).first()

        # ✅ 3. Try from session (fallback)
        if not store:
            store_id = request.session.get("store_id")
            if store_id:
                store = Store.objects.filter(id=store_id).first()

        # ✅ 4. Apply theme
        if store:
            session = ThemeSwitchSession.objects.filter(store_id=store.id).first()
            if session and session.current_theme == "single":
                base_template = "includes/singletheme_base.html"

    except Exception:
        pass

    return {
        "base_template": base_template
    }