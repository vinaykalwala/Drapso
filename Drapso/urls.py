from django.contrib import admin
from django.urls import include, path ,re_path
from django.conf.urls.static import static

from django.conf import settings
from general import views
from resellers.views import store_frontend


urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('wholesellers/',include('wholesellers.urls')),
    path('resellers/', include('resellers.urls')),
    path('privacy-policy/', views.privacy_policy, name='privacy_policy'),
    path('terms/', views.terms, name='terms'),
    path('about/', views.about, name='about'),

    path('contact/create/', views.contact_create, name='contact_create'),  
    path('contact/', views.contact_list, name='contact_list'), 

    path('contact/<int:pk>/', views.contact_detail, name='contact_detail'),
    path('contact/<int:pk>/delete/', views.contact_delete, name='contact_delete'),

    path('wholeseller-vendor-policy/', views.wholeseller_vendor_policy, name='wholeseller_vendor_policy'),
    path('reseller-seller-policy/', views.reseller_seller_policy, name='reseller_seller_policy'),
    path('community-guidelines/', views.community_guidelines, name='community_guidelines'),
    path('intellectual-property-policy/', views.intellectual_property_policy, name='intellectual_property_policy'),
    path('return-policy/', views.return_policy, name='return_policy'),
    path('shipping-delivery-policy/', views.shipping_delivery_policy, name='shipping_delivery_policy'),
    path('refund-cancellation-policy/', views.refund_cancellation_policy, name='refund_cancellation_policy'),
    path('cookie-policy/', views.cookie_policy, name='cookie_policy'),

     path('', views.home, name='home'),
    
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

