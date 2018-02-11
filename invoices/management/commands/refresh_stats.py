import datetime

from django.core.management.base import BaseCommand

from invoices.utils import refresh_invoice_stats


class Command(BaseCommand):
    help = 'Refresh statistics for each invoice'

    def add_arguments(self, parser):
        parser.add_argument(
            "--end-date",
            dest="end_date",
            help="Last month to include in statistics refresh",
        )
        parser.add_argument(
            "--start-date",
            dest="start_date",
            help="First month to include in statistics refresh",
        )

    def handle(self, *args, **options):
        if options["start_date"]:
            start_date = datetime.datetime.strptime(options["start_date"], "%Y-%m").date()
        else:
            start_date = None
        if options["end_date"]:
            end_date = datetime.datetime.strptime(options["end_date"], "%Y-%m").date()
        else:
            end_date = None

        refresh_invoice_stats(start_date, end_date)
        self.stdout.write(self.style.SUCCCESS(f"Updated invoice statistics: {start_date} - {end_date}"))
