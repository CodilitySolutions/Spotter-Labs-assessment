"""Django settings. All environment-specific values come from env vars (see /.env.example)."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ALLOWED_ORIGINS=(list, ["http://localhost:5173"]),
    REDIS_URL=(str, ""),
    TOMTOM_API_KEY=(str, ""),
    NWS_USER_AGENT=(str, "truck-routing-dev (contact: dev@example.com)"),
    HTTP_TIMEOUT_S=(float, 8.0),
)

DEBUG = env("DEBUG")
SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-insecure-key" if DEBUG else environ.Env.NOTSET)
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# The API is stateless (no users, sessions or admin), so only the apps it needs are installed.
INSTALLED_APPS = [
    "corsheaders",
    "rest_framework",
    "routing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Plan responses are ~100 KB of JSON; gzip cuts them by roughly 4x.
    "django.middleware.gzip.GZipMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# No models are persisted; a database is configured only because Django expects one.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

if env("REDIS_URL"):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": env("REDIS_URL"),
            "KEY_PREFIX": "truck-routing",
        }
    }
else:
    # Without Redis. One heatmap alone stores ~300 weather cells, so the default limit of
    # 300 entries would evict plans mid-session.
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "OPTIONS": {"MAX_ENTRIES": 20_000},
        }
    }

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "EXCEPTION_HANDLER": "routing.api.exceptions.api_exception_handler",
    "COERCE_DECIMAL_TO_STRING": False,
}

CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# External services
TOMTOM_API_KEY = env("TOMTOM_API_KEY")
NWS_USER_AGENT = env("NWS_USER_AGENT")
HTTP_TIMEOUT_S = env("HTTP_TIMEOUT_S")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        # httpx logs full request URLs at INFO, and TomTom URLs carry the API key.
        "httpx": {"level": "WARNING"},
        "httpcore": {"level": "WARNING"},
    },
}
