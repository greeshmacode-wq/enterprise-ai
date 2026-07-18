import logging

from django.contrib.auth import logout
from .constants import SessionKeys

logger = logging.getLogger(__name__)


class SessionService:
    """
    Handles storing and retrieving authentication data
    from the Django session.
    """

    @staticmethod
    def create_session(request, user, tokens):
        """
        Store user and token information in the session.
        """
        request.session[SessionKeys.ACCESS_TOKEN] = tokens["access"]
        request.session[SessionKeys.REFRESH_TOKEN] = tokens["refresh"]

        request.session[SessionKeys.USER_UUID] = str(user.uuid)
        request.session[SessionKeys.USERNAME] = user.username

        request.session[SessionKeys.LOGIN_TYPE] = "browser"

        request.session.modified = True

        logger.info(
            "Session created for user: %s (uuid=%s, login_type=browser)",
            user.username, user.uuid,
        )

    @staticmethod
    def get_access_token(request):
        token = request.session.get(SessionKeys.ACCESS_TOKEN)
        logger.debug("Retrieved access token from session: %s...", token[:20] if token else None)
        return token

    @staticmethod
    def get_refresh_token(request):
        token = request.session.get(SessionKeys.REFRESH_TOKEN)
        logger.debug("Retrieved refresh token from session: %s...", token[:20] if token else None)
        return token

    @staticmethod
    def update_access_token(request, access_token):
        request.session[SessionKeys.ACCESS_TOKEN] = access_token
        request.session.modified = True
        logger.debug("Access token updated in session")

    @staticmethod
    def clear_session(request):
        """
        Logout user and clear the session.
        """
        logger.info("Clearing session for user: %s", request.user.username if request.user.is_authenticated else "anonymous")

        logout(request)   # properly removes Django's authentication state.
        request.session.flush()     #creates a new empty session.