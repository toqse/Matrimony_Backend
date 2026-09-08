from django.urls import path

from .views import MemberProfileReportCreateView

urlpatterns = [
    path('', MemberProfileReportCreateView.as_view()),
]
