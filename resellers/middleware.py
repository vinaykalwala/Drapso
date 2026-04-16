# resellers/middleware.py
from django.utils.deprecation import MiddlewareMixin
from django.urls import set_urlconf
from .models import Store


class SubdomainMiddleware(MiddlewareMixin):
    """
    Detect subdomain and route store requests to resellers.urls
    """

    def process_request(self, request):
        host = request.get_host().split(':')[0]
        path = request.path_info

        request.subdomain = None
        request.current_store = None
        request.is_store_request = False

        # Skip static/media files
        if path.startswith('/media/') or path.startswith('/static/'):
            return None

        # Skip main domain
        if host in ['localhost', '127.0.0.1', 'www.localhost']:
            return None

        # Detect subdomain
        subdomain = None
        if '.' in host:
            parts = host.split('.')
            if len(parts) == 2 and parts[1] == 'localhost':
                subdomain = parts[0]
            elif len(parts) >= 3:
                subdomain = parts[0]

        if subdomain and subdomain not in ['www', 'admin', 'api', 'mail']:
            request.subdomain = subdomain
            request.is_store_request = True
            
            # Get store (don't fail if not found)
            request.current_store = Store.objects.filter(subdomain=subdomain).first()
            
            # ONLY switch URLconf for store frontend paths, NOT for API/orders paths
            # Check if the path is for store frontend (not admin, not orders, not products)
            is_store_frontend = not (
                path.startswith('/admin/') or 
                path.startswith('/accounts/') or 
                path.startswith('/products/') or 
                path.startswith('/orders/') or
                path.startswith('/api/')
            )
            
            if is_store_frontend and request.current_store:
                # Route to store URLs
                request.urlconf = 'resellers.urls'
            # Otherwise, let the default URLconf handle it

        return None


class StoreContextMiddleware(MiddlewareMixin):
    """
    Inject store into templates
    """

    def process_template_response(self, request, response):
        if hasattr(response, 'context_data'):
            response.context_data['current_store'] = getattr(request, 'current_store', None)
            response.context_data['subdomain'] = getattr(request, 'subdomain', None)
            response.context_data['is_store_request'] = getattr(request, 'is_store_request', False)

        return response