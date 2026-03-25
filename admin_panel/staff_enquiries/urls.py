from django.urls import path

from . import views

urlpatterns = [
    path("summary/", views.StaffEnquirySummaryView.as_view()),
    path("", views.StaffEnquiryListCreateView.as_view()),
    path("<int:pk>/", views.StaffEnquiryDetailView.as_view()),
    path("<int:pk>/move/", views.StaffEnquiryMoveView.as_view()),
    path("<int:pk>/notes/", views.StaffEnquiryAddNoteView.as_view()),
]
