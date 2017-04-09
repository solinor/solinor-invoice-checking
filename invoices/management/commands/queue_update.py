import redis

from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Queue new data refresh'

    def handle(self, *args, **options):
        redis_instance = redis.from_url(settings.REDIS)
        redis_instance.publish("request-refresh", "True")
