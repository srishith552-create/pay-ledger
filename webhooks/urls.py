"""webhooks/urls.py"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import WebhookEndpointViewSet, WebhookDeliveryListView

router = DefaultRouter()
router.register(r"webhooks/endpoints", WebhookEndpointViewSet, basename="webhook_endpoint")

urlpatterns = [
    path("", include(router.urls)),
    path("webhooks/deliveries/", WebhookDeliveryListView.as_view(), name="webhook_delivery_list"),
]
