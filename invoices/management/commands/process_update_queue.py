import datetime
import redis

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings

from invoices.models import DataUpdate
from invoices.utils import update_data, refresh_stats


class Command(BaseCommand):
    help = 'Import data from 10k feet API'

    def handle(self, *args, **options):
        redis_instance = redis.from_url(settings.REDIS)
        pubsub = redis_instance.pubsub()
        pubsub.subscribe("request-refresh")
        for _ in pubsub.listen():
            now = timezone.now()
            try:
                latest_run = DataUpdate.objects.exclude(finished_at=None).latest("finished_at")
                if now - latest_run.finished_at < datetime.timedelta(minutes=1):
                    print "Latest run was finished recently. Skip."
                    latest_run.aborted = True
                    latest_run.save()
                    continue
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
            start_date = (now - datetime.timedelta(days=45))
            end_date = now
            print "Updating data."
            update_obj.started_at = timezone.now()
            update_data(start_date, end_date)
            print "Data update done."
            print "Update statistics."
            refresh_stats(start_date, end_date)
            update_obj.finished_at = timezone.now()
            update_obj.aborted = False
            update_obj.save()
            print "Statistics updated."
