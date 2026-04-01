from django.contrib import admin
from django.urls import include, path
from django.conf.urls.static import static

from django.conf import settings
from general import views


urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('', views.home, name='home'),
    path('privacy-policy/', views.privacy_policy, name='privacy_policy'),
    path('terms/', views.terms, name='terms'),
    path('about/', views.about, name='about'),

    path('contact/create/', views.contact_create, name='contact_create'),  
    path('contact/', views.contact_list, name='contact_list'), 

    path('contact/<int:pk>/', views.contact_detail, name='contact_detail'),
    path('contact/<int:pk>/delete/', views.contact_delete, name='contact_delete'),



]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
