import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── Transfer ──────────────────────────────────────────────────────────
        migrations.CreateModel(
            name="Transfer",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("amount", models.PositiveBigIntegerField()),
                ("currency", models.CharField(max_length=3)),
                ("status", models.CharField(
                    choices=[("pending", "Pending"), ("completed", "Completed"), ("failed", "Failed")],
                    default="pending",
                    max_length=20,
                )),
                ("description", models.CharField(blank=True, max_length=255)),
                ("idempotency_key", models.CharField(max_length=255, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "initiated_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="initiated_transfers",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "source_account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="outgoing_transfers",
                        to="accounts.account",
                    ),
                ),
                (
                    "destination_account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="incoming_transfers",
                        to="accounts.account",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="transfer",
            index=models.Index(fields=["source_account", "created_at"], name="transfer_source_created_idx"),
        ),
        migrations.AddIndex(
            model_name="transfer",
            index=models.Index(fields=["destination_account", "created_at"], name="transfer_dest_created_idx"),
        ),
        migrations.AddIndex(
            model_name="transfer",
            index=models.Index(fields=["status"], name="transfer_status_idx"),
        ),
        migrations.AddIndex(
            model_name="transfer",
            index=models.Index(fields=["idempotency_key"], name="transfer_idem_key_idx"),
        ),

        # ── LedgerEntry ───────────────────────────────────────────────────────
        migrations.CreateModel(
            name="LedgerEntry",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("entry_type", models.CharField(
                    choices=[("debit", "Debit"), ("credit", "Credit")],
                    max_length=10,
                )),
                ("amount", models.BigIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ledger_entries",
                        to="accounts.account",
                    ),
                ),
                (
                    "transfer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ledger_entries",
                        to="ledger.transfer",
                    ),
                ),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.AddIndex(
            model_name="ledgerentry",
            index=models.Index(fields=["account", "created_at"], name="ledger_account_created_idx"),
        ),

        # ── IdempotencyRecord ─────────────────────────────────────────────────
        migrations.CreateModel(
            name="IdempotencyRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(db_index=True, max_length=255, unique=True)),
                ("request_hash", models.CharField(max_length=64)),
                ("response_status", models.PositiveSmallIntegerField()),
                ("response_body", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "transfer",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="idempotency_record",
                        to="ledger.transfer",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="idempotencyrecord",
            index=models.Index(fields=["key"], name="idempotency_key_idx"),
        ),
    ]
