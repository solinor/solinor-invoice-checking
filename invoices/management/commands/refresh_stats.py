from django.core.management.base import BaseCommand

from invoices.utils import refresh_stats


class Command(BaseCommand):
    help = 'Refresh statistics for each invoice'

    def handle(self, *args, **options):
        refresh_stats(None, None)
