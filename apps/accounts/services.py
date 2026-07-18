import logging

from django.contrib.auth import authenticate, login, logout

from apps.accounts.authentication.session_service import SessionService
from apps.accounts.authentication.token_service import TokenService

logger = logging.getLogger(__name__)


class AuthenticationService:
    """
    Handles all authentication related business logic.
    """

    @staticmethod
    def login_user(request, username: str, password: str):
        """
        Authenticate user, generate JWT tokens and store them in the Django session.

        Flow:
            1. authenticate()  →  Django validates credentials
            2. login()         →  Django creates session + sets session cookie
            3. TokenService    →  Generates JWT access + refresh tokens
            4. SessionService  →  Stores tokens & user info in session

        This ensures JWTRefreshMiddleware can validate tokens on subsequent requests.
        """
        user = authenticate(request=request, username=username, password=password) #validates credentials
        if user is None:
            logger.warning("Login failed: invalid credentials for username=%s", username)
            return None

        logger.info("Login successful for user: %s (uuid=%s)", user.username, user.uuid)

        # 1. Create Django session (session cookie)
        login(request, user)

        # 2. Generate JWT tokens with custom claims
        tokens = TokenService.generate_tokens(user)

        # 3. Store tokens in session for middleware validation
        SessionService.create_session(request, user, tokens)

        return user

    @staticmethod
    def logout_user(request):
        """
        Clear JWT tokens from session and log out.
        """
        logger.info("Logging out user: %s", request.user.username if request.user.is_authenticated else "anonymous")
        SessionService.clear_session(request)