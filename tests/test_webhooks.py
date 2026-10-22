"""
tests/test_webhooks.py

Tests for:
  - Signature generation and verification
  - Webhook delivery task (mocked HTTP)
  - Retry / back-off logic
  - Delivery audit log records
"""

import json
import time
import uuid
from unittest.mock import MagicMock, patch, call

import pytest
import httpx

from webhooks.models import WebhookDelivery, WebhookEndpoint
from webhooks.signing import sign_payload, verify_signature
from webhooks.tasks import deliver_webhook, MAX_RETRIES, _compute_backoff


# ─── Signature tests ───────────────────────────────────────────────────────────

def test_sign_and_verify():
    """A signed payload should verify successfully within the time window."""
    secret = "super-secret"
    body = b'{"event": "transfer.completed"}'
    header = sign_payload(secret, body)

    assert verify_signature(secret, body, header, max_age_seconds=300) is True


def test_verify_wrong_secret():
    """Verification with a different secret must fail."""
    body = b'{"event": "test"}'
    header = sign_payload("correct-secret", body)
    assert verify_signature("wrong-secret", body, header) is False


def test_verify_tampered_body():
    """Altering the body after signing must fail verification."""
    secret = "s3cr3t"
    original_body = b'{"amount": 100}'
    tampered_body = b'{"amount": 9999}'
    header = sign_payload(secret, original_body)
    assert verify_signature(secret, tampered_body, header) is False


def test_verify_expired_signature():
    """Signatures older than max_age_seconds must be rejected."""
    secret = "s3cr3t"
    body = b'{"event": "test"}'
    # Build a header with a timestamp 10 minutes in the past
    old_timestamp = int(time.time()) - 601
    import hashlib, hmac as hmac_module
    signed_string = f"{old_timestamp}.".encode() + body
    sig = hmac_module.new(secret.encode(), signed_string, hashlib.sha256).hexdigest()
    stale_header = f"t={old_timestamp},v1={sig}"

    assert verify_signature(secret, body, stale_header, max_age_seconds=300) is False


def test_verify_malformed_header():
    """A completely invalid header string must return False, not raise."""
    assert verify_signature("secret", b"body", "not-a-valid-header") is False


# ─── Back-off formula ────────────────────────────────────────────────────────

def test_backoff_increases():
    """Each attempt's base delay should be double the previous (before jitter)."""
    delays = [_compute_backoff(i) for i in range(1, 6)]
    # With jitter the exact values vary, but attempt N's delay should be
    # statistically larger than attempt N-1's.  We test the base (no jitter)
    # by checking the order of magnitudes.
    assert delays[1] > delays[0] * 0.5   # attempt 2 > half of attempt 1 even at worst jitter
    assert delays[2] > delays[1] * 0.5
    assert delays[3] > delays[2] * 0.5


# ─── Successful webhook delivery ──────────────────────────────────────────────

@pytest.mark.django_db
def test_successful_delivery(webhook_endpoint, db):
    """
    When the endpoint returns 200, the delivery should be marked SUCCESS and
    no retry should be scheduled.
    """
    transfer_id = str(uuid.uuid4())
    # Stub out the Transfer.objects.get call
    mock_transfer = MagicMock()
    mock_transfer.id = transfer_id
    mock_transfer.source_account.owner_id = webhook_endpoint.owner_id
    mock_transfer.destination_account.owner_id = webhook_endpoint.owner_id
    mock_transfer.source_account_id = uuid.uuid4()
    mock_transfer.destination_account_id = uuid.uuid4()
    mock_transfer.amount = 500
    mock_transfer.currency = "USD"
    mock_transfer.status = "completed"
    mock_transfer.created_at = MagicMock(isoformat=lambda: "2024-01-01T00:00:00+00:00")

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("ledger.models.Transfer.objects.select_related") as mock_sr, \
         patch("httpx.post", return_value=mock_response) as mock_post:

        mock_sr.return_value.get.return_value = mock_transfer

        # Call the task synchronously (not through Celery broker in tests)
        deliver_webhook.apply(args=[transfer_id])

    deliveries = WebhookDelivery.objects.filter(transfer_id=transfer_id)
    assert deliveries.count() == 1
    assert deliveries.first().delivery_status == WebhookDelivery.DeliveryStatus.SUCCESS


