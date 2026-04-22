from django.urls import path

from .section_edit_views import (
    AdminProfileAboutSectionView,
    AdminProfileBasicSectionView,
    AdminProfileEducationSectionView,
    AdminProfileLocationSectionView,
    AdminProfilePersonalSectionView,
    AdminProfilePhotosSectionView,
    AdminProfileReligionSectionView,
)
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
    path("<str:matri_id>/basic/", AdminProfileBasicSectionView.as_view(), name="admin-profiles-section-basic"),
    path("<str:matri_id>/location/", AdminProfileLocationSectionView.as_view(), name="admin-profiles-section-location"),
    path("<str:matri_id>/religion/", AdminProfileReligionSectionView.as_view(), name="admin-profiles-section-religion"),
    path("<str:matri_id>/personal/", AdminProfilePersonalSectionView.as_view(), name="admin-profiles-section-personal"),
    path("<str:matri_id>/education/", AdminProfileEducationSectionView.as_view(), name="admin-profiles-section-education"),
    path("<str:matri_id>/about/", AdminProfileAboutSectionView.as_view(), name="admin-profiles-section-about"),
    path("<str:matri_id>/photos/", AdminProfilePhotosSectionView.as_view(), name="admin-profiles-section-photos"),
    path("<str:matri_id>/verify/", AdminProfileVerifyAPIView.as_view(), name="admin-profiles-verify"),
    path("<str:matri_id>/assign-staff/", AdminProfileAssignStaffAPIView.as_view(), name="admin-profiles-assign-staff"),
    path("<str:matri_id>/block/", AdminProfileBlockAPIView.as_view(), name="admin-profiles-block"),
    path("<str:matri_id>/", AdminProfileDetailAPIView.as_view(), name="admin-profiles-detail"),
]
