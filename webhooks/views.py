"""webhooks/views.py"""

from rest_framework import viewsets, generics
from .models import WebhookDelivery, WebhookEndpoint
from .serializers import WebhookDeliverySerializer, WebhookEndpointSerializer


class WebhookEndpointViewSet(viewsets.ModelViewSet):
    """
    CRUD for webhook endpoints.
    GET    /api/webhooks/endpoints/
    POST   /api/webhooks/endpoints/
    GET    /api/webhooks/endpoints/{id}/
    PATCH  /api/webhooks/endpoints/{id}/
    DELETE /api/webhooks/endpoints/{id}/
    """

    serializer_class = WebhookEndpointSerializer

    def get_queryset(self):
        return WebhookEndpoint.objects.filter(owner=self.request.user)


class WebhookDeliveryListView(generics.ListAPIView):
    """
    GET /api/webhooks/deliveries/
    Optional filter: ?endpoint=<uuid> or ?transfer_id=<uuid>
    """

    serializer_class = WebhookDeliverySerializer

    def get_queryset(self):
        user_endpoint_ids = WebhookEndpoint.objects.filter(
            owner=self.request.user
        ).values_list("id", flat=True)

        qs = WebhookDelivery.objects.filter(endpoint_id__in=user_endpoint_ids)

        # Optional query param filters
        endpoint_id = self.request.query_params.get("endpoint")
        transfer_id = self.request.query_params.get("transfer_id")
        if endpoint_id:
            qs = qs.filter(endpoint_id=endpoint_id)
        if transfer_id:
            qs = qs.filter(transfer_id=transfer_id)

        return qs
