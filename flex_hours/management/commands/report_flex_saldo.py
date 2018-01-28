import datetime

from django.core.management.base import BaseCommand

from flex_hours.utils import FlexHourException, calculate_flex_saldo
from invoices.models import TenkfUser


class Command(BaseCommand):
    help = "Report flex saldo for everyone"

    def add_arguments(self, parser):
        parser.add_argument(
            "--flex-end-date",
            dest="end_date",
            help="Last date included in flex saldo report (YYYY-MM-DD)",
        )

    def handle(self, *args, **options):
        end_date = options.get("end_date")
        if end_date:
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()

        users = []
        for user in TenkfUser.objects.all():
            try:
                flex_info = calculate_flex_saldo(user, end_date)
            except FlexHourException as error:
                print("Unable to calculate the report for %s: %s" % (user, error))
                continue
            users.append((flex_info["person"].email, flex_info["cumulative_saldo"]))
        users = sorted(users, key=lambda k: k[1])
        for email, flex_hours in users:
            print("%s - %sh" % (email, flex_hours))
