from __future__ import unicode_literals

import calendar
import datetime
import uuid
import time
from django.db import models


def calculate_entry_stats(entries, fixed_invoice_rows, aws_entries=None):
    phases = {}
    billable_incorrect_price = []
    non_billable_hours = []
    non_phase_specific = []
    no_category = []
    not_approved_hours = []
    empty_descriptions = []
    total_rows = {"hours": {"description": "Hour markings", "incurred_hours": 0, "incurred_money": 0, "bill_rate_avg": None, "currency": "EUR" }}
    total_entries = 0

    for entry in entries:
        total_entries += 1
        phase_name = "%s - %s" % (entry.phase_name, entry.bill_rate)
        if phase_name not in phases:
            phases[phase_name] = {"users": {}, "billable": entry.calculated_is_billable, "incurred_hours": 0, "incurred_money": 0}
        phase_details = phases[phase_name]
        if entry.user_email not in phase_details["users"]:
            phase_details["users"][entry.user_email] = {"user_email": entry.user_email, "user_name": entry.user_name, "user_m": entry.user_m, "entries": {}}
        if entry.bill_rate not in phase_details["users"][entry.user_email]["entries"]:
            phase_details["users"][entry.user_email]["entries"][entry.bill_rate] = {"incurred_hours": 0, "incurred_money": 0}
        phase_details["users"][entry.user_email]["entries"][entry.bill_rate]["incurred_hours"] += entry.incurred_hours
        phase_details["users"][entry.user_email]["entries"][entry.bill_rate]["incurred_money"] += entry.incurred_money

        if not entry.calculated_has_proper_price and entry.calculated_is_billable:
            billable_incorrect_price.append(entry)

        if entry.calculated_is_billable:
            total_rows["hours"]["incurred_money"] += entry.incurred_money
            phase_details["incurred_money"] += entry.incurred_money
        else:
            non_billable_hours.append(entry)
        total_rows["hours"]["incurred_hours"] += entry.incurred_hours
        phase_details["incurred_hours"] += entry.incurred_hours
        if not entry.calculated_has_phase:
            non_phase_specific.append(entry)
        if not entry.calculated_is_approved:
            not_approved_hours.append(entry)
        if not entry.calculated_has_notes:
            empty_descriptions.append(entry)
        if not entry.calculated_has_category:
            no_category.append(entry)

    if total_rows["hours"]["incurred_hours"] > 0:
        total_rows["hours"]["bill_rate_avg"] = total_rows["hours"]["incurred_money"] / total_rows["hours"]["incurred_hours"]
    if len(fixed_invoice_rows) > 0:
        total_rows["fixed"] = {"description": "Fixed rows", "incurred_money": 0}
        phases["Fixed"] = {"entries": {}, "billable": True}
        for item in fixed_invoice_rows:
            phases["Fixed"]["entries"][item.description] = {"price": item.price, "currency": "EUR"}
            total_rows["fixed"]["incurred_money"] += item.price

    if aws_entries and len(aws_entries):
        for aws_account, aws_entries in aws_entries.items():
            account_key = "AWS: %s" % aws_account
            phases[account_key] = {"entries": {}, "billable": True}
            for aws_entry in aws_entries:
                if aws_entry.record_type == "AccountTotal":
                    total_key = "aws_%s" % aws_entry.currency
                    if total_key not in total_rows:
                        total_rows[total_key] = {"description": "Amazon billing (%s)" % aws_entry.currency, "incurred_money": 0, "currency": aws_entry.currency}

                    total_rows[total_key]["incurred_money"] += aws_entry.total_cost
                    phases[account_key]["entries"]["Amazon Web Services billing"] = {"price": aws_entry.total_cost, "currency": aws_entry.currency}
                    break
            else:
                phases[account_key]["entries"]["Amazon Web Services billing"] = {"price": 0, "currency": "USD"}

    stats = {
        "total_rows": total_rows,
        "phases": phases,
        "billable_incorrect_price": billable_incorrect_price,
        "non_billable_hours": non_billable_hours,
        "non_phase_specific": non_phase_specific,
        "billable_incorrect_price_count": len(billable_incorrect_price),
        "non_billable_hours_count": len(non_billable_hours),
        "non_phase_specific_count": len(non_phase_specific),
        "not_approved_hours": not_approved_hours,
        "not_approved_hours_count": len(not_approved_hours),
        "empty_descriptions": empty_descriptions,
        "empty_descriptions_count": len(empty_descriptions),
        "no_category": no_category,
        "no_category_count": len(no_category),
        "total_entries": total_entries,
    }
    stats["incorrect_entries_count"] = stats["billable_incorrect_price_count"] + stats["non_billable_hours_count"] + stats["non_phase_specific_count"] + stats["not_approved_hours_count"] + stats["empty_descriptions_count"] + stats["no_category_count"]
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
    date = models.DateField(db_index=True)

    last_updated_at = models.DateTimeField(db_index=True)
    user_m = models.ForeignKey("FeetUser", null=True)
    user_id = models.IntegerField()
    user_email = models.CharField(max_length=255)
    user_name = models.CharField(max_length=100, verbose_name="Name")
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

    calculated_is_billable = models.BooleanField(blank=True, default=False, verbose_name="Billable")
    calculated_has_notes = models.BooleanField(blank=True, default=True, verbose_name="Has notes")
    calculated_has_phase = models.BooleanField(blank=True, default=True, verbose_name="Has phase")
    calculated_is_approved = models.BooleanField(blank=True, default=True, verbose_name="Is approved")
    calculated_has_proper_price = models.BooleanField(blank=True, default=True, verbose_name="Has proper price")
    calculated_has_category = models.BooleanField(blank=True, default=True, verbose_name="Has category")

    invoice = models.ForeignKey("Invoice", null=True)
    project_m = models.ForeignKey("Project", null=True)

    def update_calculated_fields(self):
        self.calculated_is_billable = is_phase_billable(self.phase_name, self.project)
        if self.notes:
            self.calculated_has_notes = len(self.notes) > 0
        else:
            self.calculated_has_notes = False
        self.calculated_has_phase = self.phase_name != "[Non Phase Specific]"
        self.calculated_is_approved = self.approved
        self.calculated_has_proper_price = self.bill_rate > 50 and self.bill_rate < 170
        self.calculated_has_category = self.category != "No category" and self.category != "[none]"

    def __unicode__(self):
        return u"%s - %s - %s - %s - %sh - %se" % (self.date, self.user_name, self.client, self.project, self.incurred_hours, self.incurred_money)

    class Meta:
        ordering = ("date", "user_id")
        verbose_name_plural = "Hour entries"

