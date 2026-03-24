from django.urls import path

from .views import (
    GenerateHoroscopeView,
    HoroscopeChartView,
    HoroscopeDetailView,
    PoruthamCheckView,
)

urlpatterns = [
    path('generate/', GenerateHoroscopeView.as_view()),
    path('horoscope/<int:profile_id>/', HoroscopeDetailView.as_view()),
    path('horoscope/<int:profile_id>/chart/', HoroscopeChartView.as_view()),
    path('porutham/', PoruthamCheckView.as_view()),
]
