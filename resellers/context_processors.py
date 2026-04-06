# resellers/context_processors.py

def store_context(request):
    """Add store and domain info to all templates"""
    
    context = {}
    
    if hasattr(request, 'current_store') and request.current_store:
        context['current_store'] = request.current_store
        context['store_url'] = request.current_store.get_full_url(request)
    
    if hasattr(request, 'subdomain'):
        context['subdomain'] = request.subdomain
    
    if hasattr(request, 'base_domain'):
        context['base_domain'] = request.base_domain
    
    host = request.get_host().split(':')[0]
    context['current_host'] = host
    context['is_store_subdomain'] = len(host.split('.')) >= 3
    
    def build_store_url(store_subdomain):
        """Helper to build store URL dynamically"""
        if hasattr(request, 'base_domain') and request.base_domain:
            return f"https://{store_subdomain}.{request.base_domain}"
        return f"https://{store_subdomain}.{host}"
    
    context['build_store_url'] = build_store_url
    
    return context# resellers/context_processors.py

def store_context(request):
    """Add store and domain info to all templates"""
    
    context = {}
    
    if hasattr(request, 'current_store') and request.current_store:
        context['current_store'] = request.current_store
        context['store_url'] = request.current_store.get_full_url(request)
    
    if hasattr(request, 'subdomain'):
        context['subdomain'] = request.subdomain
    
    if hasattr(request, 'base_domain'):
        context['base_domain'] = request.base_domain
    
    host = request.get_host().split(':')[0]
    context['current_host'] = host
    context['is_store_subdomain'] = len(host.split('.')) >= 3
    
    def build_store_url(store_subdomain):
        """Helper to build store URL dynamically"""
        if hasattr(request, 'base_domain') and request.base_domain:
            return f"https://{store_subdomain}.{request.base_domain}"
        return f"https://{store_subdomain}.{host}"
    
    context['build_store_url'] = build_store_url
    
    return context