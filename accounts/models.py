"""
accounts/models.py

The Account model represents a financial account owned by a Django user.
Key design decisions:

1. Amounts are stored as INTEGER MINOR UNITS (pence, cents, paise) — never as
   floats.  Floats cannot represent many decimal values exactly, so 0.1 + 0.2
   != 0.3 in IEEE 754.  Using integers means all arithmetic is exact.

2. `balance` is a DERIVED value — it equals the sum of all LedgerEntry amounts
   on this account.  We store it here as a cached column for fast reads, but
   we always keep it in sync inside a database transaction (see ledger/services.py).
   This is the "materialized balance" pattern.

3. Currency is stored as a 3-char ISO 4217 code (USD, EUR, INR …).  We do NOT
   do cross-currency transfers (out of scope) so both accounts in a transfer
   must share the same currency.
"""

import uuid
from django.db import models
from django.contrib.auth.models import User


class Account(models.Model):
    """A financial account owned by a user."""

    # Use UUID as primary key to avoid sequential-ID enumeration attacks
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # The Django built-in User handles authentication
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="accounts",
    )

    # Human-readable name e.g. "Main Wallet", "Savings"
    name = models.CharField(max_length=120)

    # ISO 4217 currency code
    currency = models.CharField(max_length=3, default="USD")

    # Cached balance in minor units (e.g. 1000 = $10.00 USD)
    # Always kept in sync by the transfer service inside a transaction.
    balance = models.BigIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            # Most common query: "give me all accounts for user X"
            models.Index(fields=["owner", "created_at"], name="account_owner_created_idx"),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.currency}) — owner: {self.owner_id}"
