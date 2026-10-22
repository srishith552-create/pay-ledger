"""
payledger/celery.py — Celery application configuration.

Why Celery + RabbitMQ instead of inline HTTP calls?
  - Webhook delivery is I/O-bound and can fail.  Doing it synchronously would
    block the HTTP response for seconds or fail the transfer on a flaky endpoint.
  - Celery lets us retry failed tasks with exponential back-off without the
    web process knowing or caring.
  - RabbitMQ gives us a durable message queue: even if the worker crashes,
    messages survive and are re-delivered.
"""

import os
from celery import Celery

# Tell Celery which Django settings module to use
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "payledger.settings")

app = Celery("payledger")

# Read all CELERY_* keys from Django settings (namespace avoids clashes)
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks.py in every INSTALLED_APP
app.autodiscover_tasks()
