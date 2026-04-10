from django.utils.deprecation import MiddlewareMixin
from .models import Store


class SubdomainMiddleware(MiddlewareMixin):
    """
    Detect subdomain and route ALL subdomain traffic to store system
    """

    def process_request(self, request):
        host = request.get_host().split(':')[0]
        path = request.path_info  # Get the request path

        request.subdomain = None
        request.current_store = None
        request.is_store_request = False

        # 🔥 CRITICAL: Skip middleware for static and media files FIRST
        if path.startswith('/media/') or path.startswith('/static/'):
            return None

        # Skip main domain (preserved from your original code)
        if host in ['localhost', '127.0.0.1']:
            return None

        # Detect subdomain
        if '.' in host:
            parts = host.split('.')

            # storename.localhost
            if len(parts) == 2 and parts[1] == 'localhost':
                subdomain = parts[0]

            # storename.example.com
            elif len(parts) >= 3:
                subdomain = parts[0]
            else:
                subdomain = None

            if subdomain and subdomain not in ['www', 'admin', 'api', 'mail']:
                request.subdomain = subdomain
                request.is_store_request = True

        # 🔥 CRITICAL: ALWAYS route subdomain requests
        if request.is_store_request:
            store = Store.objects.filter(subdomain=request.subdomain).first()

            # even if store is None → pass to view
            request.current_store = store

            # force routing to reseller URLs
            request.urlconf = 'resellers.urls'

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