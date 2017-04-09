"""
WSGI config for gettingstarted project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.6/howto/deployment/wsgi/
"""

import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "invoice_checking.settings")

from django.core.wsgi import get_wsgi_application  # pylint: disable=wrong-import-position
from whitenoise.django import DjangoWhiteNoise  # pylint: disable=wrong-import-position

application = get_wsgi_application()  # pylint: disable=invalid-name
application = DjangoWhiteNoise(application)  # pylint: disable=redefined-variable-type,invalid-name
