from django.urls import path

from .views import (
    AdminProfileAssignStaffAPIView,
    AdminProfileBlockAPIView,
    AdminProfileDetailAPIView,
    AdminProfileListAPIView,
    AdminProfileMergeAPIView,
    AdminProfileVerifyAPIView,
)

urlpatterns = [
    path("", AdminProfileListAPIView.as_view(), name="admin-profiles-list"),
    path("merge/", AdminProfileMergeAPIView.as_view(), name="admin-profiles-merge"),
    path("<str:matri_id>/verify/", AdminProfileVerifyAPIView.as_view(), name="admin-profiles-verify"),
    path("<str:matri_id>/assign-staff/", AdminProfileAssignStaffAPIView.as_view(), name="admin-profiles-assign-staff"),
    path("<str:matri_id>/block/", AdminProfileBlockAPIView.as_view(), name="admin-profiles-block"),
    path("<str:matri_id>/", AdminProfileDetailAPIView.as_view(), name="admin-profiles-detail"),
]
