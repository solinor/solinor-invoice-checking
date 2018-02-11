# -*- coding: utf-8 -*-

# pylint: disable=too-few-public-methods

from urllib.parse import quote as url_quote

import django_tables2 as tables
from django.contrib.humanize.templatetags.humanize import intcomma
from django.template.defaultfilters import floatformat
from django.urls import reverse
from django.utils.html import format_html

from invoices.models import HourEntry, Invoice, Project


class HourListTable(tables.Table):
    client = tables.Column(accessor="project_m.client_m.name", verbose_name="Client")
    project_m = tables.Column(accessor="project_m.name", verbose_name="Project")
    date = tables.Column(order_by=("date"), attrs={"td": {"class": "nowrap-column"}})

    class Meta:
        model = HourEntry
        attrs = {"class": "table table-striped table-hover hours-table table-responsive"}
        fields = ("date", "user_name", "client", "project_m", "phase_name", "category", "incurred_hours", "bill_rate", "incurred_money", "notes", "calculated_is_approved", "calculated_is_overtime")

    def render_user_name(self, value, record):
        if record.user_m:
            return format_html("<a href='{}'>{}</a>".format(reverse("person_month", args=[record.user_m.guid, record.date.year, record.date.month]), value))
        return value

    def render_project(self, value, record):
        if record.project_m:
            return format_html("<a href='{}'>{}</a>".format(reverse("project", args=[record.project_m.guid]), value))
        return value

    def render_incurred_hours(self, value):
        return "{}h".format(intcomma(floatformat(value, 2)))

    def render_incurred_money(self, value):
        return "{}€".format(intcomma(floatformat(value, 2)))

    def render_bill_rate(self, value):
        return "{}€/h".format(intcomma(floatformat(value, 2)))


class FrontpageInvoices(tables.Table):
    invoice_state = tables.Column(verbose_name="State")
    incorrect_entries_count = tables.Column(verbose_name="Issues")
    date = tables.Column(order_by=("date"), attrs={"td": {"class": "nowrap-column"}})
    client = tables.Column(accessor="project_m.client_m.name", verbose_name="Client")
    project_m = tables.Column(accessor="project_m.name", verbose_name="Project")
    admin_users = tables.Column(orderable=False, verbose_name="Tags")

    class Meta:
        model = Invoice
        attrs = {"class": "table table-striped table-hover invoices-table table-responsive"}
        fields = ("client", "project_m", "date", "admin_users", "invoice_state", "has_comments", "incorrect_entries_count", "incurred_hours", "bill_rate_avg", "incurred_money", "billable_percentage")

    def render_project_m(self, value, record):
        return format_html("<a href='{}?sort=-date'>{}</a>".format(reverse("project", args=[record.project_m.guid]), value))

    def render_date(self, value, record):
        return format_html("<a href='{}'>{:%Y-%m}</a>".format(reverse("invoice", args=[record.invoice_id]), value))

    def render_admin_users(self, value):
        return format_html(" ".join([f"<span class='badge badge-secondary'>{tag}</span> " for tag in value]))

    def render_incurred_hours(self, value):
        return "{}h".format(intcomma(floatformat(value, 0)))

    def render_bill_rate_avg(self, value):
        return "{}€/h".format(intcomma(floatformat(value, 0)))

    def render_incurred_money(self, value):
        return "{}€".format(intcomma(floatformat(value, 0)))

    def render_billable_percentage(self, value):
        return "{}%".format(floatformat(value * 100, 0))


class ProjectsTable(tables.Table):
    starts_at = tables.Column(order_by=("starts_at"), attrs={"td": {"class": "nowrap-column"}})
    ends_at = tables.Column(order_by=("ends_at"), attrs={"td": {"class": "nowrap-column"}})

    class Meta:
        model = Project
        attrs = {"class": "table table-striped table-hover projects-table table-responsive"}
        fields = ("client_m", "name", "admin_users", "starts_at", "ends_at", "incurred_hours", "incurred_money")

    def render_name(self, value, record):
        return format_html("<a href='{}'>{}</a>".format(reverse("project", args=[record.guid]), value))

    def render_client(self, value):
        return format_html("<a href='?client__icontains={}'>{}</a>".format(url_quote(value.encode("utf8")), value))

    def render_incurred_hours(self, value):
        return "{}h".format(intcomma(floatformat(value, 0)))

    def render_incurred_money(self, value):
        return "{}€".format(intcomma(floatformat(value, 0)))

    def render_admin_users(self, value):
        return format_html(" ".join(["<span class='badge badge-secondary'>{} {}</span>".format(a.first_name, a.last_name) for a in value.all()]))

    def render_guid(self, value):
        return format_html("<a href='{}'>Details</a>".format(reverse("project", args=[value])))


def calc_bill_rate_avg(stats):
    hours = billing = 0
    for incurred_hours, incurred_money in stats:
        hours += incurred_hours
        billing += incurred_money

    if hours == 0:
        return 0
    return billing / hours


class ProjectDetailsTable(tables.Table):
    invoice_id = tables.Column(orderable=False, verbose_name="")
    date = tables.Column(order_by=("date"), attrs={"td": {"class": "nowrap-column"}})
    incurred_hours = tables.Column(footer=lambda table: "{}h".format(intcomma(floatformat(sum(x.incurred_hours for x in table.data), 0))))
    incurred_money = tables.Column(footer=lambda table: "{}€".format(intcomma(floatformat(sum(x.incurred_money for x in table.data), 0))))
    bill_rate_avg = tables.Column(footer=lambda table: "{:.0f}€/h".format(calc_bill_rate_avg((x.incurred_hours, x.incurred_money) for x in table.data)))
    incorrect_entries_count = tables.Column(footer=lambda table: sum(x.incorrect_entries_count for x in table.data))

    class Meta:
        model = Invoice
        attrs = {"class": "table table-striped table-hover invoice-table table-responsive"}
        fields = ("date", "invoice_state", "has_comments", "incorrect_entries_count", "incurred_hours", "bill_rate_avg", "incurred_money", "billable_percentage", "invoice_id")

    def render_date(self, value):
        return format_html(f"{value:%Y-%m}")

    def render_invoice_id(self, value):
        return format_html("<a href='{}'>Invoice</a>, <a href='{}'>hours</a>".format(reverse("invoice", args=[value]), reverse("invoice_hours", args=[value])))

    def render_bill_rate_avg(self, value):
        return "{}€/h".format(intcomma(floatformat(value, 0)))

    def render_incurred_hours(self, value):
        return "{}h".format(intcomma(floatformat(value, 0)))

    def render_incurred_money(self, value):
        return "{}€".format(intcomma(floatformat(value, 0)))

    def render_billable_percentage(self, value):
        return "{}%".format(floatformat(value * 100, 0))
