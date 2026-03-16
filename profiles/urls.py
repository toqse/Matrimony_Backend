from django.urls import path
from .views import (
    ProfileDetailView,
    BasicDetailsView,
    ProfileLocationView,
    ProfileReligionView,
    PartnerPreferencesView,
    ProfilePersonalView,
    ProfileFamilyView,
    ProfileEducationView,
    ProfileGenerateAboutView,
    ProfileAboutView,
    ProfilePhotosView,
    ProfileCompleteView,
)

urlpatterns = [
    path('', ProfileDetailView.as_view()),
    path('basic/', BasicDetailsView.as_view()),
    path('location/', ProfileLocationView.as_view()),
    path('religion/', ProfileReligionView.as_view()),
    path('partner-preferences/', PartnerPreferencesView.as_view()),
    path('personal/', ProfilePersonalView.as_view()),
    path('family/', ProfileFamilyView.as_view()),
    path('education/', ProfileEducationView.as_view()),
    path('generate-about/', ProfileGenerateAboutView.as_view()),
    path('about/', ProfileAboutView.as_view()),
    path('photos/', ProfilePhotosView.as_view()),
    path('complete/', ProfileCompleteView.as_view()),
]
