import datetime

from django.core.management.base import BaseCommand, CommandError

from invoices.slack import send_unapproved_hours_notifications, send_unsubmitted_hours_notifications


class Command(BaseCommand):
    help = 'Send notifications'

    def add_arguments(self, parser):
        parser.add_argument('notification_type', nargs=1, type=str, help="Notification type to be sent")

    def handle(self, *args, **options):
        if not options["notification_type"]:
            raise CommandError("Notification type not provided.")

        notification_type = options["notification_type"]
        today = datetime.date.today()
        end_date = today - datetime.timedelta(today.isoweekday())
        start_date = end_date - datetime.timedelta(days=60)

        if notification_type == "unapproved":
            send_unapproved_hours_notifications(start_date, end_date)
        elif notification_type == "unsubmitted":
            send_unsubmitted_hours_notifications(start_date, end_date)
        else:
            raise CommandError(f"Unknown notification type: {notification_type}")
        self.stdout.write(self.style.SUCCESS(f"Successfully sent {notification_type} hours notifications"))
