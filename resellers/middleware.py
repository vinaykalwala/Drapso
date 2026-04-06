from django.utils.deprecation import MiddlewareMixin
from .models import Store


class SubdomainMiddleware(MiddlewareMixin):
    """
    Detect subdomain and switch URLConf dynamically
    """

    def process_request(self, request):
        host = request.get_host().split(':')[0]

        request.subdomain = None
        request.current_store = None
        request.is_store_request = False

        # Skip localhost without subdomain
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

        # Fetch store
        if request.is_store_request:
            store = Store.objects.filter(
                subdomain=request.subdomain,
                is_published=True,
                status='active'
            ).first()

            if store:
                request.current_store = store

                # 🔥 CRITICAL FIX: switch URL routing
                request.urlconf = 'resellers.urls'

        return None


class StoreContextMiddleware(MiddlewareMixin):
    """
    Inject store into templates
    """

    def process_template_response(self, request, response):
        if hasattr(response, 'context_data'):

            if getattr(request, 'current_store', None):
                response.context_data['current_store'] = request.current_store

            response.context_data['subdomain'] = getattr(request, 'subdomain', None)
            response.context_data['is_store_request'] = getattr(request, 'is_store_request', False)

        return response