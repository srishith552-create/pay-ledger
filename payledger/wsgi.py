"""
payledger/wsgi.py — WSGI entrypoint used by gunicorn in production.
"""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "payledger.settings")

application = get_wsgi_application()
