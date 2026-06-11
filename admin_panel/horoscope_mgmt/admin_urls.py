from django.urls import path

from .views import (
    AdminHoroscopePanelJathagamPdfDownloadView,
    AdminHoroscopePanelJathakamPdfsView,
    AdminHoroscopePanelPoruthamView,
    AdminHoroscopePanelRecordByMatriView,
    AdminHoroscopePanelRecordDetailView,
    AdminHoroscopePanelRecordsView,
    AdminHoroscopePanelSummaryView,
    AdminHoroscopePanelSyncView,
)

urlpatterns = [
    path("summary/", AdminHoroscopePanelSummaryView.as_view(), name="admin_horoscope_summary"),
    path("records/", AdminHoroscopePanelRecordsView.as_view(), name="admin_horoscope_records"),
    path("records/by-matri/<str:matri_id>/", AdminHoroscopePanelRecordByMatriView.as_view(), name="admin_horoscope_by_matri"),
    path(
        "jathagam/<int:horoscope_id>/",
        AdminHoroscopePanelJathagamPdfDownloadView.as_view(),
        name="admin_horoscope_jathagam_pdf",
    ),
    path("records/<uuid:user_id>/", AdminHoroscopePanelRecordDetailView.as_view(), name="admin_horoscope_record_detail"),
    path("porutham/", AdminHoroscopePanelPoruthamView.as_view(), name="admin_horoscope_porutham"),
    path("sync/", AdminHoroscopePanelSyncView.as_view(), name="admin_horoscope_sync"),
    path("jathakam-pdfs/", AdminHoroscopePanelJathakamPdfsView.as_view(), name="admin_horoscope_jathakam_pdfs"),
]
