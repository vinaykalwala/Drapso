def store_context(request):
    context = {}

    # ===== PUBLIC STORE (no change) =====
    if hasattr(request, 'current_store') and request.current_store:
        context['current_store'] = request.current_store
        context['store_url'] = request.current_store.get_full_url(request)

    # ===== RESELLER STORE (FIXED PROPERLY) =====
    store = None

    if request.user.is_authenticated and getattr(request.user, 'role', None) == "reseller":
        
        # Try OneToOne relation first
        store = getattr(request.user, 'store', None)

        # If not found, fallback to ForeignKey relation
        if not store:
            store_qs = getattr(request.user, 'store_set', None)
            if store_qs:
                store = store_qs.first()

    context['store'] = store

    # ===== EXISTING DOMAIN LOGIC =====
    if hasattr(request, 'subdomain'):
        context['subdomain'] = request.subdomain

    if hasattr(request, 'base_domain'):
        context['base_domain'] = request.base_domain

    host = request.get_host().split(':')[0]
    context['current_host'] = host
    context['is_store_subdomain'] = len(host.split('.')) >= 3

    def build_store_url(store_subdomain):
        if hasattr(request, 'base_domain') and request.base_domain:
            return f"https://{store_subdomain}.{request.base_domain}"
        return f"https://{store_subdomain}.{host}"

    context['build_store_url'] = build_store_url

    return context