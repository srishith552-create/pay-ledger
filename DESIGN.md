# PayLedger — Design Decisions

> Written as if explaining each decision in a backend / SDE interview.

---

## 1. Why Double-Entry Bookkeeping?

In a naive system you might just have one number — the balance — and subtract from it.
The problem is: if something goes wrong mid-way (a crash, a network error), you might
subtract from one account but not add to the other. Money disappears.

Double-entry bookkeeping solves this by recording every movement **twice**:
- A **debit** on the source account (money leaves)
- A **credit** on the destination account (money arrives)

Both rows are inserted inside a single database **transaction**. Either both happen or
neither does. This is the ACID guarantee — Atomicity.

There is also a powerful audit invariant:

> The sum of **every** LedgerEntry across **every** account must equal zero.

If this ever drifts from zero, you know a bug has corrupted your data. Banks have used
this principle for centuries. Software fintech systems like Stripe and Monzo use it too.

---

## 2. Why Store Amounts as Integer Minor Units?

Floating-point numbers (Python `float`, IEEE 754 double) are **binary fractions**.
Most decimal values cannot be represented exactly:

```python
>>> 0.1 + 0.2
0.30000000000000004
```

If you store $10.10 as the float `10.1` and do arithmetic on it, you accumulate tiny
rounding errors. At scale, these add up to real money discrepancies.

The solution: store amounts in the **smallest indivisible unit** of the currency.
For USD that's cents: $10.10 → `1010` (an integer). All arithmetic is exact.
We only divide by 100 **for display** — never for storage or computation.

---

## 3. Why Idempotency Keys?

In distributed systems, networks are unreliable. A client sends a POST request, the
server processes it successfully, but the response is lost. The client can't tell whether
the request succeeded or not — so it retries.

Without idempotency, that retry creates a **duplicate transfer**. Money is moved twice.

The solution: the client generates a unique `Idempotency-Key` (a UUID) and includes it
in every request. The server:
1. Checks if it has already processed this key.
2. If yes → return the **original** response, no side effects.
3. If no → process the request, then store `key → response`.

We also hash the request body and reject replays where the key matches but the body
differs (e.g. same key, different amount). This prevents a subtle injection attack.

**Storage strategy**: We store the key in **both Redis and PostgreSQL**:
- Redis is fast (sub-millisecond) — checked first on every request.
- PostgreSQL is durable — Redis can evict keys under memory pressure, so the DB is the
  source of truth. On a Redis miss we read from DB and re-warm the cache.

---

## 4. Why RabbitMQ + Celery Instead of Inline HTTP Calls?

**The problem with synchronous webhook delivery:**
- The receiving server might be slow (adds seconds of latency to the transfer API).
- The receiving server might be down (we'd need complex retry logic inside the request).
- If the web process crashes after committing the transfer but before sending the webhook,
  the notification is permanently lost.

**Celery + RabbitMQ solves all three:**
- The web process enqueues a task (`deliver_webhook.delay(transfer_id)`) in < 1ms,
  then returns the HTTP response immediately.
- The Celery worker picks up the task from the queue and makes the HTTP call in a
  separate process.
- RabbitMQ **persists messages** to disk. If the worker crashes, the message is
  re-delivered when the worker restarts (`CELERY_TASK_ACKS_LATE = True` — the worker
  only acknowledges a message after it has successfully processed it, not when it
  picks it up).

**Why RabbitMQ specifically, not Redis as broker?**
RabbitMQ is a proper message broker with AMQP semantics: persistent queues, delivery
acknowledgements, dead-letter queues. Redis Pub/Sub is fire-and-forget — messages are
lost if no consumer is listening. For reliable task delivery, RabbitMQ is the right tool.

---

## 5. Why Redis for Idempotency (not just the DB)?

A database row lookup for every POST /transfers/ request adds latency. With Redis, the
idempotency check is a single `GET` command — typically < 1ms — before we even open a
database connection. This keeps the fast path (replaying an already-seen key) extremely
cheap.

Redis also works as the Celery result backend for tracking task state.

---

## 6. How Do Retries and Exponential Back-off Work?

When a webhook delivery fails (non-2xx response or network error), we schedule a retry
using Celery's `self.retry(countdown=N)`. The delay between attempts grows exponentially:

```
attempt 1 → ~10 seconds
attempt 2 → ~20 seconds
attempt 3 → ~40 seconds
attempt 4 → ~80 seconds
attempt 5 → permanent failure
```

**Why exponential back-off?**
If a server is temporarily down, hammering it every second makes things worse. Backing
off gives it time to recover and reduces load on both sides.

**Why jitter?**
If all retrying workers use the exact same delay formula, they will all retry at the
same instant — a "thundering herd" that overwhelms the endpoint. Adding ±20% random
noise spreads the retries out in time.

**After 5 failures:**
We mark the delivery as `FAILED` and stop. Retrying forever would clog the queue.
The delivery log gives the user visibility into what went wrong.

---

## 7. Transaction and Locking Strategy

**Problem:** Two concurrent requests can both read the same balance, both decide
they have enough funds, and both debit — resulting in a negative balance (double-spend).

**Solution — `SELECT FOR UPDATE`:**

```python
with transaction.atomic():
    accounts = Account.objects.select_for_update().filter(id__in=[src_id, dst_id])
    # ... validate and update ...
```

`SELECT FOR UPDATE` acquires a **row-level exclusive lock** in PostgreSQL. Any other
transaction trying to lock the same rows will **block** until we commit or roll back.
This serialises concurrent transfers that touch the same accounts.

**Deadlock prevention:**
If T1 locks account A then B, and T2 locks account B then A, they deadlock.
We always lock accounts in **deterministic order** (sorted by UUID string). Both
transactions always try to acquire the same lock first, so only one can proceed —
no deadlock possible.

---

## 8. Known Limitations

| Limitation | Reason / Workaround |
|---|---|
| Single currency only | Cross-currency transfers require an FX rate service — out of scope for a portfolio project. |
| No webhook event filtering per endpoint | Currently all active endpoints for an account owner receive all `transfer.completed` events. Filtering by event type is designed (the `events` column exists) but not enforced in the query. |
| No rate-limit persistence | DRF's built-in throttle stores counts in the cache. If Redis restarts, limits reset. In production use a persistent throttle backend. |
| `balance` is a cached column | The cached balance can theoretically drift from the LedgerEntry sum if a bug bypasses the service layer. A periodic reconciliation job should verify: `SELECT SUM(amount) FROM ledger_entries GROUP BY account_id` matches `accounts.balance`. |
| No TLS in Docker Compose | The compose file binds to `0.0.0.0` without TLS. Put a reverse proxy (nginx/Caddy) in front for production. |
| Locust seed creates accounts without pre-funded balances | The Locust user creates accounts dynamically with zero balance. Most transfers will fail with 422 (insufficient funds), which is still a valid latency measurement. Use `load_test/seed.py` for funded accounts. |
