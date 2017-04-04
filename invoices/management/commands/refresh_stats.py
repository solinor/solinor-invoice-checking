import csv
from django.core.management.base import BaseCommand, CommandError
from invoices.models import HourEntry, Invoice, calculate_entry_stats
import datetime
import django.db.utils
from django.utils import timezone
import sys

class Command(BaseCommand):
    help = 'Refresh statistics for each invoice'

    STATS_FIELDS = [
        "billable_incorrect_price_count",
        "non_billable_hours_count",
        "non_phase_specific_count",
        "not_approved_hours_count",
        "empty_descriptions_count",
        "total_hours",
        "bill_rate_avg",
        "total_money"]

    def handle(self, *args, **options):
        for invoice in Invoice.objects.all():
            entries = HourEntry.objects.filter(project=invoice.project, client=invoice.client, date__year__gte=invoice.year, date__month=invoice.month).filter(incurred_hours__gt=0)
            stats = calculate_entry_stats(entries)
            for field in self.STATS_FIELDS:
                setattr(invoice, field, stats[field])
            total_issues = invoice.total_issues()
            if total_issues != "?":
                invoice.incorrect_entries_count = total_issues
            else:
                invoice.incorrect_entries_count = None
            invoice.save()
