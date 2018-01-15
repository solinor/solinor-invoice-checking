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
    class Meta:
        model = HourEntry
        attrs = {"class": "table table-striped table-hover hours-table"}
        fields = ("date", "user_name", "client", "project", "phase_name", "category", "incurred_hours", "bill_rate", "incurred_money", "notes", "calculated_is_billable", "calculated_has_notes", "calculated_has_phase", "calculated_is_approved", "calculated_has_proper_price", "calculated_has_category", "calculated_is_overtime")

    def render_user_name(self, value, record):
        if record.user_m:
            return format_html("<a href='%s'>%s</a>" % (reverse("person_month", args=[record.user_m.guid, record.date.year, record.date.month]), value))
        return value

    def render_project(self, value, record):
        if record.project_m:
            return format_html("<a href='%s'>%s</a>" % (reverse("project", args=[record.project_m.guid]), value))
        return value

    def render_incurred_hours(self, value):
        return u"%sh" % intcomma(floatformat(value, 2))

    def render_incurred_money(self, value):
        return u"%s€" % intcomma(floatformat(value, 2))

    def render_bill_rate(self, value):
        return u"%s€/h" % intcomma(floatformat(value, 2))


class FrontpageInvoices(tables.Table):
    invoice_state = tables.Column(verbose_name="State")
    incorrect_entries_count = tables.Column(verbose_name="Issues")
    date = tables.Column(order_by=("year", "month"))
    full_name = tables.Column(order_by=("client", "project"), verbose_name="Name")
    processed_tags = tables.Column(order_by=("tags"), verbose_name="Tags")

    class Meta:
        model = Invoice
        attrs = {"class": "table table-striped table-hover invoices-table"}
        fields = ("full_name", "date", "processed_tags", "invoice_state", "has_comments", "incorrect_entries_count", "incurred_hours", "bill_rate_avg", "incurred_money", "billable_percentage")

    def render_full_name(self, value, record):
        return format_html("<a href='%s'>%s</a>" % (reverse("invoice", args=[record.invoice_id]), value))

    def render_processed_tags(self, value):
        return format_html(" ".join(["<span class='label label-default'>%s</span> " % tag for tag in value]))

    def render_incurred_hours(self, value):
        return u"%sh" % intcomma(floatformat(value, 0))

    def render_bill_rate_avg(self, value):
        return u"%s€/h" % intcomma(floatformat(value, 0))

    def render_incurred_money(self, value):
        return u"%s€" % intcomma(floatformat(value, 0))

    def render_billable_percentage(self, value):
        return u"%s%%" % floatformat(value * 100, 0)


class ProjectsTable(tables.Table):
    class Meta:
        model = Project
        attrs = {"class": "table table-striped table-hover projects-table"}
        fields = ("client", "name", "admin_users", "starts_at", "ends_at", "incurred_hours", "incurred_money")

    def render_name(self, value, record):
        return format_html(u"<a href='%s'>%s</a>" % (reverse("project", args=[record.guid]), value))

    def render_client(self, value):
        return format_html(u"<a href='?client__icontains=%s'>%s</a>" % (url_quote(value.encode("utf8")), value))

    def render_incurred_hours(self, value):
        return u"%sh" % intcomma(floatformat(value, 0))

    def render_incurred_money(self, value):
        return u"%s€" % intcomma(floatformat(value, 0))

    def render_admin_users(self, value):
        return format_html(u" ".join([u"<span class='label label-default'>%s %s</span>" % (a.first_name, a.last_name) for a in value.all()]))

    def render_guid(self, value):
        return format_html(u"<a href='%s'>Details</a>" % reverse("project", args=[value]))


class ProjectDetailsTable(tables.Table):
    invoice_id = tables.Column(orderable=False, verbose_name="")
    date = tables.Column(order_by=("year", "month"))

    class Meta:
        model = Invoice
        attrs = {"class": "table table-striped table-hover invoice-table"}
        fields = ("date", "invoice_state", "has_comments", "incorrect_entries_count", "incurred_hours", "bill_rate_avg", "incurred_money", "billable_percentage", "invoice_id")

    def render_invoice_id(self, value):
        return format_html("<a href='%s'>Invoice</a>, <a href='%s'>hours</a>" % (reverse("invoice", args=[value]), reverse("invoice_hours", args=[value])))

    def render_bill_rate_avg(self, value):
        return u"%s€/h" % intcomma(floatformat(value, 2))

    def render_incurred_hours(self, value):
        return u"%sh" % intcomma(floatformat(value, 0))

    def render_incurred_money(self, value):
        return u"%s€" % intcomma(floatformat(value, 0))

    def render_billable_percentage(self, value):
        return u"%s%%" % floatformat(value * 100, 0)
