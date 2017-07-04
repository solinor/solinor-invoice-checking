from django.core.management.base import BaseCommand
from invoices.slack import refresh_slack_channels

class Command(BaseCommand):
    help = 'Refresh channels from Slack'

    def handle(self, *args, **options):
        refresh_slack_channels()
