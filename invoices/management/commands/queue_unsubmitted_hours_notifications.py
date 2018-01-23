import json

import redis
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Queue notifications for hours that were not submitted'

    def add_arguments(self, parser):
        # Named (optional) arguments
        parser.add_argument(
            "--force",
            action="store_true",
            dest="force",
            help="Force queuing instead of checking weekday",
        )

    def handle(self, *args, **options):
        if options.get("force") or timezone.now().isoweekday() == 1:
            redis_client = redis.from_url(settings.REDIS)
            redis_client.publish("request-refresh", json.dumps({"type": "slack-unsubmitted-notification"}))
        else:
            self.stdout.write("No force option specified, and it is not Monday - notifications not queued.")
