import hashlib
import json
import logging
from collections import defaultdict
from datetime import date, datetime

from django.conf import settings
from django.db import transaction
from django.db.utils import IntegrityError
from django.forms.models import model_to_dict
from django.utils import timezone

from invoices.invoice_utils import calculate_entry_stats, get_aws_entries
from invoices.models import Client, Event, HourEntry, HourEntryChecksum, Invoice, Project, TenkfUser, is_phase_billable
from invoices.slack import send_new_project_to_slack
from invoices.tenkfeet_api import TenkFeetApi
from invoices.utils import daterange

tenkfeet_api = TenkFeetApi(settings.TENKFEET_AUTH)  # pylint: disable=invalid-name

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


def sync_10000ft_users(force: bool = False) -> None:
    logger.info("Updating users")
    tenkfeet_users = tenkfeet_api.fetch_users()
    updated_hour_entries = updated_users = created_users = 0
    all_users = {str(user["guid"]): user["updated_at"] for user in TenkfUser.objects.values("guid", "updated_at")}
    for user in tenkfeet_users:
        if not user["email"]:
            continue
        user_email = user["email"]
        updated_at = user["updated_at"]

        if user["guid"] in all_users:
            if all_users[user["guid"]] == updated_at and not force:
                logger.info("Skip updating %s (%s) - update timestamp matches", user["email"], user["guid"])
                continue
        logger.info("Updating user %s - %s - %s", user["guid"], all_users.get(user["guid"]), user["updated_at"])

        user_fields = {
            "user_id": user["id"],
            "first_name": user["first_name"],
            "last_name": user["last_name"],
            "archived": user["archived"],
            "display_name": user["display_name"],
            "email": user_email,
            "billable": user["billable"],
            "hire_date": user["hire_date"],
            "termination_date": user["termination_date"],
            "mobile_phone": user["mobile_phone"],
            "invitation_pending": user["invitation_pending"],
            "billability_target": user["billability_target"],
            "created_at": user["created_at"],
            "archived_at": user["archived_at"],
            "updated_at": user["updated_at"],
            "thumbnail": user["thumbnail"],
            "role": user["role"],
            "discipline": user["discipline"],
        }
        # TODO: always ensure non-archived user is added to the DB
        try:
            user_obj, created = TenkfUser.objects.update_or_create(guid=user["guid"], defaults=user_fields)
            if created:
                created_users += 1
            else:
                updated_users += 1
        except IntegrityError:
            logger.info("Unable to update %s - duplicate email", user_email)
            continue
        updated_objects = HourEntry.objects.filter(user_email__iexact=user_email).filter(user_m=None).update(user_m=user_obj)
        logger.debug("Updated %s to %s entries", user_email, updated_objects)
        updated_hour_entries += updated_objects
    logger.info("Got %s users from 10000ft, updated %s users, created %s users, linked %s hour entries", len(tenkfeet_users), updated_users, created_users, updated_hour_entries)
    Event(event_type="sync_10000ft_users", succeeded=True, message="Got {} users from 10000ft, updated {} users, created {} users, linked {} hour entries".format(len(tenkfeet_users), updated_users, created_users, updated_hour_entries)).save()


def sync_10000ft_projects(force=False):  # pylint: disable=unused-argument
    logger.info("Updating projects")
    tenkfeet_projects = tenkfeet_api.fetch_projects()
    projects = []
    created_count = 0
    clients = {client.name: client for client in Client.objects.all()}
    for project in tenkfeet_projects:
        if project["client"] is None:
            project["client"] = "none"
        client = clients.get(project["client"])
        if not client:
            client, _ = Client.objects.get_or_create(name=project["client"])
            clients[client.name] = client
        project_fields = {
            "project_id": project["id"],
            "project_state": project["project_state"],
            "client_m": client,
            "name": project["name"],
            "parent_id": project["parent_id"],
            "phase_name": project["phase_name"],
            "archived": project["archived"],
            "created_at": project["created_at"],
            "archived_at": project["archived_at"],
            "description": project["description"],
            "starts_at": project["starts_at"],
            "ends_at": project["ends_at"],
            "thumbnail_url": project["thumbnail"],
        }
        project_obj, created = Project.objects.update_or_create(guid=project["guid"], defaults=project_fields)
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
                    continue
                matching_users = TenkfUser.objects.filter(first_name=first_name, last_name=last_name).filter(archived=False)
                logger.debug("Matched %s to tag %s; first_name=%s, last_name=%s", matching_users, tag, first_name, last_name)
                user_cache[tag_value] = matching_users

            with transaction.atomic():
                project_obj.admin_users.clear()
                for matching_user in matching_users:
                    project_obj.admin_users.add(matching_user)
        project_obj.save()
        projects.append(project_obj)
        if created:
            created_count += 1
            send_new_project_to_slack(project_obj)
    logger.info("Finished updating projects (n=%s)", len(projects))
    linked_invoices = 0
    Event(event_type="sync_10000ft_projects", succeeded=True, message=f"Updated {len(projects)} projects, created {created_count} projects and linked {linked_invoices} invoices to projects").save()


