"""webhooks/admin.py"""

from django.contrib import admin
from .models import WebhookDelivery, WebhookEndpoint


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    list_display  = ["id", "owner", "url", "is_active", "created_at"]
    list_filter   = ["is_active"]
    search_fields = ["url", "owner__username"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display  = ["id", "endpoint", "transfer_id", "attempt_number", "delivery_status", "http_status_code", "latency_ms", "created_at"]
    list_filter   = ["delivery_status"]
    readonly_fields = ["id", "created_at"]
