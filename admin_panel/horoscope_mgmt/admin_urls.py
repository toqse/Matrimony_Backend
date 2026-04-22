from django.urls import path

from .views import (
    AdminHoroscopePanelJathakamPdfsView,
    AdminHoroscopePanelPoruthamView,
    AdminHoroscopePanelRecordByMatriView,
    AdminHoroscopePanelRecordDetailView,
    AdminHoroscopePanelRecordsView,
    AdminHoroscopePanelRegenerateView,
    AdminHoroscopePanelSummaryView,
)

urlpatterns = [
    path("summary/", AdminHoroscopePanelSummaryView.as_view(), name="admin_horoscope_summary"),
    path("records/", AdminHoroscopePanelRecordsView.as_view(), name="admin_horoscope_records"),
    path("records/by-matri/<str:matri_id>/", AdminHoroscopePanelRecordByMatriView.as_view(), name="admin_horoscope_by_matri"),
    path("records/<uuid:user_id>/", AdminHoroscopePanelRecordDetailView.as_view(), name="admin_horoscope_record_detail"),
    path(
        "records/<uuid:user_id>/regenerate/",
        AdminHoroscopePanelRegenerateView.as_view(),
        name="admin_horoscope_regenerate",
    ),
    path("porutham/", AdminHoroscopePanelPoruthamView.as_view(), name="admin_horoscope_porutham"),
    path("jathakam-pdfs/", AdminHoroscopePanelJathakamPdfsView.as_view(), name="admin_horoscope_jathakam_pdfs"),
]
