from django.urls import path

from .views import AdminAppConfigAPIView

urlpatterns = [
    path("", AdminAppConfigAPIView.as_view(), name="admin-app-config"),
]
