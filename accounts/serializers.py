from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):

    role_display = serializers.CharField(
        source="get_role_display",
        read_only=True
    )

    class Meta:
        model = User

        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "id_number",
            "role",
            "role_display",
            "department",
            "designation",
        ]

        read_only_fields = [
            "id",
            "role_display",
        ]