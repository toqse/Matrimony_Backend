"""URLs for admin Plan CRUD."""
from rest_framework.routers import DefaultRouter
from .views import AdminPlanViewSet

router = DefaultRouter()
router.register(r'', AdminPlanViewSet, basename='admin-plan')
urlpatterns = router.urls
