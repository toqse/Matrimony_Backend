from django.urls import path

from . import views

urlpatterns = [
    path("", views.EnquiryListCreateView.as_view()),
    path("kanban/", views.EnquiryKanbanView.as_view()),
    path("<int:pk>/", views.EnquiryDetailView.as_view()),
    path("<int:pk>/move/", views.EnquiryMoveView.as_view()),
    path("<int:pk>/assign/", views.EnquiryAssignView.as_view()),
    path("<int:pk>/notes/", views.EnquiryAddNoteView.as_view()),
]
