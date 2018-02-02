import datetime
from collections import defaultdict

from django.conf import settings
from django.core.management.base import BaseCommand

from flex_hours.utils import refresh_public_holidays


class Command(BaseCommand):
    help = "Refresh public holidays list from 10000ft"

    def handle(self, *args, **options):
        refresh_public_holidays()
