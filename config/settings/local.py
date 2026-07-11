"""Configurações do ambiente local de desenvolvimento."""

from .base import *  # noqa: F403

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# E-mails aparecem no console durante o desenvolvimento
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Logs mais detalhados no desenvolvimento
LOGGING["loggers"]["fabriq"]["level"] = "DEBUG"  # noqa: F405
