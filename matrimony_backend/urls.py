"""
URL configuration for matrimony_backend.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from profiles.views import PublicProfileByMatriIdView, ProfilePreviewByMatriIdView
from plans.views import MyPlanView, ContactUnlockView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('accounts.urls')),
    path('api/v1/profile/', include('profiles.urls')),
    path('api/v1/profiles/<str:matri_id>/preview/', ProfilePreviewByMatriIdView.as_view()),
    path('api/v1/profiles/<str:matri_id>/full/', PublicProfileByMatriIdView.as_view()),
    path('api/v1/profiles/<str:matri_id>/', PublicProfileByMatriIdView.as_view()),
    path('api/v1/master/', include('master.urls')),
    path('api/v1/matches/', include('matches.urls')),
    path('api/v1/interests/', include('plans.urls')),
    path('api/v1/wishlist/', include('wishlist.urls')),
    path('api/v1/plans/', include('plans.urls_plans')),
    path('api/v1/admin/plans/', include('plans.urls_admin_plans')),
    path('api/v1/chat/', include('chat.urls')),
    path('api/v1/settings/', include('user_settings.urls')),
    path('api/v1/contact/unlock/', ContactUnlockView.as_view()),
    path('api/v1/my/plan/', MyPlanView.as_view()),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
