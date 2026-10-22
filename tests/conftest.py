"""
tests/conftest.py — shared pytest fixtures.

Fixtures provide reusable objects (users, accounts, API clients) without
repeating setup code in every test.  pytest-django handles database rollback
between tests automatically when you use the `db` fixture.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounts.models import Account
from webhooks.models import WebhookEndpoint


@pytest.fixture
def api_client():
    """An unauthenticated DRF test client."""
    return APIClient()


@pytest.fixture
def user_a(db):
    """A Django user for test isolation."""
    return User.objects.create_user(username="alice", password="password123")


@pytest.fixture
def user_b(db):
    return User.objects.create_user(username="bob", password="password123")


@pytest.fixture
def auth_client_a(api_client, user_a):
    """APIClient authenticated as user_a via JWT."""
    response = api_client.post(
        "/api/auth/token/",
        {"username": "alice", "password": "password123"},
        format="json",
    )
    token = response.data["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return api_client


@pytest.fixture
def auth_client_b(user_b):
    client = APIClient()
    response = client.post(
        "/api/auth/token/",
        {"username": "bob", "password": "password123"},
        format="json",
    )
    token = response.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def account_a(db, user_a):
    """Account with 10 000 cents ($100.00) balance."""
    return Account.objects.create(
        owner=user_a,
        name="Alice Main",
        currency="USD",
        balance=10_000,
    )


@pytest.fixture
def account_b(db, user_b):
    """Account with 0 balance."""
    return Account.objects.create(
        owner=user_b,
        name="Bob Main",
        currency="USD",
        balance=0,
    )


@pytest.fixture
def webhook_endpoint(db, user_a):
    """A webhook endpoint registered by user_a."""
    return WebhookEndpoint.objects.create(
        owner=user_a,
        url="https://example.com/webhook",
        events=["transfer.completed"],
        secret="test-secret",
        is_active=True,
    )
