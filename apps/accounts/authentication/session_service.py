from django.contrib.auth import logout
from .constants import SessionKeys


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

    @staticmethod
    def get_access_token(request):
        return request.session.get(SessionKeys.ACCESS_TOKEN)

    @staticmethod
    def get_refresh_token(request):
        return request.session.get(SessionKeys.REFRESH_TOKEN)

    @staticmethod
    def update_access_token(request, access_token):
        request.session[SessionKeys.ACCESS_TOKEN] = access_token
        request.session.modified = True

    @staticmethod
    def clear_session(request):
        """
        Logout user and clear the session.
        """

        logout(request)   # properly removes Django's authentication state.
        request.session.flush()     #creates a new empty session.