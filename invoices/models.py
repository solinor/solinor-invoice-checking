from __future__ import unicode_literals

import uuid
import time
from django.db import models
import invoices.date_utils as date_utils


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
    status = models.CharField(max_length=30)

    calculated_is_billable = models.BooleanField(blank=True, default=False, verbose_name="Billable")
    calculated_has_notes = models.BooleanField(blank=True, default=True, verbose_name="Has notes")
    calculated_has_phase = models.BooleanField(blank=True, default=True, verbose_name="Has phase")
    calculated_is_approved = models.BooleanField(blank=True, default=True, verbose_name="Is approved")
    calculated_has_proper_price = models.BooleanField(blank=True, default=True, verbose_name="Has proper price")
    calculated_has_category = models.BooleanField(blank=True, default=True, verbose_name="Has category")

    invoice = models.ForeignKey("Invoice", null=True)
    weekly_report = models.ForeignKey("WeeklyReport", null=True)
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

    def __str__(self):
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
    bill_rate_avg = models.FloatField(default=0)
    incurred_hours = models.FloatField(default=0, verbose_name="Incurred hours")
    incurred_billable_hours = models.FloatField(default=0)
    billable_percentage = models.FloatField(default=0)
    incurred_money = models.FloatField(default=0, verbose_name="Incurred money")
    invoice_state = models.CharField(max_length=1, choices=INVOICE_STATE_CHOICES, default='C')

    @property
    def month_start_date(self):
        return date_utils.month_start_date(self.year, self.month)

    @property
    def month_end_date(self):
        return date_utils.month_end_date(self.year, self.month)

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
        return u"%s - %s" % (self.full_name, self.date)

    def __str__(self):
        return u"%s - %s" % (self.full_name, self.date)

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

    def get_fixed_invoice_rows(self):
        fixed_invoice_rows = list(InvoiceFixedEntry.objects.filter(invoice=self))
        if self.invoice_state not in ("P", "S") and self.project_m:
            fixed_invoice_rows.extend(list(ProjectFixedEntry.objects.filter(project=self.project_m)))
        return fixed_invoice_rows

    class Meta:
        unique_together = ("year", "month", "client", "project")
        ordering = ("-year", "-month", "client", "project")


class WeeklyReport(models.Model):
    WEEKLY_REPORT_STATE_CHOIOCES = (
        ("C", "Created"),
        ("A", "Approved")
    )

    ISSUE_FIELDS = ("billable_incorrect_price_count", "non_billable_hours_count", "non_phase_specific_count", "not_approved_hours_count", "empty_descriptions_count")
    weekly_report_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    year = models.IntegerField()
    week = models.IntegerField()

    project_m = models.ForeignKey("Project", null=True)

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
    bill_rate_avg = models.FloatField(default=0)
    incurred_hours = models.FloatField(default=0, verbose_name="Incurred hours")
    incurred_billable_hours = models.FloatField(default=0)
    billable_percentage = models.FloatField(default=0)
    incurred_money = models.FloatField(default=0, verbose_name="Incurred money")
    weekly_report_state = models.CharField(max_length=1, choices=WEEKLY_REPORT_STATE_CHOIOCES, default='C')

    @property
    def week_start_date(self):
        return date_utils.week_start_date(self.year, self.week)

    @property
    def week_end_date(self):
        return date_utils.week_end_date(self.year, self.week)

    @property
    def processed_tags(self):
        if self.tags:
            return self.tags.split(",")
        return []

    @property
    def date(self):
        return "%s-%02d" % (self.year, self.week)

    @property
    def full_name(self):
        return "%s - %s" % (self.project_m.client, self.project_m.name)

    def __unicode__(self):
        return u"%s - %s" % (self.full_name, self.date)

    def __str__(self):
        return u"%s - %s" % (self.full_name, self.date)

    def update_state(self, comment):
        self.weekly_report_state = "C"
        if comment.checked:
            self.weekly_report_state = "A"
        return self.weekly_report_state

    def get_tags(self):
        if self.tags:
            return self.tags.split(",")

    class Meta:
        unique_together = ("year", "week", "project_m")
        ordering = ("-year", "-week", "project_m")


class SlackChannel(models.Model):
    channel_id = models.CharField(max_length=50, primary_key=True, editable=False)
    name = models.CharField(max_length=1000)
    new_project_notification = models.BooleanField(blank=True, default=False)

    def __unicode__(self):
        return self.name

    def __str__(self):
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
    amazon_account = models.ManyToManyField("AmazonLinkedAccount", blank=True)

    def __unicode__(self):
        return u"%s %s" % (self.first_name, self.last_name)

    def __str__(self):
        return "%s %s" % (self.first_name, self.last_name)


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
    enable_weekly_notifications = models.BooleanField(blank=True, default=False)
    amazon_account = models.ManyToManyField("AmazonLinkedAccount", blank=True)
    admin_users = models.ManyToManyField("FeetUser", blank=True)

    def __unicode__(self):
        return u"%s - %s" % (self.client, self.name)

    def __str__(self):
        return u"%s - %s" % (self.client, self.name)

    class Meta:
        ordering = ("client", "name")


