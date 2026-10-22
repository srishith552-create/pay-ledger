"""webhooks/serializers.py"""

from rest_framework import serializers
from .models import WebhookDelivery, WebhookEndpoint


class WebhookEndpointSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookEndpoint
        fields = [
            "id",
            "url",
            "events",
            "secret",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {
            # Never return the secret in list/detail responses for security
            "secret": {"write_only": True},
        }

    def create(self, validated_data):
        return WebhookEndpoint.objects.create(
            owner=self.context["request"].user,
            **validated_data,
        )


class WebhookDeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookDelivery
        fields = [
            "id",
            "endpoint",
            "transfer_id",
            "attempt_number",
            "delivery_status",
            "http_status_code",
            "latency_ms",
            "error_message",
            "payload",
            "created_at",
        ]
        read_only_fields = fields
