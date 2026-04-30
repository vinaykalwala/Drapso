def dynamic_base_template(request):
    base_template = "includes/multitheme_base.html"

    try:
        store = None

        # 1. URL
        store_id = None
        if request.resolver_match:
            store_id = request.resolver_match.kwargs.get("store_id")

        if store_id:
            store = Store.objects.filter(id=store_id).first()

        # 2. GET
        if not store:
            store_id = request.GET.get("store_id")
            if store_id:
                store = Store.objects.filter(id=store_id).first()

        # 3. Session
        if not store:
            store_id = request.session.get("store_id")
            if store_id:
                store = Store.objects.filter(id=store_id).first()

        # 4. Theme
        if store:
            session = ThemeSwitchSession.objects.filter(store_id=store.id).first()
            if session and session.current_theme == "single":
                base_template = "includes/singletheme_base.html"

    except Exception as e:
        print("❌ dynamic_base_template error:", e)  # <-- IMPORTANT

    # ✅ ALWAYS return a valid template
    return {
        "base_template": base_template or "includes/multitheme_base.html"
    }