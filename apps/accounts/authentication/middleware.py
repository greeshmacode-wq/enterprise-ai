import logging
from django.conf import settings
from django.shortcuts import redirect
from rest_framework_simplejwt.exceptions import TokenError
from .session_service import SessionService
from .token_service import TokenService
logger = logging.getLogger(__name__)


class JWTRefreshMiddleware:
    """
    Middleware responsible for validating the JWT stored in
    the Django session.

    Flow:

        Request
            ↓
        Skip public URLs
            ↓
        Skip anonymous users
            ↓
        Validate access token
            ↓
        Expired?
            ↓
        Refresh access token
            ↓
        Update session
            ↓
        Continue request

    If both access and refresh tokens are invalid,
    the user is logged out and redirected to login.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):  # executes for every request

        if self._is_excluded(request):
            return self.get_response(request)
        #Skip Anonymous User->Suppose user opens ->/login No authentication yet.Middleware should simply continue.
        if not request.user.is_authenticated:
            return self.get_response(request)

        if not self._validate_session(request):
            logger.warning("Authentication tokens missing from session.")
            SessionService.clear_session(request)
            return redirect(settings.LOGIN_URL)

        access_token = SessionService.get_access_token(request)

        try:
            TokenService.validate_access_token(access_token) #SimpleJWT checks->Signature,Expiration,Token Format

        except TokenError:

            logger.info("Access token expired. Attempting refresh.")
            if not self._refresh_access_token(request):
                logger.warning("Refresh token invalid or expired. Logging out user.")
                SessionService.clear_session(request)
                return redirect(settings.LOGIN_URL)

        return self.get_response(request)

    # -------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------

    def _is_excluded(self, request):
        """
        Skip authentication for public URLs.
        """

        resolver_match = getattr(request, "resolver_match", None)

        if resolver_match is None:
            return False

        return (resolver_match.view_name in settings.AUTH_EXCLUDED_URLS)

    def _validate_session(self, request):
        """
        Ensure authentication tokens exist in the session.
        """

        access_token = SessionService.get_access_token(request)
        refresh_token = SessionService.get_refresh_token(request)

        return (
            access_token is not None
            and refresh_token is not None
        )

    def _refresh_access_token(self, request):
        """
        Generate a new access token using the refresh token.
        """
        refresh_token = SessionService.get_refresh_token(request)
        try:
            new_access_token = (TokenService.refresh_access_token(refresh_token))
            SessionService.update_access_token(request,new_access_token, )

            logger.info("Access token refreshed successfully.")

            return True

        except TokenError:

            return False

        except Exception:

            logger.exception("Unexpected error while refreshing access token.")

            return False