from __future__ import unicode_literals

import uuid
from django.db import models


def calculate_entry_stats(entries):
    phases = {}
    billable_incorrect_price = []
    non_billable_hours = []
    non_phase_specific = []
    not_approved_hours = []
    empty_descriptions = []
    total_hours = 0
    total_money = 0

    for entry in entries:
        if entry.phase_name not in phases:
            phases[entry.phase_name] = {"users": {}, "not_billable": not is_phase_billable(entry.phase_name, entry.project)}
            phase_details = phases[entry.phase_name]
        if entry.user_name not in phase_details["users"]:
            phase_details["users"][entry.user_name] = {}
        if entry.bill_rate not in phase_details["users"][entry.user_name]:
            phase_details["users"][entry.user_name][entry.bill_rate] = {"incurred_hours": 0, "incurred_money": 0}
        phase_details["users"][entry.user_name][entry.bill_rate]["incurred_hours"] += entry.incurred_hours
        phase_details["users"][entry.user_name][entry.bill_rate]["incurred_money"] += entry.incurred_money

        if (entry.bill_rate < 50 or entry.bill_rate > 170) and entry.is_billable_phase():
            billable_incorrect_price.append(entry)

        if not entry.is_billable_phase():
            non_billable_hours.append(entry)
        else:
            total_money += entry.incurred_money
        total_hours += entry.incurred_hours
        if entry.phase_name == "[Non Phase Specific]":
            non_phase_specific.append(entry)
        if not entry.approved:
            not_approved_hours.append(entry)
        if entry.notes is None or len(entry.notes) < 3:
            empty_descriptions.append(entry)

    if total_hours > 0:
        bill_rate_avg = total_money / total_hours
    else:
        bill_rate_avg = 0
    stats = {
        "phases": phases,
        "billable_incorrect_price": billable_incorrect_price,
        "non_billable_hours": non_billable_hours,
        "total_hours": total_hours,
        "total_money": total_money,
        "non_phase_specific": non_phase_specific,
        "billable_incorrect_price_count": len(billable_incorrect_price),
        "non_billable_hours_count": len(non_billable_hours),
        "non_phase_specific_count": len(non_phase_specific),
        "not_approved_hours": not_approved_hours,
        "not_approved_hours_count": len(not_approved_hours),
        "empty_descriptions": empty_descriptions,
        "empty_descriptions_count": len(empty_descriptions),
        "bill_rate_avg": bill_rate_avg,
    }
    stats["incorrect_entries_count"] = stats["billable_incorrect_price_count"] + stats["non_billable_hours_count"] + stats["non_phase_specific_count"] + stats["not_approved_hours_count"] + stats["empty_descriptions_count"]
    return stats

def is_phase_billable(phase_name, project):
    if project == "[Leave Type]":
        return False
    phase_name = phase_name.lower()

    if phase_name.startswith("non-billable") or phase_name.startswith("non billable"):
        return False
    return True


class HourEntry(models.Model):
    """ A single hour entry row.

    Note that import_csv command uses bulk_create, which does not call .save. """
    date = models.DateField()

    last_updated_at = models.DateTimeField()
    user_id = models.IntegerField()
    user_email = models.CharField(max_length=255)
    user_name = models.CharField(max_length=100)
    client = models.CharField(max_length=200)
    project = models.CharField(max_length=200)
    incurred_hours = models.FloatField()
    incurred_money = models.FloatField()
    category = models.CharField(max_length=100)
    notes = models.CharField(max_length=1000, null=True)
    entry_type = models.CharField(max_length=100)
    discipline = models.CharField(max_length=100)
    role = models.CharField(max_length=100)
    bill_rate = models.FloatField()
    leave_type = models.CharField(max_length=100)
    phase_name = models.CharField(max_length=100)
    billable = models.BooleanField(blank=True)
    approved = models.BooleanField(blank=True)
    project_tags = models.CharField(max_length=1024, null=True, blank=True)

    calculated_is_billable = models.BooleanField(blank=True, default=False)
    invoice = models.ForeignKey("Invoice", null=True)
    project_m = models.ForeignKey("Project", null=True)

    def is_billable_phase(self):
        return is_phase_billable(self.phase_name, self.project)

    def __unicode__(self):
        return u"%s - %s - %s - %s - %sh - %se" % (self.date, self.user_name, self.client, self.project, self.incurred_hours, self.incurred_money)

    class Meta:
        ordering = ("date", "user_id")

