import os
import requests
import datetime
import django.db.utils
from django.utils import timezone
import sys
from invoices.models import HourEntry, Invoice, calculate_entry_stats, DataUpdate

TENKFEET_AUTH = os.environ["TENKFEET_AUTH"]
STATS_FIELDS = [
    "billable_incorrect_price_count",
    "non_billable_hours_count",
    "non_phase_specific_count",
    "not_approved_hours_count",
    "empty_descriptions_count",
    "total_hours",
    "bill_rate_avg",
    "total_money"]


def parse_date(date):
    date = date.split("-")
    return datetime.datetime(int(date[0]), int(date[1]), int(date[2])).date()

def parse_float(data):
    try:
        return float(data)
    except TypeError:
        return 0


def update_data(start_date, end_date):
    now = timezone.now()
    today = now.strftime("%Y-%m-%d")
    url = "https://api.10000ft.com/api/v1/reports.json?startdate=%s&enddate=%s&today=%s&auth=%s" % (start_date, end_date, today, TENKFEET_AUTH)
    data = requests.get(url)
    first_entry = datetime.date(2100, 1, 1)
    last_entry = datetime.date(1970, 1, 1)
    entries = []
    projects = {}
    for entry in data.json()["time_entries"]:
        date = parse_date(entry[40])
        if date > last_entry:
            last_entry = date
        if date < first_entry:
            first_entry = date
        data = {
            "date": date,
            "year": date.year,
            "month": date.month,
            "user_id": int(entry[0]),
            "user_name": entry[1],
            "client": entry[6],
            "project": entry[3],
            "incurred_hours": parse_float(entry[8]),
            "incurred_money": parse_float(entry[11]),
            "category": entry[14],
            "notes": entry[15],
            "entry_type": entry[17],
            "discipline": entry[18],
            "role": entry[19],
            "bill_rate": parse_float(entry[28]),
            "leave_type": entry[16],
            "phase_name": entry[31],
            "billable": entry[21] in ("1", 1),
            "approved": entry[52] == "Approved",
            "user_email": entry[29],
            "project_tags": entry[34],
            "last_updated_at": now,
        }
        assert data["year"] > 2000
        assert data["year"] < 2050
        assert data["bill_rate"] >= 0
        assert data["incurred_money"] >= 0
        assert data["incurred_hours"] >= 0
        entry = HourEntry(**data)
        entries.append(entry)

        project_key = "%s %s - %s" % (data["date"].strftime("%Y-%m"), data["client"], data["project"])
        if project_key not in projects:
            projects[project_key] = True
            Invoice.objects.update_or_create(year=data["date"].year, month=data["date"].month, client=data["client"], project=data["project"], defaults={"tags": data["project_tags"]})

    # Note: this does not call .save() for entries.
    HourEntry.objects.bulk_create(entries)
    HourEntry.objects.filter(date__gte=first_entry, date__lte=last_entry, last_updated_at__lt=now).delete()


def refresh_stats():
    for invoice in Invoice.objects.all():
        entries = HourEntry.objects.filter(project=invoice.project, client=invoice.client, date__year__gte=invoice.year, date__month=invoice.month).filter(incurred_hours__gt=0)
        stats = calculate_entry_stats(entries)
        for field in STATS_FIELDS:
            setattr(invoice, field, stats[field])
        total_issues = invoice.total_issues()
        if total_issues != "?":
            invoice.incorrect_entries_count = total_issues
        else:
            invoice.incorrect_entries_count = None
        invoice.save()
