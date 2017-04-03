import csv
from django.core.management.base import BaseCommand, CommandError
from invoices.models import HourEntry, Invoice
import datetime
import django.db.utils
import sys


def parse_date(date):
    date = date.split("-")
    return datetime.datetime(int(date[0]), int(date[1]), int(date[2])).date()


class Command(BaseCommand):
    help = 'Import CSV file(s)'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', nargs='+', type=str)

    def handle(self, *args, **options):
        for csv_file in options['csv_file']:
            if csv_file == "-":
                f = sys.stdin
            else:
                f = open(csv_file)
            csvreader = csv.reader(f)
            _ = next(csvreader)
            projects = {}

            for line in csvreader:
                date = parse_date(line[1])
                data = {
                    "date": date,
                    "year": date.year,
                    "month": date.month,
                    "user_id": int(line[2]),
                    "user_name": line[3],
                    "client": line[5],
                    "project": line[6],
                    "incurred_hours": float(line[8]),
                    "incurred_money": float(line[12]),
                    "category": line[15],
                    "notes": line[16],
                    "entry_type": line[17],
                    "discipline": line[19],
                    "role": line[20],
                    "bill_rate": float(line[21]),
                    "leave_type": line[25],
                    "phase_name": line[26],
                    "billable": line[37] == "1",
                    "approved": line[42] == "Approved",
                }
                entry = HourEntry(**data)
                entry.save()

                project_key = "%s %s - %s" % (data["date"].strftime("%Y-%m"), data["client"], data["project"])
                if project_key not in projects:
                    projects[project_key] = True
                    invoice = Invoice(year=data["date"].year, month=data["date"].month, client=data["client"], project=data["project"])
                    try:
                        invoice.save()
                        print invoice.id
                    except django.db.utils.IntegrityError:
                        pass
