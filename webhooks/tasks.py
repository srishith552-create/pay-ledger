"""
webhooks/tasks.py

Celery tasks for webhook delivery with exponential back-off + jitter.

─── Why Celery + RabbitMQ? ────────────────────────────────────────────────────
Making an HTTP request to an external server inside the Django request/response
cycle is dangerous:
  • The endpoint might be slow (seconds of latency block the web worker).
  • The endpoint might be down (we'd need to retry — impossible synchronously).
  • If the web process crashes mid-request, the delivery is silently lost.

Celery solves all three:
  • Work happens in a separate worker process — the web response is instant.
  • Celery has built-in retry with configurable back-off.
  • RabbitMQ persists messages — if the worker crashes, the message is
    re-delivered when the worker restarts (CELERY_TASK_ACKS_LATE = True).

─── Exponential back-off + jitter ─────────────────────────────────────────────
Retry delays: attempt 1 → ~10s, 2 → ~20s, 3 → ~40s, 4 → ~80s, 5 → fail.
Jitter (random ±20%) prevents the "thundering herd" problem where all
retrying workers hit the endpoint at the same instant.

─── Max retries ───────────────────────────────────────────────────────────────
After 5 failed attempts we mark the delivery as FAILED and stop.  We don't
retry forever because a permanently-down endpoint would clog the queue.
"""

import json
import logging
import random
import time

import httpx
from celery import shared_task
from django.conf import settings

from .models import WebhookDelivery, WebhookEndpoint
from .signing import sign_payload

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
BASE_DELAY_SECONDS = 10  # first retry delay; doubles each attempt


def _compute_backoff(attempt: int) -> float:
    """
    Exponential back-off with ±20% jitter.

    attempt=1 → ~10s, attempt=2 → ~20s, attempt=3 → ~40s, …
    """
    delay = BASE_DELAY_SECONDS * (2 ** (attempt - 1))
    jitter = delay * 0.2 * (random.random() * 2 - 1)  # ±20%
    return max(1.0, delay + jitter)


@shared_task(bind=True, max_retries=MAX_RETRIES, queue="default")
def deliver_webhook(self, transfer_id: str):
    """
    Attempt to deliver a webhook for the given transfer to all active endpoints
    registered by the transfer's accounts' owners.

    `bind=True` makes `self` the task instance, giving us access to
    `self.request.retries` (current attempt count) and `self.retry()`.
    """
    from ledger.models import Transfer  # avoid circular import at module level

    try:
        transfer = Transfer.objects.select_related(
            "source_account__owner",
            "destination_account__owner",
        ).get(id=transfer_id)
    except Transfer.DoesNotExist:
        logger.error("deliver_webhook: transfer %s not found", transfer_id)
        return

    # Collect all owners who should receive this event
    owner_ids = {
        transfer.source_account.owner_id,
        transfer.destination_account.owner_id,
    }

    endpoints = WebhookEndpoint.objects.filter(
        owner_id__in=owner_ids,
        is_active=True,
    )

    if not endpoints.exists():
        logger.debug("deliver_webhook: no active endpoints for transfer %s", transfer_id)
        return

    # Build the payload once (same for all endpoints)
    payload = {
        "event": "transfer.completed",
        "transfer": {
            "id": transfer_id,
            "source_account": str(transfer.source_account_id),
            "destination_account": str(transfer.destination_account_id),
            "amount": transfer.amount,
            "currency": transfer.currency,
            "status": transfer.status,
            "created_at": transfer.created_at.isoformat(),
        },
    }
    payload_bytes = json.dumps(payload, sort_keys=True).encode()

    attempt_number = self.request.retries + 1  # 1-indexed

    for endpoint in endpoints:
        _deliver_to_endpoint(
            self=self,
            endpoint=endpoint,
            payload=payload,
            payload_bytes=payload_bytes,
            transfer_id=transfer_id,
            attempt_number=attempt_number,
        )


def _deliver_to_endpoint(self, endpoint, payload, payload_bytes, transfer_id, attempt_number):
    """Make the HTTP POST and record the attempt."""
    secret = endpoint.secret or settings.WEBHOOK_SIGNING_SECRET
    signature = sign_payload(secret, payload_bytes)

    delivery = WebhookDelivery.objects.create(
        endpoint=endpoint,
        transfer_id=transfer_id,
        attempt_number=attempt_number,
        delivery_status=WebhookDelivery.DeliveryStatus.PENDING,
        payload=payload,
    )

    start = time.monotonic()
    try:
        response = httpx.post(
            endpoint.url,
            content=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-PayLedger-Signature": signature,
                "X-PayLedger-Event": "transfer.completed",
            },
            timeout=10.0,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        success = 200 <= response.status_code < 300
        delivery.http_status_code = response.status_code
        delivery.latency_ms = latency_ms
        delivery.delivery_status = (
            WebhookDelivery.DeliveryStatus.SUCCESS
            if success
            else WebhookDelivery.DeliveryStatus.FAILED
        )
        delivery.save(update_fields=["http_status_code", "latency_ms", "delivery_status"])

        if success:
            logger.info(
                "Webhook delivered to %s for transfer %s (attempt %d)",
                endpoint.url, transfer_id, attempt_number,
            )
            return  # done for this endpoint

        # Non-2xx — schedule a retry
        logger.warning(
            "Webhook to %s returned %d (attempt %d/%d)",
            endpoint.url, response.status_code, attempt_number, MAX_RETRIES,
        )

    except httpx.RequestError as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        delivery.latency_ms = latency_ms
        delivery.error_message = str(exc)
        delivery.delivery_status = WebhookDelivery.DeliveryStatus.FAILED
        delivery.save(update_fields=["latency_ms", "error_message", "delivery_status"])

        logger.warning(
            "Webhook request error to %s (attempt %d/%d): %s",
            endpoint.url, attempt_number, MAX_RETRIES, exc,
        )

    # Retry with exponential back-off if we have attempts left
    if attempt_number < MAX_RETRIES:
        delay = _compute_backoff(attempt_number)
        logger.info(
            "Retrying webhook for transfer %s in %.1fs (attempt %d → %d)",
            transfer_id, delay, attempt_number, attempt_number + 1,
        )
        raise self.retry(countdown=delay)
    else:
        logger.error(
            "Webhook delivery permanently failed for transfer %s to %s after %d attempts",
            transfer_id, endpoint.url, MAX_RETRIES,
        )
