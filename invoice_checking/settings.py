"""
Django settings for gettingstarted project, on Heroku. For more info, see:
https://github.com/heroku/heroku-django-template

For more information on this file, see
https://docs.djangoproject.com/en/1.8/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.8/ref/settings/
"""

import os
import subprocess
import sys

import dj_database_url

os.environ["PATH"] += os.pathsep + os.path.dirname(sys.executable)
# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


########################################################
# Settings configured with environment variables
########################################################

# Required for working system.
# Everything is configured with os.environ.get instead of failing for missing values
# to make `manage.py` work properly in CI.
SECRET_KEY = os.environ.get("SECRET_KEY", "this-is-very-unsafe")
REDIS = os.environ.get("REDIS_URL")
TENKFEET_AUTH = os.environ.get("TENKFEET_AUTH")
SLACK_BOT_ACCESS_TOKEN = os.environ.get("SLACK_BOT_ACCESS_TOKEN")
SLACK_WORKSPACE_ACCESS_TOKEN = os.environ.get("SLACK_WORKSPACE_ACCESS_TOKEN")
SLACK_VERIFICATION_TOKEN = os.environ.get("SLACK_VERIFICATION_TOKEN")
# client ID from the Google Developer Console
GOOGLEAUTH_CLIENT_ID = os.environ.get("GOOGLEAUTH_CLIENT_ID")
# client secret from the Google Developer Console
GOOGLEAUTH_CLIENT_SECRET = os.environ.get("GOOGLEAUTH_CLIENT_SECRET")
# your app's domain, used to construct callback URLs
GOOGLEAUTH_CALLBACK_DOMAIN = os.environ.get("GOOGLEAUTH_CALLBACK_DOMAIN")
# callback URL uses HTTPS (your side, not Google), default True
GOOGLEAUTH_USE_HTTPS = os.environ.get("GOOGLEAUTH_USE_HTTPS", True) in (True, "True", "true")
# restrict to the given Google Apps domain, default None
GOOGLEAUTH_APPS_DOMAIN = os.environ.get("GOOGLEAUTH_APPS_DOMAIN")

AWS_SECRET_KEY = os.environ.get("AWS_SECRET_KEY")
AWS_ACCESS_KEY = os.environ.get("AWS_ACCESS_KEY")

# Optional settings:

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DEBUG", False) in ("true", "True", True)

TAG_MANAGER_CODE = os.environ.get("TAG_MANAGER_CODE")  # Google tag manager

SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", 0))  # https://docs.djangoproject.com/en/2.0/ref/settings/#std:setting-SECURE_HSTS_SECONDS
SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", True) in (True, "True", "true")  # https://docs.djangoproject.com/en/2.0/ref/settings/#secure-ssl-redirect
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # https://docs.djangoproject.com/en/2.0/ref/settings/#std:setting-SECURE_PROXY_SSL_HEADER
SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT  # https://docs.djangoproject.com/en/2.0/ref/settings/#std:setting-SESSION_COOKIE_SECURE
CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT  # https://docs.djangoproject.com/en/2.0/ref/settings/#csrf-cookie-secure

SLACK_NOTIFICATIONS_ADMIN = list(filter(len, os.environ.get("SLACK_NOTIFICATIONS_ADMIN", "").split(",")))
DOMAIN = os.environ.get("DOMAIN")
REDIRECT_OLD_DOMAIN = os.environ.get("REDIRECT_OLD_DOMAIN")
REDIRECT_NEW_DOMAIN = os.environ.get("REDIRECT_NEW_DOMAIN")
CSP_ENABLED = os.environ.get("CSP_ENABLED", True) in (True, "true", "True")

# Application definition

INSTALLED_APPS = (
    "django_extensions",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "googleauth",
    "django_tables2",
    "invoices",
    "flex_hours",
    "compressor",
    "reversion",
    "slack_hooks",
)

if DEBUG:
    INSTALLED_APPS += ("debug_toolbar",)

AUTHENTICATION_BACKENDS = (
    "googleauth.backends.GoogleAuthBackend",
)

GOOGLEAUTH_GET_PROFILE = True

