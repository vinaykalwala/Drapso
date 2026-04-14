# theme_manager/urls.py
from django.urls import path
from . import views

app_name = 'theme_manager'

urlpatterns = [
    # Theme switching
    path('store/<int:store_id>/switch-to-single/', 
         views.switch_to_single_theme, 
         name='switch_to_single'),
    
    path('store/<int:store_id>/switch-to-multi/', 
         views.switch_to_multi_theme, 
         name='switch_to_multi'),
    
    # Archived products management
    path('store/<int:store_id>/archived/', 
         views.archived_products_list, 
         name='archived_products_list'),
    
    path('store/<int:store_id>/archived/restore/', 
         views.restore_archived_products, 
         name='restore_archived_products'),
    
    path('store/<int:store_id>/archived/batch/<int:batch_id>/', 
         views.restore_batch_status, 
         name='restore_batch_status'),
    
    # API endpoints
    path('store/<int:store_id>/status/', 
         views.theme_status_api, 
         name='theme_status_api'),
]