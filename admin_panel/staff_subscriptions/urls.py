from django.urls import path

from . import views

urlpatterns = [
    path("summary/", views.StaffSubscriptionSummaryView.as_view()),
    path("export/", views.StaffSubscriptionExportView.as_view()),
    path("<int:pk>/renew/", views.StaffSubscriptionRenewView.as_view()),
    path("<int:pk>/", views.StaffSubscriptionDetailView.as_view()),
    path("", views.StaffSubscriptionListCreateView.as_view()),
]
