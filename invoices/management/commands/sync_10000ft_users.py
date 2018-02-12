from django.core.management.base import BaseCommand

from invoices.utils import sync_10000ft_users


class Command(BaseCommand):
    help = 'Refresh user data from 10000ft'

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            dest="force",
            help="Force update, instead of skipping if update was recently executed",
        )

    def handle(self, *args, **options):
        sync_10000ft_users(force=options.get("force", False))
        self.stdout.write(self.style.SUCCESS("Successfully synced 10000ft users"))
