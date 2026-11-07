import os

SECRET_KEY = os.environ.get("WALLET_SECRET_KEY", "local-fictional-wallet-only")
DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "rest_framework.authtoken",
    "wallet_service.wallet",
]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("WALLET_DB_NAME", "ledgerlens"),
        "USER": os.environ.get("WALLET_DB_USER", "ledgerlens"),
        "PASSWORD": os.environ.get("WALLET_DB_PASSWORD", "ledgerlens-local"),
        "HOST": os.environ.get("WALLET_DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("WALLET_DB_PORT", "55432"),
        "OPTIONS": {"options": "-c lock_timeout=10000 -c statement_timeout=20000"},
    }
}
ROOT_URLCONF = "wallet_service.urls"
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware"]
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.TokenAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}
