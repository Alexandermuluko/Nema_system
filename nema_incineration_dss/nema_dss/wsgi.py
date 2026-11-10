"""WSGI config for the NEMA decision-support application."""

import os

from django.core.wsgi import get_wsgi_application  # type: ignore[import-untyped]

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nema_dss.settings")
application = get_wsgi_application()
