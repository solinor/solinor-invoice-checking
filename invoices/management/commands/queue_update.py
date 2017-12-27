import datetime
import json

import redis
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Queue new data refresh'

    def handle(self, *args, **options):
        start_date = datetime.datetime.now() - datetime.timedelta(days=60)
        end_date = datetime.datetime.now()
        redis_instance = redis.from_url(settings.REDIS)
        redis_instance.publish("request-refresh", json.dumps({"type": "data-update", "start_date": start_date.strftime("%Y-%m-%d"), "end_date": end_date.strftime("%Y-%m-%d")}))
