from django.contrib.auth import authenticate
from rest_framework import serializers


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

        user = authenticate(request=request,username=username,password=password,)

        if user is None:
            raise serializers.ValidationError("Invalid username or password.")

        if not user.is_active:
            raise serializers.ValidationError("User account is inactive." )

        attrs["user"] = user #Later in the API View [serializer.validated_data["user"]] will give us <User: Greeshma>

        return attrs