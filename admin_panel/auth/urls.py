from django.urls import path

from .views import (
    AdminChangePhoneSendOTPView,
    AdminChangePhoneVerifyOTPView,
    AdminMyProfileView,
    LogoutView,
    SendOTPView,
    TokenRefreshView,
    VerifyOTPView,
)


urlpatterns = [
    path("send-otp/", SendOTPView.as_view()),
    path("verify-otp/", VerifyOTPView.as_view()),
    path("token/refresh/", TokenRefreshView.as_view()),
    path("logout/", LogoutView.as_view()),
    path("me/", AdminMyProfileView.as_view()),
    path("me/change-phone/send-otp/", AdminChangePhoneSendOTPView.as_view()),
    path("me/change-phone/verify-otp/", AdminChangePhoneVerifyOTPView.as_view()),
]

