import datetime
import json

import redis
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Queue new data refresh"

    MAX_RANGE_LENGTH = datetime.timedelta(days=181)
    AUTO_SPLIT_RANGE_LENGTH = datetime.timedelta(days=90)
    DATE_FORMAT = "%Y-%m-%d"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            dest="force",
            help="Force update, instead of skipping if update was recently executed",
        )
        parser.add_argument(
            "--automatic-split",
            action="store_true",
            dest="automatic_split",
            help="Automatically split long date ranges to shorter update requests. For consistent results, consider using --force with this.",
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
        if options.get("start_date"):
            start_date = datetime.datetime.strptime(options.get("start_date"), self.DATE_FORMAT).date()
        else:
            start_date = (datetime.date.today() - datetime.timedelta(days=60))

        if options.get("end_date"):
            end_date = datetime.datetime.strptime(options.get("end_date"), self.DATE_FORMAT).date()
        else:
            end_date = (datetime.date.today() + datetime.timedelta(days=2))

        if end_date < start_date:
            raise CommandError("Start date must be larger than end date.")

        force = options.get("force", False)
        if not options.get("automatic_split", False):
            self.add_to_queue(start_date, end_date, force)
        else:
            current_date = start_date
            while current_date < end_date:
                self.add_to_queue(current_date, min(current_date + self.AUTO_SPLIT_RANGE_LENGTH, end_date), force)
                current_date += self.AUTO_SPLIT_RANGE_LENGTH

    def add_to_queue(self, start_date, end_date, force):
        if end_date - start_date > self.MAX_RANGE_LENGTH:
            raise CommandError("Date range can't be >{} days.".format(self.MAX_RANGE_LENGTH.days))
        data = {
            "type": "data-update",
            "force": force,
            "start_date": start_date.strftime(self.DATE_FORMAT),
            "end_date": end_date.strftime(self.DATE_FORMAT),
        }
        self.stdout.write(self.style.SUCCESS(f"Queued update for {start_date} - {end_date}"))
        redis_instance = redis.from_url(settings.REDIS)
        redis_instance.publish("request-refresh", json.dumps(data))
