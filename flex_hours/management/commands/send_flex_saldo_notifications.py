import datetime

from django.core.management.base import BaseCommand

from flex_hours.utils import send_flex_saldo_notifications


class Command(BaseCommand):
    help = "Send flex saldo notifications"

    def handle(self, *args, **options):
        today = datetime.date.today()
        send_flex_saldo_notifications(today.year, today.month)
        self.stdout.write(self.style.SUCCESS(f"Successfully sent flex saldo notifications."))
