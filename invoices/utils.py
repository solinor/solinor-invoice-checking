import datetime
import logging

from django.utils import timezone
from django.utils.dateparse import parse_datetime as django_parse_datetime
from django.conf import settings

from invoices.tenkfeet_api import TenkFeetApi
from invoices.models import HourEntry, Invoice, is_phase_billable, Project, FeetUser, WeeklyReport
from invoices.slack import send_slack_notification
from invoices.invoice_utils import calculate_entry_stats, get_aws_entries, calculate_weekly_entry_stats


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name
tenkfeet_api = TenkFeetApi(settings.TENKFEET_AUTH)  # pylint: disable=invalid-name

STATS_FIELDS = [
    "incorrect_entries_count",
    "billable_incorrect_price_count",
    "non_billable_hours_count",
    "non_phase_specific_count",
    "not_approved_hours_count",
    "empty_descriptions_count",
]


def parse_date(date):
    if date:
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


def update_users():
    logger.info("Updating users")
    tenkfeet_users = tenkfeet_api.fetch_users()
    total_updated = 0
    for user in tenkfeet_users:
        user_email = user["email"]
        user_fields = {
            "user_id": user["id"],
            "first_name": user["first_name"],
            "last_name": user["last_name"],
            "archived": user["archived"],
            "display_name": user["display_name"],
            "email": user_email,
            "billable": user["billable"],
            "hire_date": parse_date(user["hire_date"]),
            "termination_date": parse_date(user["termination_date"]),
            "mobile_phone": user["mobile_phone"],
            "invitation_pending": user["invitation_pending"],
            "billability_target": user["billability_target"],
            "created_at": parse_datetime(user["created_at"]),
            "archived_at": user["archived_at"],
            "thumbnail": user["thumbnail"],
        }
        user_obj, _ = FeetUser.objects.update_or_create(guid=user["guid"], defaults=user_fields)
        updated_objects = HourEntry.objects.filter(user_email=user_email).filter(user_m=None).update(user_m=user_obj)
        logger.debug("Updated %s to %s entries", user_email, updated_objects)
        total_updated += updated_objects
    logger.info("Updated %s hour entries and %s users", total_updated, len(tenkfeet_users))


def update_projects():
    logger.info("Updating projects")
    tenkfeet_projects = tenkfeet_api.fetch_projects()
    projects = []
    for project in tenkfeet_projects:
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
        project_obj, created = Project.objects.update_or_create(guid=project["guid"],
                                                                defaults=project_fields)
        user_cache = {}

        for tag in project["tags"]["data"]:
            tag_value = tag["value"]
            if tag_value in user_cache:
                matching_users = user_cache[tag_value]
            else:
                try:
                    first_name, last_name = tag_value.split(" ", 1)
                except ValueError:
                    logger.info("Invalid tag: %s for %s", tag, project["id"])
                matching_users = FeetUser.objects.filter(first_name=first_name, last_name=last_name)
                logger.debug("Matched %s to tag %s; first_name=%s, last_name=%s", matching_users, tag, first_name, last_name)
                user_cache[tag_value] = matching_users

            project_obj.admin_users.clear()
            for matching_user in matching_users:
                project_obj.admin_users.add(matching_user)
        project_obj.save()
        projects.append(project_obj)
        if created:
            send_slack_notification(project_obj)
    logger.info("Finished updating projects (n=%s)", len(projects))
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


def get_weekly_reports():
    weekly_report_data = {}
    for weekly_report in WeeklyReport.objects.all():
        weekly_report_key = u"%s-%s %s - %s" % (weekly_report.year, weekly_report.week, weekly_report.project_m.client, weekly_report.project_m.project)
        weekly_report_data[weekly_report_key] = weekly_report
    return weekly_report_data


def get_users():
    users = {}
    for user in FeetUser.objects.all():
        users[user.email] = user
    return users


