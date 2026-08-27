from django.urls import path

from .views import (
    BranchHoroscopePanelJathagamPdfDownloadView,
    BranchHoroscopePanelJathakamPdfsView,
    BranchHoroscopePanelMatchReportView,
    BranchHoroscopePanelPoruthamView,
    BranchHoroscopePanelRecordByMatriView,
    BranchHoroscopePanelRecordDetailView,
    BranchHoroscopePanelRecordsView,
    BranchHoroscopePanelSavedPoruthamView,
    BranchHoroscopePanelSummaryView,
)

urlpatterns = [
    path("summary/", BranchHoroscopePanelSummaryView.as_view(), name="branch_horoscope_summary"),
    path("records/", BranchHoroscopePanelRecordsView.as_view(), name="branch_horoscope_records"),
    path(
        "records/by-matri/<str:matri_id>/",
        BranchHoroscopePanelRecordByMatriView.as_view(),
        name="branch_horoscope_by_matri",
    ),
    path(
        "jathagam/<int:horoscope_id>/",
        BranchHoroscopePanelJathagamPdfDownloadView.as_view(),
        name="branch_horoscope_jathagam_pdf",
    ),
    path("records/<uuid:user_id>/", BranchHoroscopePanelRecordDetailView.as_view(), name="branch_horoscope_record_detail"),
    path("porutham/", BranchHoroscopePanelPoruthamView.as_view(), name="branch_horoscope_porutham"),
    path("porutham/saved/", BranchHoroscopePanelSavedPoruthamView.as_view(), name="branch_horoscope_porutham_saved"),
    path("match-report/", BranchHoroscopePanelMatchReportView.as_view(), name="branch_horoscope_match_report"),
    path("jathakam-pdfs/", BranchHoroscopePanelJathakamPdfsView.as_view(), name="branch_horoscope_jathakam_pdfs"),
]
