import datetime
import json

import redis
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Queue new data refresh"

    def add_arguments(self, parser):
        # Named (optional) arguments
        parser.add_argument(
            "--force",
            action="store_true",
            dest="force",
            help="Force update, instead of skipping if update was recently executed",
        )
        parser.add_argument(
            "--start-date",
            dest="start_date",
            help="Start date for the update",
        )
        parser.add_argument(
            "--end-date",
            dest="end_date",
            help="End date for the update",
        )

    def handle(self, *args, **options):
        date_format = "%Y-%m-%d"
        start_date = options.get("start_date")
        if not start_date:
            start_date = (datetime.datetime.now() - datetime.timedelta(days=60)).strftime(date_format)
        end_date = options.get("end_date")
        if not end_date:
            end_date = (datetime.datetime.now()).strftime(date_format)

        if datetime.datetime.strptime(end_date, date_format) - datetime.datetime.strptime(start_date, date_format) > datetime.timedelta(days=181):
            raise CommandError("Date range can't be >181 days.")

        data = {
            "type": "data-update",
            "force": options.get("force", False),
            "start_date": start_date,
            "end_date": end_date
        }
        redis_instance = redis.from_url(settings.REDIS)
        redis_instance.publish("request-refresh", json.dumps(data))