class Invoice(models.Model):
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

    client = models.CharField(max_length=100)
    project = models.CharField(max_length=100)
    tags = models.CharField(max_length=1024, null=True, blank=True)

    is_approved = models.BooleanField(blank=True, default=False)
    has_comments = models.BooleanField(blank=True, default=False)
    incorrect_entries_count = models.IntegerField(default=0)
    billable_incorrect_price_count = models.IntegerField(default=0)
    non_billable_hours_count = models.IntegerField(default=0)
    non_phase_specific_count = models.IntegerField(default=0)
    not_approved_hours_count = models.IntegerField(default=0)
    no_category_count = models.IntegerField(default=0)
    empty_descriptions_count = models.IntegerField(default=0)
    total_hours = models.FloatField(default=0, verbose_name="Incurred hours")
    bill_rate_avg = models.FloatField(default=0)
    total_money = models.FloatField(default=0, verbose_name="Incurred money")
    invoice_state = models.CharField(max_length=1, choices=INVOICE_STATE_CHOICES, default='C')

    @property
    def month_start_date(self):
        return datetime.date(self.year, self.month, 1)

    @property
    def month_end_date(self):
        return self.month_start_date.replace(day=calendar.monthrange(self.year, self.month)[1])


    @property
    def processed_tags(self):
        if self.tags:
            return self.tags.split(",")
        return []

    @property
    def date(self):
        return "%s-%02d" % (self.year, self.month)

    @property
    def full_name(self):
        return "%s - %s" % (self.client, self.project)

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

    def get_fixed_invoice_rows(self):
        fixed_invoice_rows = list(InvoiceFixedEntry.objects.filter(invoice=self))
        if self.invoice_state not in ("P", "S") and self.project_m:
            fixed_invoice_rows.extend(list(ProjectFixedEntry.objects.filter(project=self.project_m)))
        return fixed_invoice_rows

    class Meta:
        unique_together = ("year", "month", "client", "project")
        ordering = ("-year", "-month", "client", "project")


class SlackChannel(models.Model):
    channel_id = models.CharField(max_length=50, primary_key=True, editable=False)
    name = models.CharField(max_length=1000)
    new_project_notification = models.BooleanField(blank=True, default=False)

    def __unicode__(self):
        return self.name

    class Meta:
        ordering = ("name",)


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
    slack_id = models.CharField(max_length=50, null=True, blank=True)


class Project(models.Model):
    guid = models.UUIDField(primary_key=True, editable=False)
    project_id = models.IntegerField(null=True, blank=True)
    project_state = models.CharField(max_length=100)
    parent_id = models.IntegerField(null=True, blank=True)
    phase_name = models.CharField(max_length=1000, null=True, blank=True)
    name = models.CharField(max_length=1000)
    client = models.CharField(max_length=1000, null=True)
    archived = models.BooleanField(blank=True, default=False)
    created_at = models.DateTimeField()
    archived_at = models.DateTimeField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    starts_at = models.DateField(null=True, blank=True)
    ends_at = models.DateField(null=True, blank=True)
    slack_channel = models.ForeignKey("SlackChannel", null=True, blank=True)
    amazon_account = models.ManyToManyField("AmazonLinkedAccount", blank=True)

    def __unicode__(self):
        return u"%s - %s" % (self.client, self.name)

    class Meta:
        ordering = ("client", "name")


