from django.urls import path

from .views import WishlistToggleView, WishlistListView, WishlistRemoveView

urlpatterns = [
    path('toggle/', WishlistToggleView.as_view()),
    path('', WishlistListView.as_view()),
    path('remove/', WishlistRemoveView.as_view()),
]

