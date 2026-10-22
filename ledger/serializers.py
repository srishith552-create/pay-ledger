"""
ledger/serializers.py
"""

from rest_framework import serializers
from .models import Transfer, LedgerEntry


class LedgerEntrySerializer(serializers.ModelSerializer):
    amount_display = serializers.SerializerMethodField()

    class Meta:
        model = LedgerEntry
        fields = [
            "id",
            "account",
            "transfer",
            "entry_type",
            "amount",
            "amount_display",
            "created_at",
        ]
        read_only_fields = fields

    def get_amount_display(self, obj: LedgerEntry) -> str:
        return f"{obj.amount / 100:.2f}"


class TransferSerializer(serializers.ModelSerializer):
    """
    Used for both CREATE (POST) and READ (GET) responses.
    On write, `source_account` and `destination_account` accept UUIDs.
    On read, they are returned as UUIDs too (keep the API simple).
    """

    amount_display = serializers.SerializerMethodField()

    class Meta:
        model = Transfer
        fields = [
            "id",
            "source_account",
            "destination_account",
            "amount",
            "amount_display",
            "currency",
            "status",
            "description",
            "idempotency_key",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "amount_display",
            "currency",
            "status",
            "idempotency_key",
            "created_at",
            "updated_at",
        ]

    def get_amount_display(self, obj: Transfer) -> str:
        return f"{obj.amount / 100:.2f}"

    def validate_amount(self, value: int) -> int:
        if value <= 0:
            raise serializers.ValidationError("Amount must be a positive integer (minor units).")
        return value

    def validate(self, data: dict) -> dict:
        src = data.get("source_account")
        dst = data.get("destination_account")
        if src and dst and src == dst:
            raise serializers.ValidationError("Source and destination accounts must be different.")
        return data