class Comments(models.Model):
    invoice = models.ForeignKey("Invoice")
    timestamp = models.DateTimeField(auto_now_add=True)
    comments = models.TextField(null=True, blank=True)
    checked = models.BooleanField(blank=True, default=False)
    checked_non_billable_ok = models.BooleanField(blank=True, default=False)
    checked_bill_rates_ok = models.BooleanField(blank=True, default=False)
    checked_phases_ok = models.BooleanField(blank=True, default=False)
    checked_no_category_ok = models.BooleanField(blank=True, default=False)
    checked_changes_last_month = models.BooleanField(blank=True, default=False)
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


class InvoiceFixedEntry(models.Model):
    invoice = models.ForeignKey("Invoice")
    price = models.FloatField()
    description = models.CharField(max_length=300)

    class Meta:
        unique_together = ("invoice", "description")
        verbose_name_plural = "Fixed invoice entries"
        verbose_name = "Fixed invoice entry"

    def __unicode__(self):
        return u"%s - %s - %s" % (self.invoice, self.description, self.price)


class ProjectFixedEntry(models.Model):
    project = models.ForeignKey("Project")
    price = models.FloatField()
    description = models.CharField(max_length=300)

    class Meta:
        unique_together = ("project", "description")
        verbose_name_plural = "Fixed project entries"
        verbose_name = "Fixed project entry"

    def __unicode__(self):
        return u"%s - %s - %s" % (self.project, self.description, self.price)


"""
"InvoiceID","PayerAccountId","LinkedAccountId","RecordType","RecordID","BillingPeriodStartDate","BillingPeriodEndDate","InvoiceDate","PayerAccountName","LinkedAccountName","TaxationAddress","PayerPONumber","ProductCode","ProductName","SellerOfRecord","UsageType","Operation","RateId","ItemDescription","UsageStartDate","UsageEndDate","UsageQuantity","BlendedRate","CurrencyCode","CostBeforeTax","Credits","TaxAmount","TaxType","TotalCost"

"Estimated","321914701408","908774477202","LinkedLineItem","3600000000614116491","2017/05/01 00:00:00","2017/05/31 23:59:59","2017/05/12 14:04:18","Hostmaster","Olli Jarva","Teollisuuskatu 21, Helsinki, Uusimaa, 00510, FI","","AmazonS3","Amazon Simple Storage Service","Amazon Web Services, Inc.","EU-TimedStorage-ByteHrs","","23712747","$0.023 per GB - first 50 TB / month of storage used","2017/05/01 00:00:00","2017/05/31 23:59:59","4.20741252","0.022999884","USD","0.096770","0.0","0.000000","None","0.096770"

"","321914701408","908774477202","AccountTotal","AccountTotal:908774477202","2017/05/01 00:00:00","2017/05/31 23:59:59","","Hostmaster","Olli Jarva","","","","","","","","","Total for linked account# 908774477202 (Olli Jarva)","","","","","USD","197.710480","0.0","0.000000","","197.710480"

"""


class AmazonLinkedAccount(models.Model):
    linked_account_id = models.CharField(max_length=50, primary_key=True, editable=False)
    name = models.CharField(max_length=255)

    class Meta:
        ordering = ("name", "linked_account_id")

    def __unicode__(self):
        return self.name


class AmazonInvoiceRow(models.Model):
    record_id = models.CharField(max_length=50, primary_key=True, editable=False)
    record_type = models.CharField(max_length=50)
    billing_period_start = models.DateTimeField()
    billing_period_end = models.DateTimeField()
    invoice_date = models.DateTimeField(null=True, blank=True)
    linked_account = models.ForeignKey("AmazonLinkedAccount")
    product_code = models.CharField(max_length=255)
    usage_type = models.CharField(max_length=255)
    item_description = models.CharField(max_length=1000, null=True, blank=True)
    usage_start = models.DateTimeField(null=True, blank=True)
    usage_end = models.DateTimeField(null=True, blank=True)
    usage_quantity = models.FloatField(null=True, blank=True)
    total_cost = models.FloatField()
    currency = models.CharField(max_length=3)


class DataUpdate(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    aborted = models.NullBooleanField(null=True, blank=True, default=False)

    class Meta:
        get_latest_by = "created_at"

    def __unicode__(self):
        return u"%s - %s - %s - aborted: %s" % (self.created_at, self.started_at, self.finished_at, self.aborted)

def gen_auth_token():
    return "%s-%s-%s" % (time.time(), str(uuid.uuid4()), str(uuid.uuid4()))


class AuthToken(models.Model):
    token = models.CharField(max_length=100, primary_key=True, editable=False, default=gen_auth_token)
    valid_until = models.DateTimeField(null=True, blank=True)
    project = models.ForeignKey("Project")

    def __unicode__(self):
        return self.token
