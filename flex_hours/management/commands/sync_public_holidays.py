from django.core.management.base import BaseCommand

from flex_hours.utils import sync_public_holidays


class Command(BaseCommand):
    help = "Refresh public holidays list from 10000ft"

    def handle(self, *args, **options):
        sync_public_holidays()
