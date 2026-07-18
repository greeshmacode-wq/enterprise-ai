import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication.token_service import TokenService
from apps.accounts.serializers import LoginSerializer

logger = logging.getLogger(__name__)


class LoginAPIView(APIView):
    """
    JWT Login API

    Accepts username + password, returns JWT access and refresh tokens
    with custom claims (uuid, username, email, department, designation).
    """

    permission_classes = [AllowAny]

    def post(self, request):
        logger.info("API login request received")

        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        # Generate JWT tokens with custom claims via TokenService
        tokens = TokenService.generate_tokens(user)

        logger.info("API login successful for user: %s (uuid=%s)", user.username, user.uuid)

        return Response(
            {
                "success": True,
                "message": "Login successful.",
                "data": {
                    "access": tokens["access"],
                    "refresh": tokens["refresh"],
                    "user": {
                        "uuid": str(user.uuid),
                        "username": user.username,
                        "email": user.email,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                        "department": user.department,
                        "designation": user.designation,
                    },
                },
            },
            status=status.HTTP_200_OK,
        )


class LogoutAPIView(APIView):
    """
    JWT Logout API

    Blacklists the refresh token so it cannot be used again.
    """

    def post(self, request):
        logger.info("API logout request received for user: %s", request.user.username if request.user.is_authenticated else "anonymous")

        try:
            refresh_token = request.data.get("refresh")
            if refresh_token:
                from rest_framework_simplejwt.tokens import RefreshToken

                token = RefreshToken(refresh_token)
                token.blacklist()
                logger.info("Refresh token blacklisted successfully")
        except Exception as e:
            logger.warning("Error blacklisting refresh token: %s", str(e))

        return Response(
            {
                "success": True,
                "message": "Logout successful.",
            },
            status=status.HTTP_200_OK,
        )