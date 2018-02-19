from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from invoices.slack import queue_slack_notification


class Command(BaseCommand):
    help = "Queue slack notifications"

    NOTIFICATION_SCHEDULE = {
        "unsubmitted": 1,  # Monday
        "unapproved": 2,  # Tuesday
    }

    def add_arguments(self, parser):
        parser.add_argument('notification_type', nargs=1, type=str, help="Notification type to be sent")
        parser.add_argument(
            "--force",
            action="store_true",
            dest="force",
            help="Force queuing instead of checking weekday",
        )

    def handle(self, *args, **options):
        if not options["notification_type"]:
            raise CommandError("Notification type not provided.")

        notification_type = options["notification_type"][0]
        if notification_type not in self.NOTIFICATION_SCHEDULE:
            raise CommandError(f"Invalid notification type: {notification_type}")

        if options.get("force") or timezone.now().isoweekday() == self.NOTIFICATION_SCHEDULE[notification_type]:
            queue_slack_notification(notification_type)
            self.stdout.write(self.style.SUCCESS(f"Queued {notification_type} notifications."))
        else:
            self.stdout.write(self.style.WARNING(f"No force option specified, and it is not correct weekday - notifications not queued."))