class Invoice(models.Model):
    CHOICES = (
        (None, "Unknown"),
        (True, "Yes"),
        (False, "No"),
    )

    INVOICE_STATE_CHOICES = (
        ("C", "Created"),
        ("A", "Approved"),
        ("P", "Preview"),
        ("S", "Sent"),
    )

    ISSUE_FIELDS = ("billable_incorrect_price_count", "non_billable_hours_count", "non_phase_specific_count", "not_approved_hours_count", "empty_descriptions_count")
    invoice_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    year = models.IntegerField()
    month = models.IntegerField()

    project_m = models.ForeignKey("Project", null=True)
    user = models.ForeignKey("FeetUser", null=True)

    client = models.CharField(max_length=100)
    project = models.CharField(max_length=100)
    tags = models.CharField(max_length=1024, null=True, blank=True)

    is_approved = models.NullBooleanField(null=True, blank=True, default=False, choices=CHOICES)
    has_comments = models.NullBooleanField(null=True, blank=True, default=False, choices=CHOICES)
    incorrect_entries_count = models.IntegerField(null=True, blank=True)
    billable_incorrect_price_count = models.IntegerField(null=True, blank=True)
    non_billable_hours_count = models.IntegerField(null=True, blank=True)
    non_phase_specific_count = models.IntegerField(null=True, blank=True)
    not_approved_hours_count = models.IntegerField(null=True, blank=True)
    empty_descriptions_count = models.IntegerField(null=True, blank=True)
    total_hours = models.FloatField(null=True, blank=True)
    bill_rate_avg = models.FloatField(null=True, blank=True)
    total_money = models.FloatField(null=True, blank=True)
    invoice_state = models.CharField(max_length=1, choices=INVOICE_STATE_CHOICES, default='C')

    def __unicode__(self):
        return u"%s %s - %s-%s" % (self.client, self.project, self.year, self.month)

    def update_state(self, comment):
        self.invoice_state = "C"
        if comment.checked:
            self.invoice_state = "A"
        if comment.invoice_number:
            self.invoice_state = "P"
        if comment.invoice_sent_to_customer:
            self.invoice_state = "S"
        return self.invoice_state

    def get_tags(self):
        if self.tags:
            return self.tags.split(",")

    def compare(self, other):
        def calc_stats(field_name):
            field_value = getattr(self, field_name)
            other_field_value = getattr(other, field_name)
            diff = (other_field_value or 0) - (field_value or 0)
            if not field_value:
                percentage = None
            else:
                percentage = diff / field_value * 100
            return {"diff": diff, "percentage": percentage, "this_value": field_value, "other_value": other_field_value}

        data = {
            "hours": calc_stats("total_hours"),
            "bill_rate_avg": calc_stats("bill_rate_avg"),
            "money": calc_stats("total_money"),
        }
        if abs(data["hours"]["diff"]) > 10 and (not data["hours"]["percentage"] or abs(data["hours"]["percentage"]) > 25):
            data["remarkable"] = True
        if abs(data["bill_rate_avg"]["diff"]) > 5 and data["bill_rate_avg"]["this_value"] > 0 and data["bill_rate_avg"]["other_value"] > 0:
            data["remarkable"] = True
        if abs(data["money"]["diff"]) > 2000 and (not data["money"]["percentage"] or abs(data["money"]["percentage"]) > 25):
            data["remarkable"] = True
        return data

    class Meta:
        unique_together = ("year", "month", "client", "project")
        ordering = ("-year", "-month", "client", "project")


class FeetUser(models.Model):
    guid = models.UUIDField(primary_key=True, editable=False)
    user_id = models.IntegerField(editable=False)
    first_name = models.CharField(max_length=100, null=True, blank=True)
    last_name = models.CharField(max_length=100, null=True, blank=True)
    archived = models.BooleanField(blank=True, default=False)
    display_name = models.CharField(max_length=100, null=True, blank=True)
    email = models.CharField(max_length=100, null=True, blank=True)
    billable = models.BooleanField(blank=True, default=False)
    hire_date = models.DateField(blank=True, null=True)
    termination_date = models.DateField(blank=True, null=True)
    mobile_phone = models.CharField(max_length=100, null=True, blank=True)
    invitation_pending = models.BooleanField(blank=True, default=False)
    billability_target = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField()
    archived_at = models.DateTimeField(null=True, blank=True)
    thumbnail = models.CharField(max_length=1000, null=True, blank=True)


class Project(models.Model):
    guid = models.UUIDField(primary_key=True, editable=False)
    project_id = models.IntegerField(null=True, blank=True)
    project_state = models.CharField(max_length=100)
    parent_id = models.IntegerField(null=True, blank=True)
    phase_name = models.CharField(max_length=1000, null=True, blank=True)
    name = models.CharField(max_length=1000)
    client = models.CharField(max_length=1000)
    archived = models.BooleanField(blank=True, default=False)
    created_at = models.DateTimeField()
    archived_at = models.DateTimeField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    starts_at = models.DateField(null=True, blank=True)
    ends_at = models.DateField(null=True, blank=True)

    def __unicode__(self):
        return u"%s - %s" % (self.client, self.name)


class Comments(models.Model):
    invoice = models.ForeignKey("Invoice")
    timestamp = models.DateTimeField(auto_now_add=True)
    comments = models.TextField(null=True, blank=True)
    checked = models.NullBooleanField(blank=True, null=True, default=False)
    checked_non_billable_ok = models.NullBooleanField(blank=True, null=True, default=False)
    checked_bill_rates_ok = models.NullBooleanField(blank=True, null=True, default=False)
    checked_phases_ok = models.NullBooleanField(blank=True, null=True, default=False)
    checked_changes_last_month = models.NullBooleanField(blank=True, null=True, default=False)
    user = models.TextField(max_length=100)

    invoice_number = models.CharField(max_length=100, null=True, blank=True)
    invoice_sent_to_customer = models.BooleanField(blank=True, default=False)

    def has_comments(self):
        if self.comments and len(self.comments) > 0:
            return True
        return False

    class Meta:
        get_latest_by = "timestamp"

    def __unicode__(self):
        return u"%s - %s - %s" % (self.invoice, self.timestamp, self.user)


class DataUpdate(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    aborted = models.NullBooleanField(null=True, blank=True, default=False)

    class Meta:
        get_latest_by = "created_at"

    def __unicode__(self):
        return u"%s - %s - %s - aborted: %s" % (self.created_at, self.started_at, self.finished_at, self.aborted)
