from django.core.management.base import BaseCommand

from invoices.utils import sync_10000ft_users


class Command(BaseCommand):
    help = 'Refresh user data from 10000ft'

    def handle(self, *args, **options):
        sync_10000ft_users()
        self.stdout.write(self.style.SUCCESS("Successfully synced 10000ft users"))
