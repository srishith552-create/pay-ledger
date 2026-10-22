"""
ledger/views.py

TransferView implements idempotency at the HTTP layer:
  1. Check Redis/DB for a cached response → return it immediately if found.
  2. If this is a new key, run the transfer service.
  3. Store the response so future replays return the same result.

The TransactionHistoryView gives a paginated, filterable log of transfers
and ledger entries for accounts the requesting user owns.
"""

import logging

from django.db import IntegrityError
from rest_framework import generics, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Account
from .filters import LedgerEntryFilter, TransferFilter
from .models import LedgerEntry, Transfer
from .serializers import LedgerEntrySerializer, TransferSerializer
from .services import (
    CurrencyMismatch,
    IdempotencyConflict,
    InsufficientFunds,
    execute_transfer,
    get_cached_response,
    store_response,
)

logger = logging.getLogger(__name__)


class TransferView(APIView):
    """
    POST /api/transfers/

    Required header: Idempotency-Key: <unique-string>

    Body:
        {
            "source_account": "<uuid>",
            "destination_account": "<uuid>",
            "amount": 1000,       ← minor units (1000 = $10.00)
            "description": "..."  ← optional
        }

    Idempotency contract:
        - Same key, same body → return original response (HTTP 200/201/400/…)
        - Same key, different body → 422
        - New key → process and store
    """

    def post(self, request):
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return Response(
                {"error": "Idempotency-Key header is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request_body = request.data

        # ── Check for a cached response ───────────────────────────────────────
        try:
            cached = get_cached_response(idempotency_key, request_body)
        except IdempotencyConflict as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        if cached is not None:
            cached_status, cached_body = cached
            return Response(cached_body, status=cached_status)

        # ── Validate the request body ─────────────────────────────────────────
        serializer = TransferSerializer(data=request_body)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        src_id = serializer.validated_data["source_account"].id
        dst_id = serializer.validated_data["destination_account"].id
        amount = serializer.validated_data["amount"]
        description = serializer.validated_data.get("description", "")

        # ── Security: caller must own the source account ───────────────────────
        if not Account.objects.filter(id=src_id, owner=request.user).exists():
            return Response(
                {"error": "You do not own the source account."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # ── Execute ───────────────────────────────────────────────────────────
        try:
            transfer = execute_transfer(
                source_account_id=src_id,
                destination_account_id=dst_id,
                amount=amount,
                description=description,
                idempotency_key=idempotency_key,
                initiated_by=request.user,
            )
        except InsufficientFunds as exc:
            response_body = {"error": str(exc)}
            response_status = status.HTTP_422_UNPROCESSABLE_ENTITY
            store_response(idempotency_key, request_body, response_status, response_body)
            return Response(response_body, status=response_status)
        except CurrencyMismatch as exc:
            response_body = {"error": str(exc)}
            response_status = status.HTTP_422_UNPROCESSABLE_ENTITY
            store_response(idempotency_key, request_body, response_status, response_body)
            return Response(response_body, status=response_status)
        except IntegrityError:
            # Race condition: another concurrent request with the same key already committed.
            # Look it up and return the stored response.
            cached = get_cached_response(idempotency_key, request_body)
            if cached:
                cached_status, cached_body = cached
                return Response(cached_body, status=cached_status)
            return Response(
                {"error": "Conflict: please retry."},
                status=status.HTTP_409_CONFLICT,
            )

        # ── Enqueue webhook delivery ───────────────────────────────────────────
        # Import here to avoid circular imports; task is defined in webhooks app
        from webhooks.tasks import deliver_webhook
        deliver_webhook.delay(str(transfer.id))

        # ── Store and return the response ─────────────────────────────────────
        response_data = TransferSerializer(transfer).data
        # Convert UUID/datetime objects to strings for JSON serialisability
        response_body = dict(response_data)
        store_response(
            idempotency_key, request_body, status.HTTP_201_CREATED, response_body, transfer
        )

        return Response(response_body, status=status.HTTP_201_CREATED)


class TransferListView(generics.ListAPIView):
    """
    GET /api/transfers/
    Paginated, filterable list of transfers involving the requesting user's accounts.
    """

    serializer_class = TransferSerializer
    filterset_class = TransferFilter
    ordering_fields = ["created_at", "amount"]
    ordering = ["-created_at"]

    def get_queryset(self):
        user_account_ids = Account.objects.filter(
            owner=self.request.user
        ).values_list("id", flat=True)
        return Transfer.objects.filter(
            source_account_id__in=user_account_ids
        ) | Transfer.objects.filter(
            destination_account_id__in=user_account_ids
        )


class TransferDetailView(generics.RetrieveAPIView):
    """GET /api/transfers/{id}/"""

    serializer_class = TransferSerializer

    def get_queryset(self):
        user_account_ids = Account.objects.filter(
            owner=self.request.user
        ).values_list("id", flat=True)
        return Transfer.objects.filter(
            source_account_id__in=user_account_ids
        ) | Transfer.objects.filter(
            destination_account_id__in=user_account_ids
        )


class LedgerEntryListView(generics.ListAPIView):
    """
    GET /api/ledger-entries/?account=<uuid>
    Paginated transaction history for an account.
    """

    serializer_class = LedgerEntrySerializer
    filterset_class = LedgerEntryFilter
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        # Only return entries for accounts the user owns
        user_account_ids = Account.objects.filter(
            owner=self.request.user
        ).values_list("id", flat=True)
        return LedgerEntry.objects.filter(account_id__in=user_account_ids)
