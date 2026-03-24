from django.urls import path

from .views import (
    MyProfilesCreateView,
    MyProfilesDetailView,
    MyProfilesDocumentsView,
    MyProfilesListView,
    MyProfilesRefreshView,
    MyProfilesSendEmailView,
    MyProfilesSummaryView,
    MyProfilesVerifyView,
    MyProfilesWishlistView,
)

urlpatterns = [
    path("summary/", MyProfilesSummaryView.as_view(), name="my-profiles-summary"),
    path("create/", MyProfilesCreateView.as_view(), name="my-profiles-create"),
    path("<str:matri_id>/verify/", MyProfilesVerifyView.as_view(), name="my-profiles-verify"),
    path("<str:matri_id>/refresh/", MyProfilesRefreshView.as_view(), name="my-profiles-refresh"),
    path("<str:matri_id>/wishlist/", MyProfilesWishlistView.as_view(), name="my-profiles-wishlist"),
    path("<str:matri_id>/documents/", MyProfilesDocumentsView.as_view(), name="my-profiles-documents"),
    path("<str:matri_id>/send-email/", MyProfilesSendEmailView.as_view(), name="my-profiles-send-email"),
    path("<str:matri_id>/", MyProfilesDetailView.as_view(), name="my-profiles-detail"),
    path("", MyProfilesListView.as_view(), name="my-profiles-list"),
]
