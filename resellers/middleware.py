from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import render
from .models import Store


class SubdomainMiddleware(MiddlewareMixin):

    RESERVED_SUBDOMAINS = [
        'www',
        'admin',
        'api',
        'mail',
        'localhost',
        '127',
    ]

    MAIN_DOMAINS = [
        'drapso.com',
        'www.drapso.com',
        'localhost',
        '127.0.0.1',
    ]

    def process_request(self, request):

        host = request.get_host().split(':')[0].lower()

        request.subdomain = None
        request.current_store = None
        request.is_store_request = False

        # Skip static/media
        if request.path.startswith('/static/') or request.path.startswith('/media/'):
            return None

        # Skip main domains
        if host in self.MAIN_DOMAINS:
            return None

        # Remove www
        if host.startswith("www."):
            host = host[4:]

        parts = host.split('.')

        subdomain = None

        # localhost support
        # abc.localhost
        if len(parts) == 2 and parts[1] == 'localhost':
            subdomain = parts[0]

        # production support
        # abc.drapso.com
        elif len(parts) >= 3:
            subdomain = parts[0]

       
        # Ignore reserved subdomains
        if subdomain and subdomain not in self.RESERVED_SUBDOMAINS:

            request.subdomain = subdomain
            request.is_store_request = True

            # Find store
            store = Store.objects.filter(
                subdomain__iexact=subdomain
            ).first()

            print("STORE:", store)

            # Store not found
            if not store:

                return render(
                    request,
                    'resellers/store_not_found.html',
                    {
                        'subdomain': subdomain,
                        'reason': 'Store not found'
                    },
                    status=404
                )

            # Attach store to request
            request.current_store = store

        return None


class StoreContextMiddleware(MiddlewareMixin):

    def process_template_response(self, request, response):

        try:

            if hasattr(response, 'context_data') and response.context_data is not None:

                response.context_data['current_store'] = getattr(
                    request,
                    'current_store',
                    None
                )

                response.context_data['subdomain'] = getattr(
                    request,
                    'subdomain',
                    None
                )

                response.context_data['is_store_request'] = getattr(
                    request,
                    'is_store_request',
                    False
                )

        except Exception as e:

            print("StoreContextMiddleware Error:", e)

        return response