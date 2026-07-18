from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.serializers import LoginSerializer


class LoginAPIView(APIView):
    """
    JWT Login API
    """

    permission_classes = [AllowAny]
    
    def post(self,request):
        serializer = LoginSerializer(data=request.data, 
                      context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        return Response(
            {
                "success": True,
                "message": "Login successful.",

                "data": {
                    "access": access_token,
                    "refresh": refresh_token,

                    "user": {
                        "uuid": str(user.uuid),
                        "username": user.username,
                        "email": user.email,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                    }
                }
            },
            status=status.HTTP_200_OK,
        )