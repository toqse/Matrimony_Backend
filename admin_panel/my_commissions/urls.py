from django.urls import path

from .views import (
    MyCommissionDetailView,
    MyCommissionsExportView,
    MyCommissionsListView,
    MyCommissionsSummaryView,
)

urlpatterns = [
    path("summary/", MyCommissionsSummaryView.as_view(), name="my-commissions-summary"),
    path("export/", MyCommissionsExportView.as_view(), name="my-commissions-export"),
    path("<int:pk>/", MyCommissionDetailView.as_view(), name="my-commissions-detail"),
    path("", MyCommissionsListView.as_view(), name="my-commissions-list"),
]
