import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from invoices.models import DataUpdate, Event


class Command(BaseCommand):
    help = "Clean up old data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--remove-older-than",
            dest="remove_older",
            type=int,
            help="Remove entries older than X days",
        )
        parser.add_argument(
            "--type",
            dest="type",
            help="Type to be cleaned up",
        )

    def handle(self, *args, **options):
        remove_older = options.get("remove_older") or 90
        if 2 > remove_older > 1000:
            raise CommandError("--remove-older-than should be larger than 2 and smaller than 1000.")
        remove_entries_older_than = timezone.now() - datetime.timedelta(days=remove_older)
        cleanup_type = options.get("type") or "event"
        if cleanup_type == "event":
            delete_count, _ = Event.objects.filter(timestamp__lt=remove_entries_older_than).delete()
            self.stdout.write(self.style.SUCCESS(f"Cleaned up events older than {remove_older} days - count: {delete_count}"))
        elif cleanup_type == "dataupdate":
            delete_count, _ = DataUpdate.objects.filter(created_at__lt=remove_entries_older_than).delete()
            self.stdout.write(self.style.SUCCESS(f"Cleaned up dataupdates older than {remove_older} days - count: {delete_count}"))
        else:
            raise CommandError("Invalid type")
