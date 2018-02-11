import datetime

from django.core.management.base import BaseCommand

from invoices.slack import send_unapproved_hours_notifications


class Command(BaseCommand):
    help = 'Send notifications for team leads with unapproved hours'

    def handle(self, *args, **options):
        today = datetime.date.today()
        last_day = today - datetime.timedelta(today.isoweekday())
        first_day = last_day - datetime.timedelta(days=60)
        send_unapproved_hours_notifications(first_day, last_day)
        self.stdout.write(self.style.SUCCESS("Successfully sent unapproved hours notifications"))
