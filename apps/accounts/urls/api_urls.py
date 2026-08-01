from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.views.api_views import LoginAPIView, LogoutAPIView


app_name = "accounts-api"

urlpatterns = [
    path("login/", LoginAPIView.as_view(), name="api-login"),
    path("logout/", LogoutAPIView.as_view(), name="api-logout"),
    path("token/refresh/", TokenRefreshView.as_view(), name="api-token-refresh"), #`rest_framework_simplejwt.views.TokenRefreshView` (built-in)
]
