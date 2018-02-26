"""
WSGI config for gettingstarted project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.6/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application  # pylint: disable=wrong-import-position
from whitenoise.django import DjangoWhiteNoise  # pylint: disable=wrong-import-position

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "invoice_checking.settings")


# DO NOT PUT SENTRY CONFIGURATION HERE. It will not catch errors with `settings.handler500` if it is not configured as a middleware. Similarly, `manage.py` errors will not be catched with wsgi middleware.
application = get_wsgi_application()  # pylint: disable=invalid-name
application = DjangoWhiteNoise(application)  # pylint: disable=invalid-name
