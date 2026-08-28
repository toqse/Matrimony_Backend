from django.urls import path

from .views import TestimonialDetailAPIView, TestimonialListCreateAPIView

urlpatterns = [
    path("", TestimonialListCreateAPIView.as_view(), name="admin-testimonial-list-create"),
    path("<int:pk>/", TestimonialDetailAPIView.as_view(), name="admin-testimonial-detail"),
]
