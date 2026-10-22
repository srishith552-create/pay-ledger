"""accounts/admin.py — register models with the Django admin site."""

from django.contrib import admin
from .models import Account


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ["id", "owner", "name", "currency", "balance", "created_at"]
    list_filter = ["currency"]
    search_fields = ["owner__username", "name"]
    readonly_fields = ["id", "balance", "created_at", "updated_at"]