class Phase(models.Model):
    project = models.ForeignKey("Project")
    phase_name = models.CharField(max_length=100)

    def __unicode__(self):
        return u"Phase: %s - %s" % (self.project, self.phase_name)

    def __str__(self):
        return u"Phase: %s - %s" % (self.project, self.phase_name)


class WeeklyReportComments(models.Model):
    weekly_report = models.ForeignKey("WeeklyReport")
    timestamp = models.DateTimeField(auto_now_add=True)
    checked = models.BooleanField(blank=True, default=False)
    user = models.TextField(max_length=100)

    class Meta:
        get_latest_by = "timestamp"

    def __unicode__(self):
        return u"%s - %s - %s" % (self.weekly_report, self.timestamp, self.user)

    def __str__(self):
        return u"%s - %s - %s" % (self.weekly_report, self.timestamp, self.user)


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
        if self.comments:
            return True
        return False

    class Meta:
        get_latest_by = "timestamp"

    def __unicode__(self):
        return u"%s - %s - %s" % (self.invoice, self.timestamp, self.user)

    def __str__(self):
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

    def __str__(self):
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

    def __str__(self):
        return u"%s - %s - %s" % (self.project, self.description, self.price)


class AmazonLinkedAccount(models.Model):
    linked_account_id = models.CharField(max_length=50, primary_key=True, editable=False)
    name = models.CharField(max_length=255)

    def has_linked_properties(self):
        return self.project_set.all().count() > 0 or self.feetuser_set.all().count() > 0

    def billing_for_month(self, year, month):
        account_total = self.amazoninvoicerow_set.filter(invoice_month__year=year, invoice_month__month=month).filter(record_type="AccountTotal")
        if account_total:
            return account_total[0].total_cost
        return 0

    class Meta:
        ordering = ("name", "linked_account_id")

    def __unicode__(self):
        return self.name

    def __str__(self):
        return self.name


class AmazonInvoiceRow(models.Model):
    record_id = models.CharField(max_length=50, primary_key=True, editable=False)
    record_type = models.CharField(max_length=50)
    billing_period_start = models.DateTimeField(null=True, blank=True)
    billing_period_end = models.DateTimeField(null=True, blank=True)
    invoice_date = models.DateTimeField(null=True, blank=True)
    linked_account = models.ForeignKey("AmazonLinkedAccount")
    product_code = models.CharField(max_length=255)
    usage_type = models.CharField(max_length=255)
    item_description = models.CharField(max_length=1000, null=True, blank=True)
    usage_start = models.DateTimeField(null=True, blank=True)
    usage_end = models.DateTimeField(null=True, blank=True)
    usage_quantity = models.FloatField(null=True, blank=True)
    total_cost = models.FloatField(null=True, blank=True)
    currency = models.CharField(max_length=3)
    invoice_month = models.DateField(null=True)

    def __unicode__(self):
        return u"%s - %s - %s - %s" % (self.linked_account.name, self.product_code, self.usage_type, self.total_cost)

    def __str__(self):
        return u"%s - %s - %s - %s" % (self.linked_account.name, self.product_code, self.usage_type, self.total_cost)


class DataUpdate(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    aborted = models.NullBooleanField(null=True, blank=True, default=False)

    class Meta:
        get_latest_by = "created_at"

    def __unicode__(self):
        return u"%s - %s - %s - aborted: %s" % (self.created_at, self.started_at, self.finished_at, self.aborted)

    def __str__(self):
        return u"%s - %s - %s - aborted: %s" % (self.created_at, self.started_at, self.finished_at, self.aborted)


class SlackNotification(models.Model):
    recipient = models.ForeignKey("FeetUser")
    message = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)

    def __unicode__(self):
        return u"%s - %s (%s)" % (self.recipient, self.message, self.sent_at)

    def __str__(self):
        return u"%s - %s (%s)" % (self.recipient, self.message, self.sent_at)


class SlackChat(models.Model):
    chat_id = models.CharField(max_length=50, primary_key=True, editable=False)


class SlackChatMember(models.Model):
    slack_chat = models.ForeignKey("SlackChat")
    member_id = models.CharField(max_length=50)

    class Meta:
        unique_together = (("slack_chat", "member_id"),)


def gen_auth_token():
    return "%s-%s-%s" % (time.time(), str(uuid.uuid4()), str(uuid.uuid4()))


class AuthToken(models.Model):
    token = models.CharField(max_length=100, primary_key=True, editable=False, default=gen_auth_token)
    valid_until = models.DateTimeField(null=True, blank=True)
    project = models.ForeignKey("Project")

    def __unicode__(self):
        return self.token

    def __str__(self):
        return self.token
