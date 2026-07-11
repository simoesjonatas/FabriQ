"""Configurações do ambiente de produção."""

from .base import *  # noqa: F403
from .base import BASE_DIR, LOGGING, env

DEBUG = False

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

# Em produção o PostgreSQL é obrigatório: sem DATABASE_URL a aplicação não sobe
DATABASES = {
    "default": env.db("DATABASE_URL"),
}

CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# Segurança
# HTTPS pode não estar disponível no início (ver cronograma), por isso
# o redirecionamento é controlado por variável de ambiente.
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=False)
SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Sessão válida por 8 horas (uma jornada de trabalho)
SESSION_COOKIE_AGE = 60 * 60 * 8

# Logs em arquivo rotativo além do console
LOGGING["handlers"]["file"] = {
    "class": "logging.handlers.RotatingFileHandler",
    "filename": BASE_DIR / "logs" / "fabriq.log",
    "maxBytes": 10 * 1024 * 1024,  # 10 MB
    "backupCount": 10,
    "formatter": "verbose",
}
LOGGING["root"]["handlers"].append("file")
LOGGING["loggers"]["django"]["handlers"].append("file")
LOGGING["loggers"]["fabriq"]["handlers"].append("file")
