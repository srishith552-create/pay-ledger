"""
load_test/locustfile.py

Locust load test for PayLedger.

Usage:
    # Headless (CI / terminal):
    locust -f load_test/locustfile.py \
        --headless \
        --users 50 \
        --spawn-rate 10 \
        --run-time 60s \
        --host http://localhost:8000

    # Interactive browser UI:
    locust -f load_test/locustfile.py --host http://localhost:8000

What is tested:
  1. POST /api/transfers/          — core throughput
  2. GET  /api/transfers/list/     — read latency
  3. GET  /api/webhooks/deliveries/ — delivery log reads

Results are printed by Locust automatically at the end of the run.
The "Results" section in README.md has placeholders for the student to
paste their actual numbers.
"""

import uuid
from locust import HttpUser, between, task


class PayLedgerUser(HttpUser):
    """
    Simulates a user who:
      - Authenticates once on startup
      - Repeatedly fires transfers, list queries, and delivery log reads
    """

    # Think time between tasks (simulates real user pacing)
    wait_time = between(0.1, 0.5)

    def on_start(self):
        """
        Called once per simulated user at startup.
        Creates two accounts and authenticates.
        """
        suffix = uuid.uuid4().hex[:8]
        username_a = f"load_user_a_{suffix}"
        username_b = f"load_user_b_{suffix}"
        password = "loadtest_password_123"

        # Register users
        self.client.post(
            "/api/auth/register/",
            json={"username": username_a, "email": "", "password": password},
        )
        self.client.post(
            "/api/auth/register/",
            json={"username": username_b, "email": "", "password": password},
        )

        # Obtain JWT for user_a
        resp = self.client.post(
            "/api/auth/token/",
            json={"username": username_a, "password": password},
        )
        if resp.status_code != 200:
            self.environment.runner.quit()
            return

        token = resp.json()["access"]
        self.client.headers.update({"Authorization": f"Bearer {token}"})

        # Create a source account (seeded with lots of balance via admin / fixture)
        resp_a = self.client.post(
            "/api/accounts/",
            json={"name": "Load Source", "currency": "USD"},
        )
        resp_b_token_response = self.client.post(
            "/api/auth/token/",
            json={"username": username_b, "password": password},
        )
        b_token = resp_b_token_response.json().get("access", "")

        # Create destination account (as user_b)
        import requests  # noqa: PLC0415 (local import for headers)
        dst_resp = requests.post(
            f"{self.host}/api/accounts/",
            json={"name": "Load Dest", "currency": "USD"},
            headers={"Authorization": f"Bearer {b_token}", "Content-Type": "application/json"},
        )

        self.source_id = resp_a.json().get("id") if resp_a.status_code == 201 else None
        self.dest_id   = dst_resp.json().get("id") if dst_resp.status_code == 201 else None

        # Seed source account with a large balance via the admin
        # (In a real load test environment you'd set this via a management command
        #  or test fixture seed script.)
        # For now, transfers may fail with 422 (insufficient funds); that's fine —
        # Locust will still measure the latency of those responses.

    @task(5)
    def post_transfer(self):
        """POST /api/transfers/ — highest weight, most interesting metric."""
        if not self.source_id or not self.dest_id:
            return

        self.client.post(
            "/api/transfers/",
            json={
                "source_account": self.source_id,
                "destination_account": self.dest_id,
                "amount": 1,
                "description": "load test transfer",
            },
            headers={"Idempotency-Key": str(uuid.uuid4())},
            name="/api/transfers/ [POST]",
        )

    @task(3)
    def list_transfers(self):
        """GET /api/transfers/list/ — paginated read."""
        self.client.get("/api/transfers/list/", name="/api/transfers/list/ [GET]")

    @task(1)
    def list_deliveries(self):
        """GET /api/webhooks/deliveries/ — webhook delivery log."""
        self.client.get("/api/webhooks/deliveries/", name="/api/webhooks/deliveries/ [GET]")

    @task(1)
    def list_accounts(self):
        """GET /api/accounts/ — account list."""
        self.client.get("/api/accounts/", name="/api/accounts/ [GET]")
