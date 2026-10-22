import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── WebhookEndpoint ───────────────────────────────────────────────────
        migrations.CreateModel(
            name="WebhookEndpoint",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("url", models.URLField(max_length=500)),
                ("events", models.JSONField(default=list)),
                ("secret", models.CharField(default="", max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="webhook_endpoints",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="webhookendpoint",
            index=models.Index(fields=["owner", "is_active"], name="webhook_owner_active_idx"),
        ),

        # ── WebhookDelivery ───────────────────────────────────────────────────
        migrations.CreateModel(
            name="WebhookDelivery",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("transfer_id", models.UUIDField()),
                ("attempt_number", models.PositiveSmallIntegerField(default=1)),
                ("delivery_status", models.CharField(
                    choices=[("pending", "Pending"), ("success", "Success"), ("failed", "Failed")],
                    default="pending",
                    max_length=20,
                )),
                ("http_status_code", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("latency_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True)),
                ("payload", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deliveries",
                        to="webhooks.webhookendpoint",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="webhookdelivery",
            index=models.Index(fields=["endpoint", "created_at"], name="delivery_endpoint_created_idx"),
        ),
        migrations.AddIndex(
            model_name="webhookdelivery",
            index=models.Index(fields=["transfer_id"], name="delivery_transfer_idx"),
        ),
    ]
