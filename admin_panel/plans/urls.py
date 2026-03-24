from rest_framework.routers import DefaultRouter

from .views import AdminPlansViewSet

router = DefaultRouter()
router.register(r"", AdminPlansViewSet, basename="admin-plans")

urlpatterns = router.urls
