"""ledger/admin.py"""

from django.contrib import admin
from .models import Transfer, LedgerEntry, IdempotencyRecord


@admin.register(Transfer)
class TransferAdmin(admin.ModelAdmin):
    list_display  = ["id", "initiated_by", "source_account", "destination_account", "amount", "currency", "status", "created_at"]
    list_filter   = ["status", "currency"]
    search_fields = ["id", "idempotency_key"]
    readonly_fields = ["id", "idempotency_key", "created_at", "updated_at"]


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display  = ["id", "account", "transfer", "entry_type", "amount", "created_at"]
    list_filter   = ["entry_type"]
    readonly_fields = ["id", "created_at"]


@admin.register(IdempotencyRecord)
class IdempotencyRecordAdmin(admin.ModelAdmin):
    list_display  = ["key", "response_status", "transfer", "created_at"]
    readonly_fields = ["key", "request_hash", "response_status", "response_body", "transfer", "created_at"]
