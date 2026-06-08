from django.urls import path

from .views import (
    AstrologyPdfJathakamDownloadView,
    AstrologyPdfOrderView,
    AstrologyPdfThalakuriDownloadView,
    AstrologyPdfVerifyView,
    HoroscopeProfileDetailView,
    HoroscopeProfileMeView,
    PoruthamCheckView,
    UpdateBirthCoordinatesView,
)

app_name = 'astrology'

urlpatterns = [
    path(
        'horoscope/me/',
        HoroscopeProfileMeView.as_view(),
        name='horoscope_me',
    ),
    path(
        'horoscope/<uuid:user_id>/',
        HoroscopeProfileDetailView.as_view(),
        name='horoscope_detail',
    ),
    path(
        'birth-coordinates/',
        UpdateBirthCoordinatesView.as_view(),
        name='birth_coordinates',
    ),
    path(
        'porutham/',
        PoruthamCheckView.as_view(),
        name='porutham',
    ),
    path(
        'pdf/order/',
        AstrologyPdfOrderView.as_view(),
        name='astrology_pdf_order',
    ),
    path(
        'pdf/verify/',
        AstrologyPdfVerifyView.as_view(),
        name='astrology_pdf_verify',
    ),
    path(
        'pdf/jathakam/',
        AstrologyPdfJathakamDownloadView.as_view(),
        name='astrology_pdf_jathakam',
    ),
    path(
        'pdf/thalakuri/',
        AstrologyPdfThalakuriDownloadView.as_view(),
        name='astrology_pdf_thalakuri',
    ),
]
