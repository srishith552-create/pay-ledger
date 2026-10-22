"""accounts/urls.py"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AccountViewSet, UserRegistrationView

router = DefaultRouter()
router.register(r"accounts", AccountViewSet, basename="account")

urlpatterns = [
    path("auth/register/", UserRegistrationView.as_view(), name="user_register"),
    path("", include(router.urls)),
]
