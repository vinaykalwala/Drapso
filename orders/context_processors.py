def dynamic_base_template(request):
    base_template = "includes/multitheme_base.html"

    try:
        store = getattr(request, "store", None)

        if store and store.theme:
            if store.theme.theme_type == "single":
                base_template = "includes/singletheme_base.html"

    except Exception:
        pass

    return {
        "base_template": base_template
    }