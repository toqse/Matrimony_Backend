"""
Auth URL routes.
"""
from django.urls import path

from .views import (
    RegisterView,
    VerifyOTPView,
    RegisterMobileView,
    VerifyMobileView,
    RegisterEmailView,
    VerifyEmailView,
    LoginView,
    TokenRefreshViewCustom,
    LogoutView,
    PasswordResetView,
    PasswordConfirmView,
)

urlpatterns = [
    path('register/', RegisterView.as_view()),
    path('verify-otp/', VerifyOTPView.as_view()),
    path('register/mobile/', RegisterMobileView.as_view()),
    path('verify/mobile/', VerifyMobileView.as_view()),
    path('register/email/', RegisterEmailView.as_view()),
    path('verify/email/', VerifyEmailView.as_view()),
    path('login/', LoginView.as_view()),
    path('token/refresh/', TokenRefreshViewCustom.as_view()),
    path('logout/', LogoutView.as_view()),
    path('password/reset/', PasswordResetView.as_view()),
    path('password/confirm/', PasswordConfirmView.as_view()),
]
