from __future__ import unicode_literals

import uuid
from django.db import models
from django.contrib.auth.models import User

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
            phases[entry.phase_name] = {"users": {}, "not_billable": not is_phase_billable(entry.phase_name)}
        if entry.user_name not in phases[entry.phase_name]["users"]:
            phases[entry.phase_name]["users"][entry.user_name] = {}
        if entry.bill_rate not in phases[entry.phase_name]["users"][entry.user_name]:
            phases[entry.phase_name]["users"][entry.user_name][entry.bill_rate] = {"incurred_hours": 0, "incurred_money": 0}
        phases[entry.phase_name]["users"][entry.user_name][entry.bill_rate]["incurred_hours"] += entry.incurred_hours
        phases[entry.phase_name]["users"][entry.user_name][entry.bill_rate]["incurred_money"] += entry.incurred_money

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
    return {
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

def is_phase_billable(phase_name):
    phase_name = phase_name.lower()

    if phase_name.startswith("non-billable") or phase_name.startswith("non billable"):
        return False
    return True


class HourEntry(models.Model):
    """ A single hour entry row.

    Note that import_csv command uses bulk_create, which does not call .save. """
    date = models.DateField()
    year = models.IntegerField()
    month = models.IntegerField()

    last_updated_at = models.DateTimeField()
    user_id = models.IntegerField()
    user_name = models.CharField(max_length=100)
    client = models.CharField(max_length=200)
    project = models.CharField(max_length=200)
    incurred_hours = models.FloatField()
    incurred_money = models.FloatField()
    category = models.CharField(max_length=100)
    notes = models.CharField(max_length=1000)
    entry_type = models.CharField(max_length=100)
    discipline = models.CharField(max_length=100)
    role = models.CharField(max_length=100)
    bill_rate = models.FloatField()
    leave_type = models.CharField(max_length=100)
    phase_name = models.CharField(max_length=100)
    billable = models.BooleanField(blank=True)
    approved = models.BooleanField(blank=True)

    def is_billable_phase(self):
        return is_phase_billable(self.phase_name)


class Invoice(models.Model):
    ISSUE_FIELDS = ("billable_incorrect_price_count", "non_billable_hours_count", "non_phase_specific_count", "not_approved_hours_count", "empty_descriptions_count")
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    year = models.IntegerField()
    month = models.IntegerField()
    client = models.CharField(max_length=100)
    project = models.CharField(max_length=100)

    billable_incorrect_price_count = models.IntegerField(null=True, blank=True)
    non_billable_hours_count = models.IntegerField(null=True, blank=True)
    non_phase_specific_count = models.IntegerField(null=True, blank=True)
    not_approved_hours_count = models.IntegerField(null=True, blank=True)
    empty_descriptions_count = models.IntegerField(null=True, blank=True)
    total_hours = models.FloatField(null=True, blank=True)
    bill_rate_avg = models.FloatField(null=True, blank=True)
    total_money = models.FloatField(null=True, blank=True)

    def total_issues(self):
        total = 0
        for field in self.ISSUE_FIELDS:
            d = getattr(self, field)
            if d is None:
                return "?"
            total += d
        return total

    def is_approved(self):
        return False
        try:
            comment = Comments.objects.filter(invoice=self).latest()
            return comment.checked
        except Comments.DoesNotExist:
            return False

    def has_comments(self):
        return False
        try:
            comment = Comments.objects.filter(invoice=self).latest()
            if comment.comments:
                return True
        except Comments.DoesNotExist:
            pass
        return False

    class Meta:
        unique_together = ("year", "month", "client", "project")
        ordering = ("-year", "-month", "client", "project")


class Comments(models.Model):
    invoice = models.ForeignKey("Invoice")
    timestamp = models.DateTimeField(auto_now_add=True)
    comments = models.TextField(null=True, blank=True)
    checked = models.NullBooleanField(blank=True, null=True)
    checked_non_billable_ok = models.NullBooleanField(blank=True, null=True)
    checked_bill_rates_ok = models.NullBooleanField(blank=True, null=True)
    checked_phases_ok = models.NullBooleanField(blank=True, null=True)
    user = models.TextField(max_length=100, null=True, blank=True)

    class Meta:
        get_latest_by = "timestamp"