def get_projects():
    return {project.project_id: project for project in Project.objects.all()}


def get_invoices():
    return {f"{invoice.date:%Y-%m} {invoice.project_m.project_id}": invoice for invoice in Invoice.objects.all()}  # TODO: cache key is hardcoded


def get_users():
    return {user.email: user for user in TenkfUser.objects.all()}


def get_clients():
    return {item.name: item for item in Client.objects.all()}


def parse_upstream_id(upstream_id):
    if not upstream_id:
        return None
    return int(upstream_id.split("-")[-1])


class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()

        return json.JSONEncoder.default(self, o)


def fetch_assignables():
    result = {}
    phases = {phase["id"]: phase for phase in tenkfeet_api.fetch_phases()}

    for id, phase in phases.items():
        if phase.get("parent_id"):
            result[id] = {
                "project": phases[phase["parent_id"]],
                "phase": phase
            }
        else:
            result[id] = {
                "project": phase,
                "phase": {}
            }

    return result


class HourEntryUpdate(object):
    def __init__(self, start_date, end_date):
        self.logger = logging.getLogger(__name__)
        self.invoices_data = get_invoices()
        self.projects_data = get_projects()
        self.clients_data = get_clients()
        self.leave_project = Project.objects.get(name="[Leave Type]")  # TODO: this should not be hardcoded
        self.user_data = get_users()
        self.start_date = start_date
        self.end_date = end_date
        self.first_entry = date(2100, 1, 1)
        self.last_entry = date(1970, 1, 1)

    def update_range(self, date):
        self.last_entry = max(self.last_entry, date)
        self.first_entry = min(self.first_entry, date)

    def match_client(self, client_name):
        if client_name in self.clients_data:
            return self.clients_data[client_name]
        client, _ = Client.objects.get_or_create(name=client_name)
        self.clients_data[client_name] = client
        return client

    def match_project(self, project_id, client, project):
        if not project_id:
            if project in ["[Leave Type]", "LeaveType"]:  # TODO: this should not be hardcoded
                return self.leave_project
            # 10000ft returns some entries without project IDs
            try:
                return Project.objects.get(name=project, client_m__name=client)
            except Project.DoesNotExist:
                return None
        return self.projects_data.get(project_id, None)

    def match_invoice(self, date, project_id, client, project):
        date = date.replace(day=1)
        project_m = self.match_project(project_id, client, project)
        if not project_m:
            return None

        invoice_key = f"{date:%Y-%m} {project_id}"  # TODO: cache key is hardcoded
        invoice = self.invoices_data.get(invoice_key)
        if invoice:
            logger.debug("Invoice already exists: %s - project_m=%s", date, project_m)
            return invoice
        logger.info("Creating a new invoice: %s - project_m=%s", date, project_m)
        invoice, _ = Invoice.objects.update_or_create(date=date, project_m=project_m)
        self.invoices_data[invoice_key] = invoice
        return invoice

    def match_user(self, email):
        return self.user_data.get(email)

    def update(self):
        def fetch_per_date_data():
            date_data = defaultdict(lambda: {"items": [], "sha256": hashlib.sha256()})
            for entry in tenkfeet_api.fetch_api_hour_entries(self.start_date, self.end_date):
                if entry["hours"] in (0, None):
                    logger.debug("Skipping hour entry with 0 incurred hours: %s", entry)
                else:
                    entry_date = entry["date"]
                    date_data[entry_date]["sha256"].update(json.dumps(entry, cls=DateTimeEncoder).encode())
                    date_data[entry_date]["items"].append(entry)

            return date_data

        def merge_data(entry, users, assignables):
            def datetime_to_date(dt):
                if dt:
                    return dt.date()
                return None

            def legacy_leave_type():
                if entry["assignable_type"] == "Project":
                    return "[project]"
                return entry["assignable_type"]

            def status(approval):
                if not approval:
                    return "Unsubmitted"
                if approval.get("approved_at"):
                    return "Approved"
                return "Pending Approval"

            approvals = entry.get("approvals") or {}
            approval_data = approvals.get("data")
            if approval_data:
                approval = approval_data[0]
            else:
                approval = {}

            user = users[entry["user_id"]]
            assignable = assignables.get(entry["assignable_id"]) or {}
            project = assignable.get("project") or {}

            data = {
                "date": entry["date"],
                "user_id": entry["user_id"],
                "user_name": user["display_name"],
                "assignable_id": entry["assignable_id"],
                "approved_at": datetime_to_date(approval.get("approved_at")),
                "upstream_id": entry["id"],
                "approved_by": approval.get("approved_by"),
                "submitted_by": approval.get("submitted_by"),
                "updated_at": entry.get("updated_at"),
                "created_at": entry.get("created_at"),
                "project": project.get("name") or "[Leave Type]",
                "client": project.get("client") or "[none]",
                "incurred_hours": entry["hours"],
                "incurred_money": entry["bill_rate"] * entry["hours"],
                "category": entry.get("task") or "[none]",
                "notes": entry.get("notes"),
                "entry_type": "Confirmed" if not entry["is_suggestion"] else "Suggestion",
                "discipline": user.get("discipline") or "[none]",
                "role": user.get("role") or "[none]",
                "bill_rate": entry["bill_rate"],
                "leave_type": legacy_leave_type(),
                "phase_name": assignable.get("phase", {}).get("phase_name") or "[Non Phase Specific]",
                "billable": is_phase_billable(
                    phase_name="",
                    project=project.get("name") or "[Leave Type]"
                ),  # TODO Check what is this value and is it meaningful at all. Only 'billable' in API is from user
                "approved": approval is not None,
                "status": status(approval),
                "user_email": user["email"].lower(),
                "last_updated_at": now,
                "calculated_is_billable": is_phase_billable(
                    phase_name=assignable.get("phase", {}).get("phase_name") or "[Non Phase Specific]",
                    project=project.get("name") or "[Leave Type]"
                ),
                "upstream_approvable_id": approval.get("id"),
                "upstream_approvable_updated_at": approval.get("updated_at"),
            }

            assert data["date"].year > 2000
            assert data["date"].year < 2050
            assert data["bill_rate"] >= 0
            assert data["incurred_money"] >= 0
            assert data["incurred_hours"] >= 0

            # Reset billing rates and money for all leaves
            if data["leave_type"] != "[project]":
                data["incurred_money"] = data["bill_rate"] = 0

            return data

        self.logger.info("Starting hour entry update: %s - %s", self.start_date, self.end_date)

        users = {user.user_id: model_to_dict(user) for user in TenkfUser.objects.all()}

        self.logger.info("Fetch assignables.")
        assignables = fetch_assignables()  # TODO cache this

        self.logger.info("Fetch per date data.")
        per_date_data = fetch_per_date_data()
        dates = list(daterange(self.start_date, self.end_date))
        checksums = {k.date: k.sha256 for k in HourEntryChecksum.objects.filter(date__in=dates)}

        now = timezone.now()
        entries = []
        delete_days = set()
        updated_days = set()
        checksum_updates = []
        for date in dates:
            if date not in per_date_data:
                logger.info("No entries for %s - delete all existing entries.", date)
                delete_days.add(date)
            else:
                sha256 = per_date_data[date]["sha256"].hexdigest()
                if checksums.get(date) != sha256:
                    logger.info("Something changed for %s", date)

                    for entry in per_date_data[date]["items"]:
                        data = merge_data(entry, users, assignables)
                        project_id = assignables\
                            .get(entry["assignable_id"], {})\
                            .get("project", {})\
                            .get("id")

                        self.update_range(data["date"])

                        invoice = self.match_invoice(
                            date=data["date"],
                            project_id=project_id,
                            client=data["client"],
                            project=data["project"]
                        )

                        if not invoice:
                            logger.warning("No matching invoice available - skip entry. data=%s; entry=%s", data, entry)
                            sha256 = "-" * 64  # Reset checksum to ensure reprocessing
                        else:
                            data["invoice"] = invoice
                            data["user_m"] = self.match_user(data["user_email"])
                            hour_entry = HourEntry(**data)
                            hour_entry.update_calculated_fields()
                            entries.append(hour_entry)
                            delete_days.add(data["date"])
                            updated_days.add(data["date"])

                    checksum_updates.append({"date": date, "defaults": {"sha256": sha256}})
                else:
                    logger.info("Nothing was changed for %s - skip updating", date)

        logger.info("Processed all 10k entries. Inserting %s entries to database.", len(entries))

        # It is very important to run these operations inside a transaction to avoid non-consistent views.
        with transaction.atomic():
            logger.info("Deleting old 10k entries.")
            deleted_entries, _ = HourEntry.objects.filter(
                date__gte=self.first_entry,
                date__lte=self.last_entry,
                date__in=list(delete_days),
                last_updated_at__lt=now
            ).delete()

            logger.info("Update hour entry checksums.")
            for checksum in checksum_updates:
                HourEntryChecksum.objects.update_or_create(date=checksum["date"], defaults=checksum["defaults"])

            logger.info("All old 10k entries deleted: %s.", deleted_entries)
            # Note: this does not call .save() for entries.
            HourEntry.objects.bulk_create(entries)
            logger.info("All 10k entries added: %s.", len(entries))

        Event(
            event_type="sync_10000ft_report_hours",
            succeeded=True,
            message="Entries between {:%Y-%m-%d} and {:%Y-%m-%d}. Added {}, deleted {}; processed dates: {}.".format(
                self.start_date,
                self.end_date,
                len(entries),
                deleted_entries,
                ", ".join([day.strftime("%Y-%m-%d") for day in delete_days]))
        ).save()

        return (self.first_entry, self.last_entry, deleted_entries + len(entries))


