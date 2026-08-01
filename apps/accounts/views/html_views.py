import logging

from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin #protects the view from unauthenticated users. If an unauthenticated user tries to access the view, they will be redirected to the login page.
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import FormView, TemplateView

from apps.accounts.forms import LoginForm
from apps.accounts.services import AuthenticationService

logger = logging.getLogger(__name__)


class LoginView(FormView):
    template_name = 'accounts/login.html'
    form_class = LoginForm
    success_url = reverse_lazy('accounts:dashboard')  # Redirect to dashboard after successful login

    def form_valid(self, form):
        username = form.cleaned_data['username'] # Django has already validated and cleaned the input.
        password = form.cleaned_data['password']

        logger.info("Browser login attempt for username=%s", username)

        user = AuthenticationService.login_user(self.request, username, password)

        if user is None:
            logger.warning("Browser login failed: invalid credentials for username=%s", username)
            form.add_error(None, "Invalid username or password")
            return self.form_invalid(form)

        logger.info("Browser login successful for user: %s (uuid=%s)", user.username, user.uuid)
        return super().form_valid(form) #If login succeeds -> redirect to success_url


class DashboardView(LoginRequiredMixin, TemplateView):  #protects the view from unauthenticated users. If an unauthenticated user tries to access the view, they will be redirected to the login page.
    template_name = "accounts/dashboard.html"   #settings ->redirection LOGIN_URL = "accounts:login"