from django.urls import path

from .views import AdminProfileReportListView, AdminProfileReportStatusView

urlpatterns = [
    path('', AdminProfileReportListView.as_view(), name='admin-profile-reports-list'),
    path('<int:report_id>/', AdminProfileReportStatusView.as_view(), name='admin-profile-reports-status'),
]
