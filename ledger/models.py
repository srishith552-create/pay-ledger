"""
ledger/models.py

Three models implement the core domain:

1. Transfer     — the intent: "move X from account A to account B"
2. LedgerEntry  — the immutable bookkeeping record (one debit + one credit per transfer)
3. IdempotencyRecord — maps an Idempotency-Key to the stored API response

─── Why Double-Entry? ─────────────────────────────────────────────────────────
In double-entry bookkeeping every movement of money is recorded twice:
  • A DEBIT on the source account  (-amount)
  • A CREDIT on the destination    (+amount)

The sum of ALL ledger entries across ALL accounts must always equal zero.
This is a powerful invariant: if the sum ever drifts from zero you know
something is wrong.  It also makes auditing trivial.

─── Why Integer Minor Units? ──────────────────────────────────────────────────
Floats are binary fractions.  0.1 cannot be represented exactly, so
  0.1 + 0.2 == 0.30000000000000004   in Python (and every other IEEE 754 language)
Storing 10 cents as the integer 10 means all arithmetic is exact.
We only convert to decimal for display (÷ 100).
"""

import uuid
from django.db import models
from django.contrib.auth.models import User
from accounts.models import Account


class Transfer(models.Model):
    """
    Represents a requested movement of funds between two accounts.

    Status lifecycle:
        PENDING → COMPLETED  (happy path)
        PENDING → FAILED     (insufficient funds or any other error)
    """

    class Status(models.TextChoices):
        PENDING   = "pending",   "Pending"
        COMPLETED = "completed", "Completed"
        FAILED    = "failed",    "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # The user who initiated the transfer (for authorisation checks)
    initiated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="initiated_transfers",
    )

    source_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,   # never silently delete accounts with transfers
        related_name="outgoing_transfers",
    )
    destination_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="incoming_transfers",
    )

    # Amount in minor units (e.g. 500 = $5.00)
    amount = models.PositiveBigIntegerField()

    currency = models.CharField(max_length=3)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    # Optional human-readable description
    description = models.CharField(max_length=255, blank=True)

    # The idempotency key from the request header (stored for DB-level uniqueness)
    idempotency_key = models.CharField(max_length=255, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            # Paginated history: "give me transfers for account X, newest first"
            models.Index(
                fields=["source_account", "created_at"],
                name="transfer_source_created_idx",
            ),
            models.Index(
                fields=["destination_account", "created_at"],
                name="transfer_dest_created_idx",
            ),
            # Filter by status (e.g. "show me all failed transfers")
            models.Index(fields=["status"], name="transfer_status_idx"),
            # The idempotency key lookup must be fast
            models.Index(fields=["idempotency_key"], name="transfer_idem_key_idx"),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Transfer {self.id} | {self.amount} {self.currency} | {self.status}"


class LedgerEntry(models.Model):
    """
    An immutable accounting record.  Never update or delete these rows.

    For every transfer we insert exactly two rows:
      entry_type=DEBIT   on the source account      (negative: money leaves)
      entry_type=CREDIT  on the destination account (positive: money arrives)

    The balance of an account equals:
        SELECT SUM(amount) FROM ledger_entries WHERE account_id = X
    """

    class EntryType(models.TextChoices):
        DEBIT  = "debit",  "Debit"   # money leaves the account
        CREDIT = "credit", "Credit"  # money enters the account

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
    )
    transfer = models.ForeignKey(
        Transfer,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
    )

    entry_type = models.CharField(max_length=10, choices=EntryType.choices)

    # POSITIVE for credits, NEGATIVE for debits (signed integer)
    amount = models.BigIntegerField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            # Transaction history: "all entries for account X, chronological"
            models.Index(
                fields=["account", "created_at"],
                name="ledger_account_created_idx",
            ),
        ]
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.entry_type} {self.amount} on account {self.account_id}"


class IdempotencyRecord(models.Model):
    """
    Maps an Idempotency-Key to the serialized HTTP response we returned.

    Why store in the DB as well as Redis?
      Redis is an in-memory store; it can evict keys under memory pressure.
      The DB record is the durable source of truth.  We always check Redis first
      (fast) and fall back to the DB (slow but reliable).

    The `request_hash` is a hash of the request body.  If a client replays the
    same key with a DIFFERENT body we return 422 (Unprocessable Entity) instead
    of silently applying the second request.
    """

    # The key the client sends in the Idempotency-Key header
    key = models.CharField(max_length=255, unique=True, db_index=True)

    # SHA-256 of the request body — used to detect key reuse with different payload
    request_hash = models.CharField(max_length=64)

    # The HTTP status code we returned
    response_status = models.PositiveSmallIntegerField()

    # The JSON response body, stored as text
    response_body = models.TextField()

    # Which transfer was created (nullable: the transfer might have failed)
    transfer = models.OneToOneField(
        Transfer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="idempotency_record",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["key"], name="idempotency_key_idx"),
        ]

    def __str__(self) -> str:
        return f"IdempotencyRecord({self.key})"
