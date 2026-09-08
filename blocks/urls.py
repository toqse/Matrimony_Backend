from django.urls import path

from .views import BlockListCreateDeleteView

urlpatterns = [
    path('', BlockListCreateDeleteView.as_view()),
]
