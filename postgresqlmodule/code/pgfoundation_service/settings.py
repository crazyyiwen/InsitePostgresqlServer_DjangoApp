"""Django settings — WEB LAYER ONLY (ADR-012).

No ORM and no ``DATABASES`` for the foundation; the foundation manages its own
PostgreSQL connections. Django is used purely as the async HTTP layer.
"""
from __future__ import annotations

import os

# SECURITY: override in production via env / secret manager.
SECRET_KEY = os.environ.get("PGF_SERVICE_SECRET_KEY", "dev-insecure-change-me")
DEBUG = os.environ.get("PGF_SERVICE_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = os.environ.get("PGF_SERVICE_ALLOWED_HOSTS", "*").split(",")

ROOT_URLCONF = "pgfoundation_service.urls"
INSTALLED_APPS: list[str] = []          # no apps: no admin, no ORM
MIDDLEWARE: list[str] = []              # auth is a pluggable seam (ADR-013), not Django middleware
DATABASES: dict = {}                    # foundation owns its own connections
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Path to the pgfoundation config file (doc 05). Set via env for real deploys.
PGF_CONFIG = os.environ.get("PGF_CONFIG")
