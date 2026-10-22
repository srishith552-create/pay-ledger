"""
payledger/urls.py — root URL configuration.

Each app registers its own router; we just include them here.
"""

from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

urlpatterns = [
    # Django admin — useful for debugging during development
    path("admin/", admin.site.urls),

    # JWT auth endpoints
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    # App-level routers
    path("api/", include("accounts.urls")),
    path("api/", include("ledger.urls")),
    path("api/", include("webhooks.urls")),
]
