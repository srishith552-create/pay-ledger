"""
ledger/filters.py — django-filter filter sets for Transfer and LedgerEntry.
"""

import django_filters
from .models import Transfer, LedgerEntry


class TransferFilter(django_filters.FilterSet):
    """
    Allow clients to filter transfers by:
      ?status=completed
      ?created_after=2024-01-01T00:00:00Z
      ?created_before=2024-12-31T23:59:59Z
      ?source_account=<uuid>
    """

    created_after  = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Transfer
        fields = ["status", "source_account", "destination_account", "currency"]


class LedgerEntryFilter(django_filters.FilterSet):
    created_after  = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = LedgerEntry
        fields = ["account", "entry_type", "transfer"]
