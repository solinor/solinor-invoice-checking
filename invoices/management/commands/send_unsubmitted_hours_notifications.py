import datetime

from django.core.management.base import BaseCommand

from invoices.slack import send_unsubmitted_hours_notifications


class Command(BaseCommand):
    help = 'Send notifications for hours that were not submitted'

    def handle(self, *args, **options):
        today = datetime.date.today()
        end_date = today - datetime.timedelta(today.isoweekday())
        start_date = end_date - datetime.timedelta(days=60)
        send_unsubmitted_hours_notifications(start_date, end_date)
        self.stdout.write(self.style.SUCCESS("Successfully sent unsubmitted hours notifications"))