class HourEntryUpdate(object):
    def __init__(self, start_date, end_date):
        self.logger = logging.getLogger(__name__)
        self.invoices_data = get_invoices()
        self.weekly_report_data = get_weekly_reports()
        self.projects_data = get_projects()
        self.user_data = get_users()
        self.start_date = start_date
        self.end_date = end_date
        self.first_entry = datetime.date(2100, 1, 1)
        self.last_entry = datetime.date(1970, 1, 1)

    def update_range(self, date):
        self.last_entry = max(self.last_entry, date)
        self.first_entry = min(self.first_entry, date)

    def match_project(self, project_id):
        return self.projects_data.get(project_id, None)

    def match_invoice(self, data):
        invoice_key = u"%s-%s %s - %s" % (data["date"].year, data["date"].month, data["client"], data["project"])
        invoice = self.invoices_data.get(invoice_key)
        if invoice:
            logger.debug("Invoice already exists: %s", invoice_key)
            if invoice.tags != data["project_tags"]:
                invoice.tags = data["project_tags"]
                invoice.save()
            return invoice
        else:
            logger.info("Creating a new invoice: %s", invoice_key)
            invoice = Invoice(year=data["date"].year, month=data["date"].month, client=data["client"], project=data["project"], tags=data["project_tags"])
            invoice.save()
            self.invoices_data[invoice_key] = invoice
            return invoice

    def match_weekly_report(self, data):
        week_number = data["date"].isocalendar()[1]  # week number, 1-53
        weekly_report_key = u"%s-%s %s - %s" % (data["date"].year, week_number, data["client"], data["project"])
        weekly_report = self.weekly_report_data.get(weekly_report_key)
        if weekly_report:
            logger.debug("Weekly report already exists: %s", weekly_report_key)
            if weekly_report.tags != data["project_tags"]:
                weekly_report.tags = data["project_tags"]
                weekly_report.save()
            return weekly_report
        else:
            logger.info("Creating a new weekly report %s", weekly_report_key)
            projects = Project.objects.filter(name=data["project"], client=data["client"])
            if not projects:
                logger.error("No project %s with client %s found, cannot create weekly report", data["project"], data["client"])
                return
            project = projects[0]
            weekly_report = WeeklyReport(year=data["date"].year, week=week_number, project_m=project, tags=data["project_tags"])
            weekly_report.save()
            self.weekly_report_data[weekly_report_key] = weekly_report
            return weekly_report

    def match_user(self, email):
        return self.user_data.get(email)

    def update(self):
        self.logger.info("Starting hour entry update: %s - %s", self.start_date, self.end_date)
        now = timezone.now()
        tenkfeet_entries = tenkfeet_api.fetch_hour_entries(now, self.start_date, self.end_date)
        entries = []

        for entry in tenkfeet_entries:
            date = parse_date(entry[40])
            data = {
                "date": date,
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
                "status": entry[52],
                "user_email": entry[29],
                "project_tags": entry[34],
                "last_updated_at": now,
                "calculated_is_billable": is_phase_billable(entry[31], entry[3]),
            }
            if data["incurred_hours"] == 0 or data["incurred_hours"] is None:
                logger.debug("Skipping hour entry with 0 incurred hours: %s", data)
                continue

            self.update_range(date)

            try:
                project_id = int(entry[32])
                data["project_m"] = self.match_project(project_id)
            except (ValueError, TypeError):
                pass

            assert data["date"].year > 2000
            assert data["date"].year < 2050
            assert data["bill_rate"] >= 0
            assert data["incurred_money"] >= 0
            assert data["incurred_hours"] >= 0

            data["invoice"] = self.match_invoice(data)
            data["weekly_report"] = self.match_weekly_report(data)
            data["user_m"] = self.match_user(data["user_email"])
            entry = HourEntry(**data)
            entry.update_calculated_fields()
            entries.append(entry)

        # TODO: this add and remove process should be atomic.
        logger.info("Processed all 10k entries. Inserting %s entries to database.", len(entries))
        # Note: this does not call .save() for entries.
        HourEntry.objects.bulk_create(entries)
        logger.info("All 10k entries added.")
        logger.info("Deleting old 10k entries.")
        HourEntry.objects.filter(date__gte=self.first_entry, date__lte=self.last_entry, last_updated_at__lt=now).delete()
        logger.info("All old 10k entries deleted.")
        return (self.first_entry, self.last_entry)


def refresh_report(report, stats):
    for field in STATS_FIELDS:
        setattr(report, field, stats[field])

    report.incurred_money = sum(
        [row["incurred_money"] for row in stats["total_rows"].values() if "incurred_money" in row])
    report.incurred_hours = sum(
        [row["incurred_hours"] for row in stats["total_rows"].values() if "incurred_hours" in row])
    report.incurred_billable_hours = stats["total_rows"]["hours"]["incurred_billable_hours"]
    if report.incurred_hours > 0:
        report.billable_percentage = report.incurred_billable_hours / report.incurred_hours
    else:
        report.billable_percentage = 0
    if stats["total_rows"]["hours"]["incurred_hours"] > 0:
        report.bill_rate_avg = stats["total_rows"]["hours"]["incurred_money"] / stats["total_rows"]["hours"][
            "incurred_hours"]
    else:
        report.bill_rate_avg = 0
    report.save()
    logger.debug("Updated statistics for %s", report)


def refresh_stats(start_date, end_date):
    if start_date and end_date:
        invoices = Invoice.objects.filter(year__gte=start_date.year, year__lte=end_date.year, month__gte=start_date.month, month__lte=end_date.month)  # TODO: this is not working properly over new year.
        logger.info("Updating statistics for invoices between %s and %s: %s invoices", start_date, end_date, invoices.count())
    else:
        logger.info("Updating statistics for all invoices")
        invoices = Invoice.objects.all()
    for invoice in invoices:
        entries = HourEntry.objects.filter(invoice=invoice).filter(incurred_hours__gt=0)
        aws_entries = None
        if invoice.project_m:
            aws_accounts = invoice.project_m.amazon_account.all()
            aws_entries = get_aws_entries(aws_accounts, invoice.month_start_date, invoice.month_end_date)
        stats = calculate_entry_stats(entries, invoice.get_fixed_invoice_rows(), aws_entries)

        refresh_report(invoice, stats)


def refresh_weekly_stats(start_date, end_date):
    if start_date and end_date:
        weekly_reports = WeeklyReport.objects.filter(year__gte=start_date.year, year__lte=end_date.year, week__gte=start_date.isocalendar()[1], week__lte=end_date.isocalendar()[1])
        logger.info("Updating statistics for weekly reports between %s and %s: %s invoices", start_date, end_date, weekly_reports.count())
    else:
        logger.info("Updating statistics for all weekly reports")
        weekly_reports = WeeklyReport.objects.all()
    for weekly_report in weekly_reports:
        entries = HourEntry.objects.filter(weekly_report=weekly_report).filter(incurred_hours__gt=0)
        aws_entries = None
        stats = calculate_weekly_entry_stats(entries, aws_entries)

        refresh_report(weekly_report, stats)
