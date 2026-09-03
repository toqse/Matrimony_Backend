from django.urls import path

from .views import AdminMsgConfigAPIView

urlpatterns = [
    path("", AdminMsgConfigAPIView.as_view(), name="admin-msg-config"),
]
