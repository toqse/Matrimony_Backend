from django.urls import path
from .views import (
    ProfileSettingsView,
    ProfileVisibilityView,
    InterestPermissionView,
    NotificationSettingsView,
    AccountUpdateView,
    ChangePasswordView,
)

urlpatterns = [
    path('profile/', ProfileSettingsView.as_view()),
    path('profile-visibility/', ProfileVisibilityView.as_view()),
    path('interest-permission/', InterestPermissionView.as_view()),
    path('notifications/', NotificationSettingsView.as_view()),
    path('account/', AccountUpdateView.as_view()),
    path('change-password/', ChangePasswordView.as_view()),
]
