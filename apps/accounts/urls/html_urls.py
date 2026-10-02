from django.contrib.auth.views import LogoutView
from django.urls import path

from apps.accounts.views.html_views import CurrentTokenView, LoginView, DashboardView

app_name = 'accounts'
urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(next_page='accounts:login'), name='logout'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('token/', CurrentTokenView.as_view(), name='current-token'),
]