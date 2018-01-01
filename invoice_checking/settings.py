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

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '%(levelname)s %(asctime)s %(module)s %(message)s'
        },
        'simple': {
            'format': '%(levelname)s %(message)s'
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'stream': sys.stdout,
            'formatter': 'verbose',
            'level': 'DEBUG',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
        },
        'invoices': {
            'handlers': ['console'],
            'level': os.getenv('INVOICES_LOG_LEVEL', 'INFO'),
            'propagate': True,
        }
    },
}

os.environ['PATH'] += os.pathsep + os.path.dirname(sys.executable)
WKHTMLTOPDF_CMD = subprocess.Popen(
    ['which', os.environ.get('WKHTMLTOPDF_BINARY', 'wkhtmltopdf')],  # Note we default to 'wkhtmltopdf' as the binary name
    stdout=subprocess.PIPE).communicate()[0].strip()

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.8/howto/deployment/checklist/

# SECURITY WARNING: change this before deploying to production!
SECRET_KEY = os.environ["SECRET_KEY"]
REDIS = os.environ["REDIS_URL"]
TENKFEET_AUTH = os.environ["TENKFEET_AUTH"]
SLACK_BOT_ACCESS_TOKEN = os.environ["SLACK_BOT_ACCESS_TOKEN"]

TAG_MANAGER_CODE = os.environ.get("TAG_MANAGER_CODE")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DEBUG", False) in ("true", "True", True)


# Application definition

INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'googleauth',
    'django_tables2',
    'invoices',
    'flex_hours',
)

if DEBUG:
    INSTALLED_APPS += ('debug_toolbar',)

AUTHENTICATION_BACKENDS = (
    'googleauth.backends.GoogleAuthBackend',
)

# client ID from the Google Developer Console
GOOGLEAUTH_CLIENT_ID = os.environ["GOOGLEAUTH_CLIENT_ID"]

# client secret from the Google Developer Console
GOOGLEAUTH_CLIENT_SECRET = os.environ["GOOGLEAUTH_CLIENT_SECRET"]

# your app's domain, used to construct callback URLs
GOOGLEAUTH_CALLBACK_DOMAIN = os.environ["GOOGLEAUTH_CALLBACK_DOMAIN"]

# callback URL uses HTTPS (your side, not Google), default True
GOOGLEAUTH_USE_HTTPS = os.environ.get("GOOGLEAUTH_USE_HTTPS", True) in (True, "True", "true")

# restrict to the given Google Apps domain, default None
GOOGLEAUTH_APPS_DOMAIN = os.environ["GOOGLEAUTH_APPS_DOMAIN"]

SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", 0))
# get user's name, default True (extra HTTP request)
GOOGLEAUTH_GET_PROFILE = True

# sets value of user.is_staff for new users, default False
GOOGLEAUTH_IS_STAFF = False

# list of default group names to assign to new users
GOOGLEAUTH_GROUPS = []

SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", True) in (True, "True", "true")
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SSLIFY_DISABLE = os.environ.get("SECURE_SSL_REDIRECT", False) not in (True, "True", "true")

AWS_SECRET_KEY = os.environ["AWS_SECRET_KEY"]
AWS_ACCESS_KEY = os.environ["AWS_ACCESS_KEY"]

SLACK_NOTIFICATIONS_ADMIN = list(filter(len, os.environ.get("SLACK_NOTIFICATIONS_ADMIN", u"").split(u",")))

REDIRECT_OLD_DOMAIN = os.environ.get("REDIRECT_OLD_DOMAIN")
REDIRECT_NEW_DOMAIN = os.environ.get("REDIRECT_NEW_DOMAIN")

CSP_DEFAULT_SRC = ("'none'",)
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'", "https://www.gstatic.com", "https://www.google-analytics.com", "https://www.googletagmanager.com", "https://stats.g.doubleclick.net", "https://ajax.googleapis.com")
CSP_OBJECT_SRC = ("'none'",)
CSP_MEDIA_SRC = ("'none'",)
CSP_FRAME_SRC = ("'none'",)
CSP_FONT_SRC = ("'self'", "https://fonts.gstatic.com")
CSP_CONNECT_SRC = ("'none'",)
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'", "https://www.gstatic.com", "https://fonts.googleapis.com")
CSP_IMG_SRC = ("'self'", "https://stats.g.doubleclick.net")
CSP_REPORT_URI = "https://solinor.report-uri.com/r/d/csp/reportOnly"
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True

MIDDLEWARE = (
    'invoice_checking.middleware.DomainRedirectMiddleware',
    'csp.middleware.CSPMiddleware',
    'sslify.middleware.SSLifyMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.security.SecurityMiddleware',
)

if DEBUG:
    MIDDLEWARE += ("debug_toolbar.middleware.DebugToolbarMiddleware",)
    INTERNAL_IPS = ("127.0.0.1",)

ROOT_URLCONF = 'invoice_checking.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'debug': True,
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'invoice_checking.wsgi.application'


# Database
# https://docs.djangoproject.com/en/1.9/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

# Password validation
# https://docs.djangoproject.com/en/1.9/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/1.8/topics/i18n/

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = False
USE_TZ = True

DATE_FORMAT = "Y-m-d"
SHORT_DATE_FORMAT = "Y-m-d"
DATETIME_FORMAT = "Y-m-d H:i"
SHORT_DATETIME_FORMAT = "Y-m-d H:i"

# Update database configuration with $DATABASE_URL.
DATABASES['default'].update(dj_database_url.config(conn_max_age=500))

# Honor the 'X-Forwarded-Proto' header for request.is_secure()
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Allow all host headers
ALLOWED_HOSTS = ['*']

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.8/howto/static-files/

STATIC_ROOT = os.path.join(PROJECT_ROOT, 'staticfiles')
STATIC_URL = '/static/'

# Extra places for collectstatic to find static files.
STATICFILES_DIRS = (
    os.path.join(PROJECT_ROOT, 'static'),
)

# Simplified static file serving.
# https://warehouse.python.org/project/whitenoise/
STATICFILES_STORAGE = 'whitenoise.django.GzipManifestStaticFilesStorage'
