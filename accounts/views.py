"""
accounts/views.py

ViewSets map HTTP methods to actions automatically.
ModelViewSet gives us list/create/retrieve/update/destroy for free.
"""

from django.contrib.auth.models import User
from rest_framework import viewsets, generics, permissions
from .models import Account
from .serializers import AccountSerializer, UserRegistrationSerializer


class UserRegistrationView(generics.CreateAPIView):
    """
    POST /api/auth/register/

    Public endpoint — no authentication required.
    Creates a new user account.
    """

    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]


class AccountViewSet(viewsets.ModelViewSet):
    """
    GET    /api/accounts/        — list user's accounts
    POST   /api/accounts/        — create a new account
    GET    /api/accounts/{id}/   — retrieve a single account
    PATCH  /api/accounts/{id}/   — update name/currency
    DELETE /api/accounts/{id}/   — delete account (only if balance is 0)
    """

    serializer_class = AccountSerializer
    # Throttling is inherited from the global DRF settings

    def get_queryset(self):
        # Users can only see their own accounts — critical security boundary
        return Account.objects.filter(owner=self.request.user)

    def perform_destroy(self, instance):
        if instance.balance != 0:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Cannot delete an account with a non-zero balance.")
        instance.delete()
