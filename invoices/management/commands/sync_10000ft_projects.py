from django.core.management.base import BaseCommand

from invoices.utils import sync_10000ft_projects


class Command(BaseCommand):
    help = 'Refresh project data from 10000ft'

    def handle(self, *args, **options):
        sync_10000ft_projects()
