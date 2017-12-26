import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from invoices.utils import HourEntryUpdate


class Command(BaseCommand):
    help = 'Import data from 10k feet API'

    def handle(self, *args, **options):
        now = timezone.now()
        start_date = (now - datetime.timedelta(days=45))
        end_date = now
        hour_entry_update = HourEntryUpdate(start_date, end_date)
        hour_entry_update.update()
