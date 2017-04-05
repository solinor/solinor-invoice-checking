from django.core.management.base import BaseCommand, CommandError
import redis
import os

REDIS = redis.from_url(os.environ.get("REDIS_URL"))

class Command(BaseCommand):
    help = 'Queue new data refresh'

    def handle(self, *args, **options):
        REDIS.publish("request-refresh", "True")
