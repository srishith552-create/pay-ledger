"""
load_test/locustfile.py

Locust load test for PayLedger. Uses the accounts created by load_test/seed.py.

Setup (once):
    docker compose run --rm -e PYTHONPATH=/app web python load_test/seed.py

Run:
    locust -f load_test/locustfile.py --headless --users 50 --spawn-rate 10 \
        --run-time 60s --host http://localhost:8000

What is tested:
  1. POST /api/transfers/            - core throughput
  2. GET  /api/transfers/list/       - read latency
  3. GET  /api/webhooks/deliveries/  - delivery log reads
"""

import uuid

from locust import HttpUser, between, task

USERNAME_A = "loadtest_a"
USERNAME_B = "loadtest_b"
PASSWORD = "LoadTest_Password_123!"


class PayLedgerUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        """Log in as the seeded user and look up the two seeded accounts."""
        self.source_id = None
        self.dest_id = None

        resp = self.client.post(
            "/api/auth/token/",
            json={"username": USERNAME_A, "password": PASSWORD},
            name="/api/auth/token/",
        )
        if resp.status_code != 200:
            return

        token = resp.json()["access"]
        self.client.headers.update({"Authorization": f"Bearer {token}"})

        # The accounts list is paginated; read the first page.
        acc = self.client.get("/api/accounts/", name="/api/accounts/ [GET]")
        if acc.status_code != 200:
            return
        data = acc.json()
        accounts = data.get("results", data) if isinstance(data, dict) else data
        if len(accounts) >= 1:
            self.source_id = accounts[0]["id"]

        # The destination account belongs to loadtest_b. Its id is passed in
        # via the DEST_ACCOUNT_ID environment variable (see README), or we
        # fall back to a second account of user A if one exists.
        import os
        self.dest_id = os.environ.get("DEST_ACCOUNT_ID")
        if not self.dest_id and len(accounts) >= 2:
            self.dest_id = accounts[1]["id"]

    @task(5)
    def post_transfer(self):
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
        self.client.get("/api/transfers/list/", name="/api/transfers/list/ [GET]")

    @task(2)
    def list_deliveries(self):
        self.client.get(
            "/api/webhooks/deliveries/", name="/api/webhooks/deliveries/ [GET]"
        )