# sets value of user.is_staff for new users, default False
GOOGLEAUTH_IS_STAFF = False

# list of default group names to assign to new users
GOOGLEAUTH_GROUPS = []

WKHTMLTOPDF_CMD = subprocess.Popen(
    ["which", os.environ.get("WKHTMLTOPDF_BINARY", "wkhtmltopdf")],  # Note we default to "wkhtmltopdf" as the binary name
    stdout=subprocess.PIPE).communicate()[0].strip()

CSP_DEFAULT_SRC = ("'none'",)
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'", "'unsafe-eval'", "https://www.gstatic.com", "https://www.google-analytics.com", "https://www.googletagmanager.com", "https://stats.g.doubleclick.net", "https://ajax.googleapis.com")  # thanks to google charts, unsafe-eval is required
CSP_OBJECT_SRC = ("'none'",)
CSP_MEDIA_SRC = ("'none'",)
CSP_FRAME_SRC = ("'none'",)
CSP_FONT_SRC = ("'self'", "https://fonts.gstatic.com")
CSP_CONNECT_SRC = ("'self'")
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'", "https://www.gstatic.com", "https://fonts.googleapis.com")  # unsafe-inline is required by google charts
CSP_IMG_SRC = ("'self'", "https://stats.g.doubleclick.net", "https://www.google-analytics.com", "https://solinor.fi")
CSP_REPORT_URI = os.environ.get("CSP_REPORT_URI")
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

MIDDLEWARE = (
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "invoice_checking.middleware.DomainRedirectMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.gzip.GZipMiddleware",
)

COMPRESS_STORAGE = 'compressor.storage.GzipCompressorFileStorage'
WHITENOISE_MAX_AGE = 60 * 60 * 24 * 30 if not DEBUG else 0

if CSP_ENABLED:
    MIDDLEWARE += ("csp.middleware.CSPMiddleware",)


if DEBUG:
    MIDDLEWARE += ("debug_toolbar.middleware.DebugToolbarMiddleware",)
    INTERNAL_IPS = ("127.0.0.1",)

ROOT_URLCONF = "invoice_checking.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "debug": True,
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "invoices.context_processors.add_tenkfuser",
            ],
        },
    },
]

WSGI_APPLICATION = "invoice_checking.wsgi.application"

# Database
# https://docs.djangoproject.com/en/1.9/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(BASE_DIR, "db.sqlite3"),
    }
}

# Password validation
# https://docs.djangoproject.com/en/1.9/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s %(message)s"
        },
        "simple": {
            "format": "%(levelname)s %(message)s"
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "verbose",
            "level": "DEBUG",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
        },
        "invoices": {
            "handlers": ["console"],
            "level": os.getenv("INVOICES_LOG_LEVEL", "INFO"),
            "propagate": True,
        }
    },
}

# Internationalization
# https://docs.djangoproject.com/en/1.8/topics/i18n/

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Helsinki"
USE_I18N = True
USE_L10N = False
USE_TZ = True

DATE_FORMAT = "Y-m-d"
SHORT_DATE_FORMAT = "Y-m-d"
DATETIME_FORMAT = "Y-m-d H:i"
SHORT_DATETIME_FORMAT = "Y-m-d H:i"

handler404 = "invoices.views.handler404"  # pylint:disable=invalid-name
handler500 = "invoices.views.handler500"  # pylint:disable=invalid-name

# Update database configuration with $DATABASE_URL.
DATABASES["default"].update(dj_database_url.config(conn_max_age=500))

# Honor the "X-Forwarded-Proto" header for request.is_secure()
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Allow all host headers
ALLOWED_HOSTS = ["*"]

COMPRESS_CSS_HASHING_METHOD = None

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.8/howto/static-files/

STATIC_ROOT = os.path.join(PROJECT_ROOT, "staticfiles")
STATIC_URL = "/static/"

STATICFILES_FINDERS = (
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
    "compressor.finders.CompressorFinder",
)

# Extra places for collectstatic to find static files.
STATICFILES_DIRS = (
    os.path.join(PROJECT_ROOT, "static"),
)

# Simplified static file serving.
# https://warehouse.python.org/project/whitenoise/
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
