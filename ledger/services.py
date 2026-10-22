"""
ledger/services.py

The transfer service is the heart of PayLedger.  All business logic lives
here, not in views or serializers, so it can be called from tests, management
commands, or Celery tasks without going through HTTP.

─── Transaction + Locking Strategy ───────────────────────────────────────────
Problem: two concurrent requests could both read the same balance (say $100),
both decide the balance is sufficient, and both deduct $80 — resulting in a
$-60 balance (a double-spend).

Solution — select_for_update():
  We wrap everything in a single database transaction and acquire a row-level
  exclusive lock on both accounts with SELECT ... FOR UPDATE.  Any other
  transaction that tries to lock the same rows will block until we commit or
  roll back.  This serialises concurrent transfers on the same account.

  We always lock accounts in a DETERMINISTIC order (sorted by UUID) to prevent
  deadlocks.  If T1 locks A then B, and T2 locks B then A, they deadlock.
  If both always lock in the same order, only one can proceed.

─── Overdraft Prevention ──────────────────────────────────────────────────────
After acquiring the lock we re-read the balance.  If balance < amount we
raise InsufficientFunds and roll back.  Because we hold the lock, no other
transaction can have sneaked in between our read and our write.
"""

import hashlib
import json
import logging

from django.core.cache import cache
from django.db import transaction
from django.conf import settings
from rest_framework import status

from accounts.models import Account
from .models import IdempotencyRecord, LedgerEntry, Transfer

logger = logging.getLogger(__name__)


# ─── Custom exceptions ────────────────────────────────────────────────────────

class InsufficientFunds(Exception):
    """Raised when source account balance < transfer amount."""


class CurrencyMismatch(Exception):
    """Raised when source and destination accounts use different currencies."""


class IdempotencyConflict(Exception):
    """Raised when the same key is replayed with a different request body."""


# ─── Idempotency helpers ──────────────────────────────────────────────────────

def _redis_key(idempotency_key: str) -> str:
    """Prefix the key to avoid clashes with other Redis users."""
    return f"idem:{idempotency_key}"


def _hash_body(body: dict) -> str:
    """SHA-256 hash of the canonical JSON representation of the request body."""
    canonical = json.dumps(body, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def get_cached_response(idempotency_key: str, request_body: dict):
    """
    Check Redis (fast) then DB (durable) for a previously stored response.

    Returns (status_code, response_body_dict) if found, else None.
    Raises IdempotencyConflict if the key exists but with a different payload.
    """
    request_hash = _hash_body(request_body)
    redis_key = _redis_key(idempotency_key)

    # ── Redis check ──────────────────────────────────────────────────────────
    cached = cache.get(redis_key)
    if cached:
        if cached["request_hash"] != request_hash:
            raise IdempotencyConflict(
                "Idempotency-Key reused with a different request body."
            )
        return cached["response_status"], json.loads(cached["response_body"])

    # ── DB fallback ──────────────────────────────────────────────────────────
    try:
        record = IdempotencyRecord.objects.get(key=idempotency_key)
    except IdempotencyRecord.DoesNotExist:
        return None  # genuinely new request

    if record.request_hash != request_hash:
        raise IdempotencyConflict(
            "Idempotency-Key reused with a different request body."
        )

    # Warm the Redis cache so future replays are fast
    _store_in_redis(redis_key, record.request_hash, record.response_status, record.response_body)

    return record.response_status, json.loads(record.response_body)


def store_response(
    idempotency_key: str,
    request_body: dict,
    response_status: int,
    response_body: dict,
    transfer=None,
):
    """Persist the response in both Redis and the DB."""
    request_hash = _hash_body(request_body)
    body_str = json.dumps(response_body)
    redis_key = _redis_key(idempotency_key)

    _store_in_redis(redis_key, request_hash, response_status, body_str)

    IdempotencyRecord.objects.update_or_create(
        key=idempotency_key,
        defaults={
            "request_hash": request_hash,
            "response_status": response_status,
            "response_body": body_str,
            "transfer": transfer,
        },
    )


def _store_in_redis(redis_key: str, request_hash: str, response_status: int, response_body: str):
    cache.set(
        redis_key,
        {
            "request_hash": request_hash,
            "response_status": response_status,
            "response_body": response_body,
        },
        timeout=settings.IDEMPOTENCY_KEY_TTL,
    )


# ─── Core transfer logic ──────────────────────────────────────────────────────

def execute_transfer(
    source_account_id,
    destination_account_id,
    amount: int,
    description: str,
    idempotency_key: str,
    initiated_by,
) -> Transfer:
    """
    Create a Transfer and its two LedgerEntries inside a single atomic transaction.

    Steps:
      1. Open a DB transaction.
      2. Lock both accounts with SELECT FOR UPDATE (deterministic order).
      3. Validate: same currency, sufficient balance.
      4. Debit source, credit destination (update cached balance column).
      5. Create Transfer (COMPLETED) and two LedgerEntry rows.
      6. Commit — all or nothing.

    Returns the created Transfer object.
    Raises InsufficientFunds, CurrencyMismatch on validation failure.
    """

    with transaction.atomic():
        # Lock accounts in a fixed order to prevent deadlocks.
        # str(UUID) gives a consistent ordering across calls.
        account_ids_sorted = sorted(
            [str(source_account_id), str(destination_account_id)]
        )
        # select_for_update acquires row-level exclusive locks
        locked_accounts = {
            str(acc.id): acc
            for acc in Account.objects.select_for_update().filter(
                id__in=account_ids_sorted
            )
        }

        source = locked_accounts[str(source_account_id)]
        destination = locked_accounts[str(destination_account_id)]

        # ── Validation ────────────────────────────────────────────────────────
        if source.currency != destination.currency:
            raise CurrencyMismatch(
                f"Source currency {source.currency} != destination currency {destination.currency}"
            )

        if source.balance < amount:
            raise InsufficientFunds(
                f"Insufficient funds: balance={source.balance}, requested={amount}"
            )

        # ── Apply the transfer ────────────────────────────────────────────────
        # Update the cached balance columns (still inside the same transaction)
        source.balance -= amount
        source.save(update_fields=["balance", "updated_at"])

        destination.balance += amount
        destination.save(update_fields=["balance", "updated_at"])

        # ── Create the Transfer record ────────────────────────────────────────
        transfer = Transfer.objects.create(
            initiated_by=initiated_by,
            source_account=source,
            destination_account=destination,
            amount=amount,
            currency=source.currency,
            status=Transfer.Status.COMPLETED,
            description=description,
            idempotency_key=idempotency_key,
        )

        # ── Create the two LedgerEntry rows ───────────────────────────────────
        # Debit: negative amount leaves the source account
        LedgerEntry.objects.create(
            account=source,
            transfer=transfer,
            entry_type=LedgerEntry.EntryType.DEBIT,
            amount=-amount,  # negative
        )
        # Credit: positive amount enters the destination account
        LedgerEntry.objects.create(
            account=destination,
            transfer=transfer,
            entry_type=LedgerEntry.EntryType.CREDIT,
            amount=amount,  # positive
        )

        logger.info(
            "Transfer %s completed: %d %s from %s to %s",
            transfer.id,
            amount,
            source.currency,
            source.id,
            destination.id,
        )

    return transfer
