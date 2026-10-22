"""
payledger/__init__.py

Import the Celery app here so it is initialised whenever Django starts.
This ensures tasks are discovered correctly by the worker.
"""

from .celery import app as celery_app  # noqa: F401

__all__ = ["celery_app"]
