"""
webhooks/models.py

WebhookEndpoint — a URL registered by a user to receive transfer notifications.
WebhookDelivery  — an audit log of every HTTP delivery attempt.

─── Why store every attempt? ──────────────────────────────────────────────────
Debugging webhook failures is painful without a log.  Storing the HTTP status
code, latency, and any error message for every attempt lets the user see
exactly what happened and why the webhook might be retrying.

─── Signature ─────────────────────────────────────────────────────────────────
We sign each payload with HMAC-SHA256 using a secret the user configures.
The receiving server verifies the signature before processing the payload.
This prevents attackers from spoofing webhook calls to the receiving server.
"""

import uuid
from django.db import models
from django.contrib.auth.models import User


class WebhookEndpoint(models.Model):
    """A URL that a user wants to receive webhook events on."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="webhook_endpoints",
    )

    url = models.URLField(max_length=500)

    # Events this endpoint subscribes to.  "transfer.completed" is the only
    # event for now; the field is kept flexible for future extension.
    events = models.JSONField(default=list)

    # User-provided secret used to verify the HMAC signature on the receiving end
    secret = models.CharField(max_length=255, default="")

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["owner", "is_active"], name="webhook_owner_active_idx"),
        ]

    def __str__(self) -> str:
        return f"WebhookEndpoint({self.url}) owner={self.owner_id}"


class WebhookDelivery(models.Model):
    """
    An immutable audit record of one HTTP delivery attempt.

    One WebhookEndpoint can accumulate many WebhookDelivery rows for the same
    transfer — one per retry attempt.
    """

    class DeliveryStatus(models.TextChoices):
        PENDING  = "pending",  "Pending"
        SUCCESS  = "success",  "Success"
        FAILED   = "failed",   "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    endpoint = models.ForeignKey(
        WebhookEndpoint,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )

    # The transfer that triggered this delivery
    transfer_id = models.UUIDField()

    # Which attempt number is this? (1 = first try, 2 = first retry, …)
    attempt_number = models.PositiveSmallIntegerField(default=1)

    delivery_status = models.CharField(
        max_length=20,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING,
    )

    # HTTP response code from the receiving server (null if the request failed entirely)
    http_status_code = models.PositiveSmallIntegerField(null=True, blank=True)

    # How long the HTTP request took, in milliseconds
    latency_ms = models.PositiveIntegerField(null=True, blank=True)

    # Error message if the delivery failed (e.g. connection refused, timeout)
    error_message = models.TextField(blank=True)

    # The exact JSON payload we sent
    payload = models.JSONField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["endpoint", "created_at"],
                name="delivery_endpoint_created_idx",
            ),
            models.Index(
                fields=["transfer_id"],
                name="delivery_transfer_idx",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return (
            f"Delivery(endpoint={self.endpoint_id}, transfer={self.transfer_id}, "
            f"attempt={self.attempt_number}, status={self.delivery_status})"
        )
