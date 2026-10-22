"""
accounts/serializers.py

DRF serializers convert between Python objects and JSON.
We keep serializers thin — business logic lives in models and services.
"""

from django.contrib.auth.models import User
from rest_framework import serializers
from .models import Account


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Create a new Django user (username + password)."""

    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password"]

    def create(self, validated_data):
        # Use create_user so the password is hashed (never store plain text)
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"],
        )
        return user


class AccountSerializer(serializers.ModelSerializer):
    """Read/write serializer for Account.

    `balance_display` converts integer minor units to a human-readable decimal
    string so the API consumer doesn't need to know about minor units.
    Example: 1050 USD → "10.50"
    """

    balance_display = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = [
            "id",
            "name",
            "currency",
            "balance",         # raw minor units (useful for computations)
            "balance_display", # formatted string (useful for display)
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "balance", "balance_display", "created_at", "updated_at"]

    def get_balance_display(self, obj: Account) -> str:
        """Format minor units as a decimal string with 2 decimal places."""
        return f"{obj.balance / 100:.2f}"

    def create(self, validated_data):
        # Inject the current user as the owner
        request = self.context["request"]
        return Account.objects.create(owner=request.user, **validated_data)
