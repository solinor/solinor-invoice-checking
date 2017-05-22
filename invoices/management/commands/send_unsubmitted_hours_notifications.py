from django.core.management.base import BaseCommand
from invoices.slack import send_unsubmitted_hours_notifications

import datetime

class Command(BaseCommand):
    help = 'Send notifications for hours that were not submitted'

    def handle(self, *args, **options):
        send_unsubmitted_hours_notifications()
