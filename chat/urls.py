from django.urls import path
from .views import ChatListView, ChatMessagesView, ChatUserStatusView
from plans.views import ChatPermissionView, ChatStartView

urlpatterns = [
    path('list/', ChatListView.as_view()),
    path('messages/<int:conversation_id>/', ChatMessagesView.as_view()),
    path('status/<str:matri_id>/', ChatUserStatusView.as_view()),
    path('start/', ChatStartView.as_view()),
    path('permission/<str:matri_id>/', ChatPermissionView.as_view()),
]
