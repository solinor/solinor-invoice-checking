import datetime
import logging
import requests
from invoices.models import HourEntry, Invoice, calculate_entry_stats, is_phase_billable, Project
from django.utils import timezone
from django.conf import settings
from django.utils.dateparse import parse_datetime as django_parse_datetime

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

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

def parse_datetime(date):
    if date is None:
        return None
    return django_parse_datetime(date)

def update_projects():
    logger.info("Updating projects")
    next_page = "/api/v1/projects?per_page=250&page=1"
    projects = []
    while next_page:
        logger.debug("Processing page %s", next_page)
        url = "https://api.10000ft.com%s&auth=%s" % (next_page, settings.TENKFEET_AUTH)
        tenkfeet_data = requests.get(url).json()
        for project in tenkfeet_data["data"]:
            project_fields = {
                "project_id": project["id"],
                "project_state": project["project_state"],
                "client": project["client"],
                "name": project["name"],
                "parent_id": project["parent_id"],
                "phase_name": project["phase_name"],
                "archived": project["archived"],
                "created_at": parse_datetime(project["created_at"]),
                "archived_at": parse_datetime(project["archived_at"]),
                "description": project["description"],
                "starts_at": parse_date(project["starts_at"]),
                "ends_at": parse_date(project["ends_at"]),
            }
            project_obj, _ = Project.objects.update_or_create(guid=project["guid"],
                                                              defaults=project_fields)
            projects.append(project_obj)
        next_page = tenkfeet_data["paging"]["next"]
    logger.info("Finished updating projects")
    for invoice in Invoice.objects.filter(project_m=None):
        for project in projects:
            if project.name == invoice.project and project.client == invoice.client:
                logger.info("Updating invoice %s with project %s", invoice, project)
                invoice.project_m = project
                invoice.save()
                break

def get_projects():
    projects_data = {}
    for project in Project.objects.all():
        projects_data[project.project_id] = project
    return projects_data


def get_invoices():
    invoices_data = {}
    for invoice in Invoice.objects.all():
        invoice_key = u"%s-%s %s - %s" % (invoice.year, invoice.month, invoice.client, invoice.project)
        invoices_data[invoice_key] = invoice
    return invoices_data


def update_data(start_date, end_date):
    logger.info("Starting hour entry update: %s - %s", start_date, end_date)
    now = timezone.now()
    url = "https://api.10000ft.com/api/v1/reports.json?startdate=%s&enddate=%s&today=%s&auth=%s" % (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d"), settings.TENKFEET_AUTH)
    tenkfeet_data = requests.get(url).json()
    logger.info("10k data downloaded")
    first_entry = datetime.date(2100, 1, 1)
    last_entry = datetime.date(1970, 1, 1)
    entries = []

    invoices_data = get_invoices()
    projects_data = get_projects()

    for entry in tenkfeet_data["time_entries"]:
        date = parse_date(entry[40])
        last_entry = max(last_entry, date)
        first_entry = min(first_entry, date)
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
            "calculated_is_billable": is_phase_billable(entry[31], entry[3]),
        }

        try:
            project_id = int(entry[32])
            if project_id in projects_data:
                logger.debug("Matched project %s", projects_data[project_id])
                data["project_m"] = projects_data[project_id]
            else:
                logger.debug("No match for project ID %s", project_id)
        except (ValueError, TypeError):
            pass

        assert data["year"] > 2000
        assert data["year"] < 2050
        assert data["bill_rate"] >= 0
        assert data["incurred_money"] >= 0
        assert data["incurred_hours"] >= 0

        invoice_key = u"%s-%s %s - %s" % (data["date"].year, data["date"].month, data["client"], data["project"])
        if invoice_key in invoices_data:
            logger.debug("Invoice already exists: %s", invoice_key)
            data["invoice"] = invoices_data[invoice_key]
            if invoices_data[invoice_key].tags != data["project_tags"]:
                invoices_data[invoice_key].tags = data["project_tags"]
                invoices_data[invoice_key].save()
        else:
            logger.info("Creating a new invoice: %s", invoice_key)
            invoice, _ = Invoice.objects.update_or_create(year=data["date"].year, month=data["date"].month, client=data["client"], project=data["project"], defaults={"tags": data["project_tags"]})
            invoices_data[invoice_key] = invoice
            data["invoice"] = invoice

        entries.append(HourEntry(**data))

    logger.info("Processed all 10k entries. Inserting to database.")
    # Note: this does not call .save() for entries.
    HourEntry.objects.bulk_create(entries)
    logger.info("All 10k entries added.")
    logger.info("Deleting old 10k entries.")
    HourEntry.objects.filter(date__gte=first_entry, date__lte=last_entry, last_updated_at__lt=now).delete()
    logger.info("All old 10k entries deleted.")
    return (first_entry, last_entry)


def refresh_stats(start_date, end_date):
    if start_date and end_date:
        logger.info("Updating statistics for invoices between %s and %s", start_date, end_date)
        invoices = Invoice.objects.filter(year__gte=start_date.year, year__lte=end_date.year, month__gte=start_date.month, month__lte=end_date.month)
    else:
        logger.info("Updating statistics for all invoices")
        invoices = Invoice.objects.all()
    for invoice in invoices:
        entries = HourEntry.objects.filter(invoice=invoice).filter(incurred_hours__gt=0)
        stats = calculate_entry_stats(entries)
        for field in STATS_FIELDS:
            setattr(invoice, field, stats[field])
        invoice.save()
        logger.debug("Updated statistics for %s", invoice)
