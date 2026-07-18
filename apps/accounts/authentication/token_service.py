from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from .constants import TokenClaims


class TokenService:   
    """
    Handles JWT token generation, validation and refresh.
    """
    #Passwords should never be inside a JWT.
    #tokens are stored inside the Django session.
    @staticmethod
    def generate_tokens(user):
        """
        Generate access and refresh tokens for a user.
        """
        refresh = RefreshToken.for_user(user) #header + payload +signature [secret key]
        # ----------------------------
        # Custom Refresh Token Claims
        # ----------------------------
        refresh[TokenClaims.USER_UUID] = str(user.uuid)
        refresh[TokenClaims.USERNAME] = user.username
        refresh[TokenClaims.EMAIL] = user.email
        refresh[TokenClaims.DEPARTMENT] = user.department
        refresh[TokenClaims.DESIGNATION] = user.designation
        
        access = refresh.access_token
        # ----------------------------
        # Custom Access Token Claims
        # ----------------------------
        access[TokenClaims.USER_UUID] = str(user.uuid)
        access[TokenClaims.USERNAME] = user.username
        access[TokenClaims.EMAIL] = user.email
        access[TokenClaims.DEPARTMENT] = user.department
        access[TokenClaims.DESIGNATION] = user.designation

        return {
            "refresh": str(refresh),
            "access": str(access),
        }

    @staticmethod
    def validate_access_token(token):  # middleware will call this function to validate the access token. If valid, it returns the decoded token. If expired or invalid, it raises TokenError.
        """
        Validate an access token.        

        Raises TokenError if invalid.
        """
        return AccessToken(token)  

    @staticmethod
    def refresh_access_token(refresh_token): #when a user's access token expires. -> The client can send the refresh token to the server to get a new access token. This function will be called in the view that handles the refresh token endpoint.
        """
        Generate a new access token from a refresh token.
        """
        refresh = RefreshToken(refresh_token)
        return str(refresh.access_token)

    @staticmethod
    def get_claims(token):
        """
        Return decoded JWT claims.
        """
        validated = AccessToken(token)
        return dict(validated)

    @staticmethod
    def is_valid(token):
        """
        Returns True if token is valid.
        """
        try:
            AccessToken(token)
            return True

        except TokenError:
            return False