from django.urls import path

from .views import (
    StaffHoroscopePanelJathagamPdfDownloadView,
    StaffHoroscopePanelJathakamPdfsView,
    StaffHoroscopePanelMatchReportView,
    StaffHoroscopePanelPoruthamView,
    StaffHoroscopePanelRecordByMatriView,
    StaffHoroscopePanelRecordDetailView,
    StaffHoroscopePanelRecordsView,
    StaffHoroscopePanelSavedPoruthamView,
    StaffHoroscopePanelSummaryView,
)

urlpatterns = [
    path("summary/", StaffHoroscopePanelSummaryView.as_view(), name="staff_horoscope_summary"),
    path("records/", StaffHoroscopePanelRecordsView.as_view(), name="staff_horoscope_records"),
    path("records/by-matri/<str:matri_id>/", StaffHoroscopePanelRecordByMatriView.as_view(), name="staff_horoscope_by_matri"),
    path(
        "jathagam/<int:horoscope_id>/",
        StaffHoroscopePanelJathagamPdfDownloadView.as_view(),
        name="staff_horoscope_jathagam_pdf",
    ),
    path("records/<uuid:user_id>/", StaffHoroscopePanelRecordDetailView.as_view(), name="staff_horoscope_record_detail"),
    path("porutham/", StaffHoroscopePanelPoruthamView.as_view(), name="staff_horoscope_porutham"),
    path("porutham/saved/", StaffHoroscopePanelSavedPoruthamView.as_view(), name="staff_horoscope_porutham_saved"),
    path("match-report/", StaffHoroscopePanelMatchReportView.as_view(), name="staff_horoscope_match_report"),
    path("jathakam-pdfs/", StaffHoroscopePanelJathakamPdfsView.as_view(), name="staff_horoscope_jathakam_pdfs"),
]
