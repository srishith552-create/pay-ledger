"""
tests/test_transfers.py

Tests for the core transfer flow:
  - Successful transfer
  - Insufficient funds
  - Idempotent replay (same key, same body)
  - Idempotency conflict (same key, different body)
  - Concurrent transfers (no double-spend)

Each test is self-contained and documents WHAT it tests and WHY.
"""

import threading
import uuid

import pytest
from django.urls import reverse

from accounts.models import Account
from ledger.models import LedgerEntry, Transfer


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_transfer_payload(src, dst, amount=500, description="Test transfer"):
    return {
        "source_account": str(src.id),
        "destination_account": str(dst.id),
        "amount": amount,
        "description": description,
    }


def post_transfer(client, payload, idempotency_key=None):
    key = idempotency_key or str(uuid.uuid4())
    return client.post(
        "/api/transfers/",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    ), key


# ─── Successful transfer ───────────────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_successful_transfer(auth_client_a, account_a, account_b):
    """
    A transfer from A → B should:
      1. Return 201 Created.
      2. Deduct the amount from A's balance.
      3. Add the amount to B's balance.
      4. Create exactly 2 LedgerEntry rows (one debit, one credit).
      5. Create a Transfer record with status=COMPLETED.
    """
    payload = make_transfer_payload(account_a, account_b, amount=1000)
    response, _ = post_transfer(auth_client_a, payload)

    assert response.status_code == 201, response.data
    assert response.data["status"] == "completed"
    assert response.data["amount"] == 1000

    # Verify DB state
    account_a.refresh_from_db()
    account_b.refresh_from_db()
    assert account_a.balance == 9_000   # 10_000 - 1_000
    assert account_b.balance == 1_000

    transfer_id = response.data["id"]
    entries = LedgerEntry.objects.filter(transfer_id=transfer_id)
    assert entries.count() == 2

    debit  = entries.get(entry_type=LedgerEntry.EntryType.DEBIT)
    credit = entries.get(entry_type=LedgerEntry.EntryType.CREDIT)
    assert debit.amount  == -1000  # negative: money left
    assert credit.amount == +1000  # positive: money arrived

    # Double-entry invariant: sum of all entries must be zero
    total = sum(e.amount for e in entries)
    assert total == 0, f"Double-entry invariant violated: sum = {total}"


# ─── Insufficient funds ────────────────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_insufficient_funds(auth_client_a, account_a, account_b):
    """
    Attempting to transfer more than the account balance should:
      1. Return 422.
      2. Leave both balances unchanged.
      3. Create NO LedgerEntry rows.
    """
    payload = make_transfer_payload(account_a, account_b, amount=99_999)
    response, _ = post_transfer(auth_client_a, payload)

    assert response.status_code == 422
    assert "Insufficient funds" in response.data["error"]

    account_a.refresh_from_db()
    account_b.refresh_from_db()
    assert account_a.balance == 10_000  # unchanged
    assert account_b.balance == 0       # unchanged

    # No ledger entries should have been created
    assert LedgerEntry.objects.count() == 0


# ─── Idempotency: same key, same body → same response ─────────────────────────

@pytest.mark.django_db(transaction=True)
def test_idempotent_replay(auth_client_a, account_a, account_b):
    """
    Replaying the exact same transfer (same key, same body) must:
      1. Return the same status code and body as the original.
      2. NOT create a second transfer or additional ledger entries.
      3. NOT change balances a second time.
    """
    payload = make_transfer_payload(account_a, account_b, amount=500)
    idem_key = str(uuid.uuid4())

    # First request
    resp1, _ = post_transfer(auth_client_a, payload, idempotency_key=idem_key)
    assert resp1.status_code == 201

    # Replay — must be identical
    resp2, _ = post_transfer(auth_client_a, payload, idempotency_key=idem_key)
    assert resp2.status_code == 201
    assert resp2.data["id"] == resp1.data["id"]  # same transfer

    # Only ONE transfer should exist in the DB
    assert Transfer.objects.count() == 1
    assert LedgerEntry.objects.count() == 2  # only from the first request

    account_a.refresh_from_db()
    assert account_a.balance == 9_500  # deducted only once


# ─── Idempotency conflict: same key, different body → 422 ─────────────────────

@pytest.mark.django_db(transaction=True)
def test_idempotency_conflict(auth_client_a, account_a, account_b):
    """
    Replaying a key with a DIFFERENT amount must return 422.
    This prevents a subtle bug where an attacker replays a key to change the amount.
    """
    idem_key = str(uuid.uuid4())
    payload1 = make_transfer_payload(account_a, account_b, amount=500)
    payload2 = make_transfer_payload(account_a, account_b, amount=999)  # different amount

    resp1, _ = post_transfer(auth_client_a, payload1, idempotency_key=idem_key)
    assert resp1.status_code == 201

    resp2, _ = post_transfer(auth_client_a, payload2, idempotency_key=idem_key)
    assert resp2.status_code == 422
    assert "different request body" in resp2.data["error"]


# ─── Missing Idempotency-Key header ───────────────────────────────────────────

@pytest.mark.django_db
def test_missing_idempotency_key(auth_client_a, account_a, account_b):
    """Omitting the header must return 400."""
    payload = make_transfer_payload(account_a, account_b)
    response = auth_client_a.post("/api/transfers/", payload, format="json")
    assert response.status_code == 400
    assert "Idempotency-Key" in response.data["error"]


# ─── Concurrent transfers (no double-spend) ───────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_concurrent_transfers_no_double_spend(user_a, account_a, account_b):
    """
    Fire N concurrent transfers that each try to take 9 000 cents from an account
    with 10 000 cents.  Only ONE should succeed; the rest must fail with 422.

    This tests that select_for_update() prevents overdrafts under concurrency.
    """
    from django.test import RequestFactory
    from rest_framework.test import APIClient
    from django.contrib.auth.models import User

    n_concurrent = 5
    results = []
    lock = threading.Lock()

    def do_transfer():
        # Each thread needs its own client
        client = APIClient()
        resp = client.post(
            "/api/auth/token/",
            {"username": "alice", "password": "password123"},
            format="json",
        )
        token = resp.data["access"]
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        payload = {
            "source_account": str(account_a.id),
            "destination_account": str(account_b.id),
            "amount": 9_000,
            "description": "concurrent test",
        }
        response = client.post(
            "/api/transfers/",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),  # unique key per thread
        )
        with lock:
            results.append(response.status_code)

    threads = [threading.Thread(target=do_transfer) for _ in range(n_concurrent)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    successes = results.count(201)
    failures  = results.count(422)

    # Exactly one thread should have succeeded
    assert successes == 1, f"Expected 1 success, got {successes}. Results: {results}"
    assert failures == n_concurrent - 1

    # Final balance must be non-negative
    account_a.refresh_from_db()
    assert account_a.balance >= 0


# ─── Unauthorised access ───────────────────────────────────────────────────────

@pytest.mark.django_db
def test_cannot_transfer_from_other_users_account(auth_client_b, account_a, account_b):
    """
    user_b must NOT be able to initiate a transfer from user_a's account.
    """
    payload = {
        "source_account": str(account_a.id),  # owned by user_a
        "destination_account": str(account_b.id),
        "amount": 100,
        "description": "unauthorized",
    }
    response = auth_client_b.post(
        "/api/transfers/",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert response.status_code == 403