def refresh_invoice_stats(start_date, end_date):
    if start_date and end_date:
        invoices = Invoice.objects.filter(date__gte=start_date, date__lte=end_date)
        logger.info("Updating statistics for invoices between %s and %s: %s invoices", start_date, end_date, len(invoices))
    else:
        logger.info("Updating statistics for all invoices")
        invoices = Invoice.objects.all()
    invoice_count = 0
    for invoice in invoices:
        invoice_count += 1
        entries = HourEntry.objects.exclude(status="Unsubmitted").filter(invoice=invoice).filter(incurred_hours__gt=0)
        aws_entries = None
        if invoice.project_m:
            aws_accounts = invoice.project_m.amazon_account.all()
            aws_entries = get_aws_entries(aws_accounts, invoice.month_start_date, invoice.month_end_date)
        stats = calculate_entry_stats(entries, invoice.get_fixed_invoice_rows(), aws_entries)
        for field in Invoice.STATS_FIELDS:
            setattr(invoice, field, stats[field])

        invoice.incurred_money = sum([row["incurred_money"] for row in stats["total_rows"].values() if "incurred_money" in row])
        invoice.incurred_hours = sum([row["incurred_hours"] for row in stats["total_rows"].values() if "incurred_hours" in row])
        invoice.incurred_billable_hours = stats["total_rows"]["hours"]["incurred_billable_hours"]
        if invoice.incurred_hours > 0:
            invoice.billable_percentage = invoice.incurred_billable_hours / invoice.incurred_hours
        else:
            invoice.billable_percentage = 0
        if stats["total_rows"]["hours"]["incurred_hours"] > 0:
            invoice.bill_rate_avg = stats["total_rows"]["hours"]["incurred_money"] / stats["total_rows"]["hours"]["incurred_hours"]
        else:
            invoice.bill_rate_avg = 0
        invoice.save()
        logger.debug("Updated statistics for %s", invoice)
    if start_date and end_date:
        message = f"Refreshed {invoice_count} invoices between {start_date:%Y-%m-%d} and {end_date:%Y-%m-%d}."
    else:
        message = f"Refreshed {invoice_count} invoices (without date range)."
    Event(event_type="refresh_invoice_statistics", succeeded=True, message=message).save()
