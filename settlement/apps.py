from django.apps import AppConfig

class SettlementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'settlement'
    
    def ready(self):
        import settlement.signals