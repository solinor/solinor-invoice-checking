import datetime

from django.core.management.base import BaseCommand
from invoices.slack import send_unapproved_hours_notifications


class Command(BaseCommand):
    help = 'Send notifications for team leads with unapproved hours'

    def handle(self, *args, **options):
        today = datetime.date.today()
        send_unapproved_hours_notifications(today.year, today.month)
