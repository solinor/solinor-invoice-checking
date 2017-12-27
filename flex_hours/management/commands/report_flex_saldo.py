from django.core.management.base import BaseCommand

from flex_hours.utils import FlexHourException, calculate_flex_saldo
from invoices.models import TenkfUser


class Command(BaseCommand):
    help = 'Report flex saldo for everyone'

    def handle(self, *args, **options):
        users = []
        for user in TenkfUser.objects.all():
            try:
                flex_info = calculate_flex_saldo(user)
            except FlexHourException as error:
                print("Unable to calculate the report for %s: %s" % (user, error))
                continue
            users.append((flex_info["person"].email, flex_info["flex_hours"]))
        users = sorted(users, key=lambda k: k[1])
        for email, flex_hours in users:
            print("%s - %sh" % (email, flex_hours))
