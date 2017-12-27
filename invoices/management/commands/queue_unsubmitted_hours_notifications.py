import json

import redis
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Queue notifications for hours that were not submitted'

    def handle(self, *args, **options):
        redis_client = redis.from_url(settings.REDIS)
        redis_client.publish("request-refresh", json.dumps({"type": "slack-unsubmitted-notification"}))
