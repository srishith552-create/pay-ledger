"""ledger/urls.py"""

from django.urls import path
from .views import (
    TransferView,
    TransferListView,
    TransferDetailView,
    LedgerEntryListView,
)

urlpatterns = [
    # POST to create a transfer; GET to list all transfers for the user
    path("transfers/", TransferView.as_view(), name="transfer_create"),
    path("transfers/list/", TransferListView.as_view(), name="transfer_list"),
    path("transfers/<uuid:pk>/", TransferDetailView.as_view(), name="transfer_detail"),

    # Ledger (accounting) entries — read-only
    path("ledger-entries/", LedgerEntryListView.as_view(), name="ledger_entry_list"),
]
