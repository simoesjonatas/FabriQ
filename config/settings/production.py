"""Configurações do ambiente de produção."""

from .base import *  # noqa: F403
from .base import BASE_DIR, LOGGING, MIDDLEWARE, env

DEBUG = False

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

# Em produção o PostgreSQL é obrigatório. Aceita DATABASE_URL ou as variáveis
# POSTGRES_* usadas pelo docker-compose.prod.yml.
DATABASE_URL = env("DATABASE_URL", default=None)
if DATABASE_URL:
    DATABASES = {
        "default": env.db("DATABASE_URL"),
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB"),
            "USER": env("POSTGRES_USER"),
            "PASSWORD": env("POSTGRES_PASSWORD"),
            "HOST": env("POSTGRES_HOST", default="db"),
            "PORT": env("POSTGRES_PORT", default="5432"),
            "CONN_MAX_AGE": env.int("POSTGRES_CONN_MAX_AGE", default=60),
        }
    }

CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# Arquivos estáticos em produção
MIDDLEWARE = [
    MIDDLEWARE[0],
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *MIDDLEWARE[1:],
]
STATIC_URL = "/static/"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
SERVE_MEDIA_FILES = env.bool("DJANGO_SERVE_MEDIA", default=True)

# Segurança
# HTTPS pode não estar disponível no início (ver cronograma), por isso
# o redirecionamento é controlado por variável de ambiente.
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=False)
SESSION_COOKIE_SECURE = env.bool("DJANGO_SESSION_COOKIE_SECURE", default=True)
CSRF_COOKIE_SECURE = env.bool("DJANGO_CSRF_COOKIE_SECURE", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
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
