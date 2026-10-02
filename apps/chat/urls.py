from django.urls import path

from apps.chat.views import ChatPageView

app_name = "chat"

urlpatterns = [
    path("", ChatPageView.as_view(), name="chat"),
]
