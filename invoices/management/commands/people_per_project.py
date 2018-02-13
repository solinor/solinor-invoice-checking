import datetime
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db.models import Q

from invoices.models import HourEntry, Invoice


class Command(BaseCommand):
    help = "Statistics for number of people per project."

    def add_arguments(self, parser):
        parser.add_argument(
            "--start-date",
            dest="start_date",
        )
        parser.add_argument(
            "--end-date",
            dest="end_date",
        )

    def handle(self, *args, **options):
        range_start_date = datetime.datetime.strptime(options["start_date"], "%Y-%m-%d")
        range_end_date = datetime.datetime.strptime(options["end_date"], "%Y-%m-%d")
        data = defaultdict(dict)
        current_day = range_start_date
        all_months = set()
        while current_day < range_end_date:
            start_date = current_day
            end_date = (current_day + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)

            active_invoices = Invoice.objects.exclude(Q(incurred_hours=0) & Q(incurred_money=0)).exclude(project_m__project_state="Internal").exclude(client__in=["Solinor", "[none]"]).filter(date__gte=start_date, date__lte=end_date).exclude(project_m=None).select_related("project_m", "project_m__client_m")
            clients = {invoice.project_m.client_m for invoice in active_invoices}

            people_entries = defaultdict(lambda: defaultdict(set))
            for item in HourEntry.objects.filter(invoice__project_m__client_m__in=clients).filter(date__gte=start_date).filter(date__lte=end_date).values("invoice__project_m__client_m__name", "date", "user_email").order_by("invoice__project_m__client_m__name", "date", "user_email"):
                people_entries[item["invoice__project_m__client_m__name"]][item["date"]].add(item["user_email"])

            for client, entries in people_entries.items():
                c = people = 0
                for _, names in entries.items():
                    c += 1
                    people += len(names)
                data[client][start_date.strftime("%Y-%m")] = people / c
                all_months.add(start_date.strftime("%Y-%m"))

            if current_day.month == 12:
                current_day = current_day.replace(year=current_day.year + 1).replace(month=1)
            else:
                current_day = current_day.replace(month=current_day.month + 1)

        all_months = sorted(all_months)
        print("\t{}".format("\t".join(all_months)))
        for client, items in data.items():
            per_month = []
            for month in all_months:
                per_month.append(str(items.get(month, 0)))
            print("{}\t{}".format(client, "\t".join(per_month)))
