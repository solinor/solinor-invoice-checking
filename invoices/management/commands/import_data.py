import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from invoices.utils import update_data

class Command(BaseCommand):
    help = 'Import data from 10k feet API'

    def handle(self, *args, **options):
        now = timezone.now()
        start_date = (now - datetime.timedelta(days=45)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")
        update_data(start_date, end_date)
