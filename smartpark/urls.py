from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('django-admin/', admin.site.urls),   # built-in database browser (log in with an admin account)
    path('', include('parking.urls')),         # everything else is in parking/urls.py
]
