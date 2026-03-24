from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import BranchViewSet, BranchSummaryAPIView

# Router for ViewSet
router = DefaultRouter()
router.register(r'', BranchViewSet, basename='branches')

urlpatterns = [
    # Summary API (must be before router)
    path('summary/', BranchSummaryAPIView.as_view(), name='branch-summary'),

    # All CRUD + toggle APIs
    path('', include(router.urls)),
]