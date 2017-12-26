from django.core.management.base import BaseCommand

from invoices.utils import update_users


class Command(BaseCommand):
    help = 'Refresh user data from 10000ft'

    def handle(self, *args, **options):
        update_users()
