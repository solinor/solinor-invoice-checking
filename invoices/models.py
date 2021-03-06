from __future__ import unicode_literals

import datetime
import uuid

import reversion
from django.db import models

from invoices.utils import month_end_date, month_start_date


def is_phase_billable(phase_name, project):
    if project in ("LeaveType", "Solinor"):
        return False
    phase_name = phase_name.lower()

    if phase_name.startswith("non-billable") or phase_name.startswith("non billable"):
        return False
    return True


class Client(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class HourEntry(models.Model):
    """ A single hour entry row.

    Note that import_csv command uses bulk_create, which does not call .save. """

    STATUS_CHOICES = (
        ("Approved", "Approved"),
        ("Unsubmitted", "Unsubmitted"),
        ("Pending Approval", "Pending Approval"),
    )

    date = models.DateField(db_index=True)

    last_updated_at = models.DateTimeField(db_index=True)
    user_m = models.ForeignKey("TenkfUser", null=True, on_delete=models.CASCADE)
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
    status = models.CharField(max_length=30)
    assignable_id = models.IntegerField(null=True, blank=True)
    approved_at = models.DateField(null=True, blank=True)
    approved_by = models.CharField(max_length=255, blank=True, null=True)
    submitted_by = models.CharField(max_length=255, blank=True, null=True)

    upstream_approvable_id = models.IntegerField(null=True, blank=True)
    upstream_approvable_updated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    upstream_id = models.IntegerField(unique=True)

    calculated_is_billable = models.BooleanField(blank=True, default=False, verbose_name="Billable")
    calculated_has_notes = models.BooleanField(blank=True, default=True, verbose_name="Has notes")
    calculated_has_phase = models.BooleanField(blank=True, default=True, verbose_name="Has phase")
    calculated_is_approved = models.BooleanField(blank=True, default=True, verbose_name="Is approved")
    calculated_has_proper_price = models.BooleanField(blank=True, default=True, verbose_name="Has proper price")
    calculated_has_category = models.BooleanField(blank=True, default=True, verbose_name="Has category")
    calculated_is_overtime = models.BooleanField(blank=True, default=False, verbose_name="Is overtime")

    invoice = models.ForeignKey("Invoice", on_delete=models.CASCADE)

    def update_calculated_fields(self):
        self.calculated_is_billable = is_phase_billable(self.phase_name, self.invoice.project_m.name)
        self.calculated_has_notes = self.notes is not None and len(self.notes) > 0
        self.calculated_has_phase = self.phase_name != "[Non Phase Specific]"
        self.calculated_is_approved = self.approved
        self.calculated_has_proper_price = self.bill_rate > 50 and self.bill_rate < 170
        self.calculated_has_category = self.category != "No category" and self.category != "[none]"
        self.calculated_is_overtime = "overtime" in self.phase_name.lower()

    @property
    def can_submit_automatically(self):
        if self.calculated_has_notes and self.calculated_has_phase and self.calculated_has_category:
            if self.updated_at and self.upstream_id:
                if self.date > datetime.date.today() - datetime.timedelta(days=60):
                    return True
        return False

    def __str__(self):
        return f"{self.date} - {self.user_name} - {self.invoice.project_m.client_m.name} - {self.invoice.project_m.name} - {self.incurred_hours}h - {self.incurred_money}e"

    class Meta:
        ordering = ("date", "user_id")
        verbose_name_plural = "Hour entries"
        verbose_name = "Hour entry"


@reversion.register()
class Invoice(models.Model):
    INVOICE_STATE_CHOICES = (
        ("C", "Created"),
        ("A", "Approved"),
        ("P", "Preview"),
        ("S", "Sent"),
    )

    STATS_FIELDS = (
        "incorrect_entries_count",
        "billable_incorrect_price_count",
        "non_billable_hours_count",
        "non_phase_specific_count",
        "not_approved_hours_count",
        "empty_descriptions_count",
    )

    invoice_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    date = models.DateField()

    project_m = models.ForeignKey("Project", on_delete=models.CASCADE)

    is_approved = models.BooleanField(blank=True, default=False)
    has_comments = models.BooleanField(blank=True, default=False)
    incorrect_entries_count = models.IntegerField(default=0)
    billable_incorrect_price_count = models.IntegerField(default=0)
    non_billable_hours_count = models.IntegerField(default=0)
    non_phase_specific_count = models.IntegerField(default=0)
    not_approved_hours_count = models.IntegerField(default=0)
    no_category_count = models.IntegerField(default=0)
    empty_descriptions_count = models.IntegerField(default=0)
    bill_rate_avg = models.FloatField(default=0)
    incurred_hours = models.FloatField(default=0, verbose_name="Incurred hours")
    incurred_billable_hours = models.FloatField(default=0)
    billable_percentage = models.FloatField(default=0)
    incurred_money = models.FloatField(default=0, verbose_name="Incurred money")
    invoice_state = models.CharField(max_length=1, choices=INVOICE_STATE_CHOICES, default="C")

    @property
    def month_start_date(self):
        return month_start_date(self.date.year, self.date.month)

    @property
    def month_end_date(self):
        return month_end_date(self.date.year, self.date.month)

    @property
    def formatted_date(self):
        return f"{self.date:%Y-%m}"

    @property
    def full_name(self):
        return f"{self.project_m.client_m.name} - {self.project_m.name}"

    def __str__(self):
        return f"{self.full_name} - {self.date:%Y-%m}"

    def admin_users(self):
        return self.project_m.admin_users.all()

    def update_state(self, comment):
        self.invoice_state = "C"
        if comment.checked:
            self.invoice_state = "A"
        if comment.invoice_number:
            self.invoice_state = "P"
        if comment.invoice_sent_to_customer:
            self.invoice_state = "S"
        return self.invoice_state

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
            "hours": calc_stats("incurred_hours"),
            "bill_rate_avg": calc_stats("bill_rate_avg"),
            "money": calc_stats("incurred_money"),
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

    def save(self, *args, **kwargs):  # pylint:disable=arguments-differ
        self.date = self.date.replace(day=1)  # All invoices are dated for first day of the month, to ensure uniqueness.
        super(Invoice, self).save(*args, **kwargs)

    class Meta:
        unique_together = ("date", "project_m")
        ordering = ("-date",)


@reversion.register()
class SlackChannel(models.Model):
    channel_id = models.CharField(max_length=50, primary_key=True, editable=False)
    name = models.CharField(max_length=1000)
    new_project_notification = models.BooleanField(blank=True, default=False)
    archived = models.BooleanField(blank=True, default=False)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ("name",)


@reversion.register()
class TenkfUser(models.Model):
    guid = models.UUIDField(primary_key=True, editable=False)
    user_id = models.IntegerField(editable=False)
    first_name = models.CharField(max_length=100, null=True, blank=True)
    last_name = models.CharField(max_length=100, null=True, blank=True)
    archived = models.BooleanField(blank=True, default=False)
    display_name = models.CharField(max_length=100, null=True, blank=True)
    email = models.CharField(max_length=100, unique=True)
    billable = models.BooleanField(blank=True, default=False)
    hire_date = models.DateField(blank=True, null=True)
    termination_date = models.DateField(blank=True, null=True)
    mobile_phone = models.CharField(max_length=100, null=True, blank=True)
    invitation_pending = models.BooleanField(blank=True, default=False)
    billability_target = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    thumbnail = models.CharField(max_length=1000, null=True, blank=True)
    slack_id = models.CharField(max_length=50, null=True, blank=True)
    role = models.CharField(max_length=1000, null=True, blank=True)
    discipline = models.CharField(max_length=1000, null=True, blank=True)
    amazon_account = models.ManyToManyField("AmazonLinkedAccount", blank=True)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def __str__(self):
        return self.full_name

    class Meta:
        ordering = ("first_name", "last_name")
        verbose_name = "10000ft user"
        verbose_name_plural = "10000ft users"


@reversion.register()
class Project(models.Model):
    guid = models.UUIDField(primary_key=True, editable=False)
    project_id = models.IntegerField(unique=True)
    project_state = models.CharField(max_length=100)
    parent_id = models.IntegerField(null=True, blank=True)
    phase_name = models.CharField(max_length=1000, null=True, blank=True)
    name = models.CharField(max_length=1000)
    client_m = models.ForeignKey("Client", on_delete=models.CASCADE)
    archived = models.BooleanField(blank=True, default=False)
    created_at = models.DateTimeField()
    archived_at = models.DateTimeField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    starts_at = models.DateField(null=True, blank=True)
    ends_at = models.DateField(null=True, blank=True)
    slack_channel = models.ForeignKey("SlackChannel", null=True, blank=True, on_delete=models.CASCADE)
    amazon_account = models.ManyToManyField("AmazonLinkedAccount", blank=True)
    admin_users = models.ManyToManyField("TenkfUser", blank=True)
    thumbnail_url = models.CharField(max_length=1024, null=True, blank=True)

    @property
    def full_name(self):
        return f"{self.client_m.name} {self.name}"

    def __str__(self):
        return self.full_name

    class Meta:
        ordering = ("client_m__name", "name")


class Phase(models.Model):
    project = models.ForeignKey("Project", on_delete=models.CASCADE)
    phase_name = models.CharField(max_length=100)

    def __str__(self):
        return f"Phase: {self.project} - {self.phase_name}"


@reversion.register()
class Comments(models.Model):
    invoice = models.ForeignKey("Invoice", on_delete=models.CASCADE)
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
        if self.comments:
            return True
        return False

    class Meta:
        get_latest_by = "timestamp"
        verbose_name = "Comment"
        verbose_name_plural = "Comments"

    def __str__(self):
        return f"{self.invoice} - {self.timestamp} - {self.user}"


@reversion.register()
class InvoiceFixedEntry(models.Model):
    invoice = models.ForeignKey("Invoice", on_delete=models.CASCADE)
    price = models.FloatField()
    description = models.CharField(max_length=300)

    class Meta:
        unique_together = ("invoice", "description")
        verbose_name_plural = "Fixed invoice entries"
        verbose_name = "Fixed invoice entry"

    def __str__(self):
        return f"{self.invoice} - {self.description} - {self.price}"


@reversion.register()
class ProjectFixedEntry(models.Model):
    project = models.ForeignKey("Project", on_delete=models.CASCADE)
    price = models.FloatField()
    description = models.CharField(max_length=300)

    class Meta:
        unique_together = ("project", "description")
        verbose_name_plural = "Fixed project entries"
        verbose_name = "Fixed project entry"

    def __str__(self):
        return f"{self.project} - {self.description} - {self.price}"


@reversion.register()
class AmazonLinkedAccount(models.Model):
    linked_account_id = models.CharField(max_length=50, primary_key=True, editable=False)
    name = models.CharField(max_length=255)

    def has_linked_properties(self):
        return self.project_set.count() > 0 or self.tenkfuser_set.count() > 0

    def billing_for_month(self, year, month):
        account_total = self.amazoninvoicerow_set.filter(invoice_month__year=year, invoice_month__month=month).filter(record_type="AccountTotal")
        if account_total:
            return account_total[0].total_cost
        return 0

    class Meta:
        ordering = ("name", "linked_account_id")
        verbose_name = "Linked Amazon Account"

    def __str__(self):
        return self.name


class AmazonInvoiceRow(models.Model):
    record_id = models.CharField(max_length=50, primary_key=True, editable=False)
    record_type = models.CharField(max_length=50)
    billing_period_start = models.DateTimeField(null=True, blank=True)
    billing_period_end = models.DateTimeField(null=True, blank=True)
    invoice_date = models.DateTimeField(null=True, blank=True)
    linked_account = models.ForeignKey("AmazonLinkedAccount", on_delete=models.CASCADE)
    product_code = models.CharField(max_length=255)
    usage_type = models.CharField(max_length=255)
    item_description = models.CharField(max_length=1000)
    usage_start = models.DateTimeField(null=True, blank=True)
    usage_end = models.DateTimeField(null=True, blank=True)
    usage_quantity = models.FloatField(null=True, blank=True)
    total_cost = models.FloatField(null=True, blank=True)
    currency = models.CharField(max_length=3)
    invoice_month = models.DateField()

    def __str__(self):
        return f"{self.linked_account.name} - {self.product_code} - {self.usage_type} - {self.total_cost}"


class DataUpdate(models.Model):  # TODO: remove this - no longer required
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    aborted = models.NullBooleanField(null=True, blank=True, default=False)

    class Meta:
        get_latest_by = "created_at"

    def __str__(self):
        return f"{self.created_at} - {self.started_at} - {self.finished_at} - aborted: {self.aborted}"


class SlackNotificationBundle(models.Model):  # TODO: migrate to Event
    notification_type = models.CharField(max_length=50)
    sent_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sent_at} - {self.notification_type}"

    class Meta:
        get_latest_by = "sent_at"
        ordering = ("-sent_at", "notification_type")


class HourEntryChecksum(models.Model):
    date = models.DateField(primary_key=True)
    sha256 = models.CharField(max_length=64)


@reversion.register()
class SlackChat(models.Model):
    chat_id = models.CharField(max_length=50, primary_key=True, editable=False)


@reversion.register()
class SlackChatMember(models.Model):  # TODO: link to TenkfUser model
    slack_chat = models.ForeignKey("SlackChat", on_delete=models.CASCADE)
    member_id = models.CharField(max_length=50)

    class Meta:
        unique_together = (("slack_chat", "member_id"),)


class Event(models.Model):
    event_type = models.CharField(max_length=50)
    succeeded = models.BooleanField(blank=True, default=False)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-timestamp",)


class Permission(models.Model):

    class Meta:
        permissions = (
            ("can_run_sync", "Can manually sync data"),
            ("can_send_notifications", "Can manually trigger slack notifications"),
            ("can_see_hours_overview", "Can see hours overview"),
            ("can_see_sick_leaves", "Can see sick leaves overview"),
            ("can_see_flex_saldos", "Can see flex saldos overview"),
        )


def gen_auth_token():  # Migrations support function
    return ""
