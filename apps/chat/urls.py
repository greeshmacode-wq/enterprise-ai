from django.urls import path

from apps.chat.views import ChatView

app_name = "chat"

urlpatterns = [
    path("", ChatView.as_view(), name="chat"),
]
