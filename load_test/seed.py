"""
load_test/seed.py

Seed script to create test users and accounts with generous balances
BEFORE running the Locust load test.

Usage:
    docker-compose exec web python load_test/seed.py

This creates:
  - 1 load-test user: loadtest_user / loadtest_pass
  - 2 accounts with 10 000 000 cents ($100 000) each
  - Prints the account UUIDs for use in Locust

The script uses Django ORM directly (not HTTP), so it bypasses rate limiting.
"""

import os
import sys
import django

# Make sure Django is set up before importing models
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "payledger.settings")
django.setup()

from django.contrib.auth.models import User
from accounts.models import Account

USERNAME_A = "loadtest_a"
USERNAME_B = "loadtest_b"
PASSWORD   = "LoadTest_Password_123!"


def seed():
    user_a, _ = User.objects.get_or_create(username=USERNAME_A)
    user_a.set_password(PASSWORD)
    user_a.save()

    user_b, _ = User.objects.get_or_create(username=USERNAME_B)
    user_b.set_password(PASSWORD)
    user_b.save()

    account_a, _ = Account.objects.get_or_create(
        owner=user_a,
        name="Load Source Account",
        defaults={"currency": "USD", "balance": 100_000_000},  # $1 000 000
    )
    # Ensure large balance even if the account existed
    account_a.balance = 100_000_000
    account_a.save(update_fields=["balance"])

    account_b, _ = Account.objects.get_or_create(
        owner=user_b,
        name="Load Destination Account",
        defaults={"currency": "USD", "balance": 0},
    )

    print("=" * 60)
    print("Load-test seed complete.")
    print(f"  User A:     {USERNAME_A} / {PASSWORD}")
    print(f"  User B:     {USERNAME_B} / {PASSWORD}")
    print(f"  Account A:  {account_a.id}  (balance: {account_a.balance} cents)")
    print(f"  Account B:  {account_b.id}")
    print("=" * 60)


if __name__ == "__main__":
    seed()
