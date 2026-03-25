from django.urls import path

from .views import (
    StaffMyProfilesCreateView,
    StaffMyProfilesDetailView,
    StaffMyProfilesDocumentsView,
    StaffMyProfilesListView,
    StaffMyProfilesRefreshView,
    StaffMyProfilesSendEmailView,
    StaffMyProfilesSummaryView,
    StaffMyProfilesWishlistView,
)

urlpatterns = [
    path("summary/", StaffMyProfilesSummaryView.as_view(), name="staff-my-profiles-summary"),
    path("create/", StaffMyProfilesCreateView.as_view(), name="staff-my-profiles-create"),
    path("<str:matri_id>/refresh/", StaffMyProfilesRefreshView.as_view(), name="staff-my-profiles-refresh"),
    path("<str:matri_id>/wishlist/", StaffMyProfilesWishlistView.as_view(), name="staff-my-profiles-wishlist"),
    path("<str:matri_id>/documents/", StaffMyProfilesDocumentsView.as_view(), name="staff-my-profiles-documents"),
    path("<str:matri_id>/send-email/", StaffMyProfilesSendEmailView.as_view(), name="staff-my-profiles-send-email"),
    path("<str:matri_id>/", StaffMyProfilesDetailView.as_view(), name="staff-my-profiles-detail"),
    path("", StaffMyProfilesListView.as_view(), name="staff-my-profiles-list"),
]
