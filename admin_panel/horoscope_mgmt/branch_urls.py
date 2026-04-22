from django.urls import path

from .views import (
    BranchHoroscopePanelJathakamPdfsView,
    BranchHoroscopePanelPoruthamView,
    BranchHoroscopePanelRecordByMatriView,
    BranchHoroscopePanelRecordDetailView,
    BranchHoroscopePanelRecordsView,
    BranchHoroscopePanelRegenerateView,
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
    path("records/<uuid:user_id>/", BranchHoroscopePanelRecordDetailView.as_view(), name="branch_horoscope_record_detail"),
    path(
        "records/<uuid:user_id>/regenerate/",
        BranchHoroscopePanelRegenerateView.as_view(),
        name="branch_horoscope_regenerate",
    ),
    path("porutham/", BranchHoroscopePanelPoruthamView.as_view(), name="branch_horoscope_porutham"),
    path("jathakam-pdfs/", BranchHoroscopePanelJathakamPdfsView.as_view(), name="branch_horoscope_jathakam_pdfs"),
]
