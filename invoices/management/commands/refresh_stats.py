import csv
from django.core.management.base import BaseCommand, CommandError
from invoices.models import HourEntry, Invoice, calculate_entry_stats
import datetime
import django.db.utils
from django.utils import timezone
import sys
from invoices.utils import refresh_stats

class Command(BaseCommand):
    help = 'Refresh statistics for each invoice'

    def handle(self, *args, **options):
        refresh_stats(None, None)
