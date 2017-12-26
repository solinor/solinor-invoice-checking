import datetime
import json
import logging

import redis
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from invoices.models import DataUpdate
from invoices.slack import send_unapproved_hours_notifications, send_unsubmitted_hours_notifications
from invoices.utils import HourEntryUpdate, refresh_stats


def update_10kf_data(logger, data):
    now = timezone.now()
    try:
        latest_run = DataUpdate.objects.exclude(finished_at=None).latest("finished_at")
        if now - latest_run.finished_at < datetime.timedelta(seconds=10):
            logger.info("Latest run was finished recently. Skip this data update.")
            latest_run.aborted = True
            latest_run.save()
            return
    except DataUpdate.DoesNotExist:
        pass
    update_obj = DataUpdate.objects.filter(started_at=None).filter(aborted=False)
    obj_count = update_obj.count()
    if obj_count > 1:
        update_obj.update(aborted=True)
        update_obj = update_obj[obj_count - 1]
    else:
        update_obj = DataUpdate()
    DataUpdate.objects.filter(aborted=False).filter(finished_at=None).update(aborted=True)
    update_obj.aborted = False
    update_obj.started_at = timezone.now()
    update_obj.save()
    start_date = datetime.datetime.strptime(data["start_date"], "%Y-%m-%d").date()
    end_date = datetime.datetime.strptime(data["end_date"], "%Y-%m-%d").date()
    logger.info("Updating data.")
    update_obj.started_at = timezone.now()
    hour_entry_update = HourEntryUpdate(start_date, end_date)
    hour_entry_update.update()
    logger.info("Data update done.")
    logger.info("Update statistics.")
    refresh_stats(start_date, end_date)
    update_obj.finished_at = timezone.now()
    update_obj.aborted = False
    update_obj.save()
    logger.info("Statistics updated.")


def slack_unapproved_notifications(logger, data):
    today = datetime.date.today()
    send_unapproved_hours_notifications(today.year, today.month)


def slack_unsubmitted_notifications(logger, data):
    send_unsubmitted_hours_notifications()


class Command(BaseCommand):
    help = 'Import data from 10k feet API'

    def handle(self, *args, **options):
        logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

        redis_instance = redis.from_url(settings.REDIS)
        pubsub = redis_instance.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe("request-refresh")
        for entry in pubsub.listen():
            logger.debug("Received %s from redis queue", entry)
            data = json.loads(entry["data"])
            if data["type"] == "data-update":
                update_10kf_data(logger, data)
            elif data["type"] == "slack-unsubmitted-notification":
                slack_unsubmitted_notifications(logger, data)
            elif data["type"] == "slack-unapproved-notification":
                slack_unapproved_notifications(logger, data)
            else:
                logger.error("Unhandled data: %s", entry)
