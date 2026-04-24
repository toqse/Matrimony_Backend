from django.urls import path

from .views import (
    AstrologyPdfJathakamDownloadView,
    AstrologyPdfOrderView,
    AstrologyPdfThalakuriDownloadView,
    AstrologyPdfVerifyView,
    BirthDetailCandidatesListView,
    GenerateHoroscopeView,
    HoroscopeChartView,
    HoroscopeDetailView,
    HoroscopeMeView,
    MatchReportPdfView,
    PoruthamCheckView,
    get_chart_data,
    get_match_chart_data,
    get_match_chart_data_partner,
)

app_name = 'astrology'

urlpatterns = [
    path(
        'birth-detail-candidates/',
        BirthDetailCandidatesListView.as_view(),
        name='birth_detail_candidates',
    ),
    path('pdf/order/', AstrologyPdfOrderView.as_view(), name='astrology_pdf_order'),
    path('pdf/verify/', AstrologyPdfVerifyView.as_view(), name='astrology_pdf_verify'),
    path('pdf/jathakam/', AstrologyPdfJathakamDownloadView.as_view(), name='astrology_pdf_jathakam'),
    path('pdf/thalakuri/', AstrologyPdfThalakuriDownloadView.as_view(), name='astrology_pdf_thalakuri'),
    path('generate/', GenerateHoroscopeView.as_view(), name='generate'),
    path('horoscope/me/', HoroscopeMeView.as_view(), name='horoscope_me'),
    path('horoscope/<int:profile_id>/', HoroscopeDetailView.as_view(), name='horoscope_detail'),
    path('horoscope/<int:profile_id>/chart/', HoroscopeChartView.as_view(), name='horoscope_chart'),
    path('match-report/', MatchReportPdfView.as_view(), name='match_report'),
    path('porutham/', PoruthamCheckView.as_view(), name='porutham'),
    path(
        'chart/<int:profile_id>/<str:chart_type>/',
        get_chart_data,
        name='chart-data',
    ),
    path(
        'chart/<int:profile_id>/',
        get_chart_data,
        {'chart_type': 'rasi'},
        name='chart-data-default',
    ),
    path(
        'match-chart/<int:bride_id>/<int:groom_id>/<str:chart_type>/',
        get_match_chart_data,
        name='match-chart-data',
    ),
    path(
        'match-chart/<int:bride_id>/<int:groom_id>/',
        get_match_chart_data,
        {'chart_type': 'rasi'},
        name='match-chart-data-default',
    ),
    path(
        'match-chart/<str:partner_matri_id>/<str:chart_type>/',
        get_match_chart_data_partner,
        name='match-chart-partner-data',
    ),
    path(
        'match-chart/<str:partner_matri_id>/',
        get_match_chart_data_partner,
        {'chart_type': 'rasi'},
        name='match-chart-partner-data-default',
    ),
]
