from django.conf import settings

def global_settings(request):
    return {
        "MAIN_DOMAIN": settings.MAIN_DOMAIN
    }