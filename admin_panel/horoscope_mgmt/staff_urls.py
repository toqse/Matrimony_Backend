from django.urls import path

from .views import (
    StaffHoroscopePanelJathakamPdfsView,
    StaffHoroscopePanelPoruthamView,
    StaffHoroscopePanelRecordByMatriView,
    StaffHoroscopePanelRecordDetailView,
    StaffHoroscopePanelRecordsView,
    StaffHoroscopePanelSummaryView,
)

urlpatterns = [
    path("summary/", StaffHoroscopePanelSummaryView.as_view(), name="staff_horoscope_summary"),
    path("records/", StaffHoroscopePanelRecordsView.as_view(), name="staff_horoscope_records"),
    path("records/by-matri/<str:matri_id>/", StaffHoroscopePanelRecordByMatriView.as_view(), name="staff_horoscope_by_matri"),
    path("records/<uuid:user_id>/", StaffHoroscopePanelRecordDetailView.as_view(), name="staff_horoscope_record_detail"),
    path("porutham/", StaffHoroscopePanelPoruthamView.as_view(), name="staff_horoscope_porutham"),
    path("jathakam-pdfs/", StaffHoroscopePanelJathakamPdfsView.as_view(), name="staff_horoscope_jathakam_pdfs"),
]