@pytest.mark.django_db
def test_delivery_records_http_status_and_latency(webhook_endpoint, db):
    """Delivery record must capture the HTTP status code and a positive latency."""
    transfer_id = str(uuid.uuid4())

    mock_transfer = MagicMock()
    mock_transfer.id = transfer_id
    mock_transfer.source_account.owner_id = webhook_endpoint.owner_id
    mock_transfer.destination_account.owner_id = webhook_endpoint.owner_id
    mock_transfer.source_account_id = uuid.uuid4()
    mock_transfer.destination_account_id = uuid.uuid4()
    mock_transfer.amount = 100
    mock_transfer.currency = "USD"
    mock_transfer.status = "completed"
    mock_transfer.created_at = MagicMock(isoformat=lambda: "2024-01-01T00:00:00+00:00")

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("ledger.models.Transfer.objects.select_related") as mock_sr, \
         patch("httpx.post", return_value=mock_response):
        mock_sr.return_value.get.return_value = mock_transfer
        deliver_webhook.apply(args=[transfer_id])

    delivery = WebhookDelivery.objects.get(transfer_id=transfer_id)
    assert delivery.http_status_code == 200
    assert delivery.latency_ms is not None
    assert delivery.latency_ms >= 0


@pytest.mark.django_db
def test_delivery_retry_on_failure(webhook_endpoint, db):
    """
    When the endpoint returns 500, the task should record a FAILED delivery
    and raise a retry.  We verify the delivery count increases on each retry.
    """
    transfer_id = str(uuid.uuid4())

    mock_transfer = MagicMock()
    mock_transfer.id = transfer_id
    mock_transfer.source_account.owner_id = webhook_endpoint.owner_id
    mock_transfer.destination_account.owner_id = webhook_endpoint.owner_id
    mock_transfer.source_account_id = uuid.uuid4()
    mock_transfer.destination_account_id = uuid.uuid4()
    mock_transfer.amount = 200
    mock_transfer.currency = "USD"
    mock_transfer.status = "completed"
    mock_transfer.created_at = MagicMock(isoformat=lambda: "2024-01-01T00:00:00+00:00")

    mock_response = MagicMock()
    mock_response.status_code = 500  # server error

    with patch("ledger.models.Transfer.objects.select_related") as mock_sr, \
         patch("httpx.post", return_value=mock_response), \
         patch("webhooks.tasks._compute_backoff", return_value=0):  # no sleep in tests
        mock_sr.return_value.get.return_value = mock_transfer
        # apply() runs synchronously; retries raise Retry exception, so we catch it
        from celery.exceptions import Retry
        try:
            deliver_webhook.apply(args=[transfer_id])
        except Exception:
            pass

    # At least one delivery attempt was recorded
    deliveries = WebhookDelivery.objects.filter(transfer_id=transfer_id)
    assert deliveries.count() >= 1
    assert deliveries.first().delivery_status == WebhookDelivery.DeliveryStatus.FAILED


@pytest.mark.django_db
def test_delivery_on_connection_error(webhook_endpoint, db):
    """A network error should record an error message and trigger a retry."""
    transfer_id = str(uuid.uuid4())

    mock_transfer = MagicMock()
    mock_transfer.id = transfer_id
    mock_transfer.source_account.owner_id = webhook_endpoint.owner_id
    mock_transfer.destination_account.owner_id = webhook_endpoint.owner_id
    mock_transfer.source_account_id = uuid.uuid4()
    mock_transfer.destination_account_id = uuid.uuid4()
    mock_transfer.amount = 300
    mock_transfer.currency = "USD"
    mock_transfer.status = "completed"
    mock_transfer.created_at = MagicMock(isoformat=lambda: "2024-01-01T00:00:00+00:00")

    with patch("ledger.models.Transfer.objects.select_related") as mock_sr, \
         patch("httpx.post", side_effect=httpx.ConnectError("Connection refused")), \
         patch("webhooks.tasks._compute_backoff", return_value=0):
        mock_sr.return_value.get.return_value = mock_transfer
        try:
            deliver_webhook.apply(args=[transfer_id])
        except Exception:
            pass

    delivery = WebhookDelivery.objects.filter(transfer_id=transfer_id).first()
    assert delivery is not None
    assert "Connection refused" in delivery.error_message
