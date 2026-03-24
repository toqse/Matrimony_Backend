from django.urls import path

from .views import (
    PublishSuccessStoryAPIView,
    SuccessStoryDetailAPIView,
    SuccessStoryListCreateAPIView,
    ToggleFeaturedSuccessStoryAPIView,
)

urlpatterns = [
    path("", SuccessStoryListCreateAPIView.as_view(), name="admin-success-story-list-create"),
    path("<int:pk>/", SuccessStoryDetailAPIView.as_view(), name="admin-success-story-detail"),
    path("<int:pk>/publish/", PublishSuccessStoryAPIView.as_view(), name="admin-success-story-publish"),
    path(
        "<int:pk>/toggle-featured/",
        ToggleFeaturedSuccessStoryAPIView.as_view(),
        name="admin-success-story-toggle-featured",
    ),
]
