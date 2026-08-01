import logging

from django.contrib.auth import authenticate
from rest_framework import serializers

logger = logging.getLogger(__name__)


class LoginSerializer(serializers.Serializer):
    """
    Validate login credentials.
    """

    username = serializers.CharField(max_length=150,)
    password = serializers.CharField(write_only=True, style={"input_type": "password"},)

    def validate(self, attrs):
        username = attrs.get("username")
        password = attrs.get("password")
        request = self.context.get("request")

        logger.info("Login attempt for username=%s", username)

        user = authenticate(request=request, username=username, password=password,)

        if user is None:
            logger.warning("Login validation failed: invalid credentials for username=%s", username)
            raise serializers.ValidationError("Invalid username or password.")

        if not user.is_active:
            logger.warning("Login validation failed: inactive account for username=%s (uuid=%s)", username, user.uuid)
            raise serializers.ValidationError("User account is inactive.")

        logger.info("Login validation passed for user: %s (uuid=%s)", user.username, user.uuid)

        attrs["user"] = user #Later in the API View [serializer.validated_data["user"]] will give us <User: Greeshma>

        return attrs