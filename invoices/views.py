# -*- coding: utf-8 -*-

import copy
import datetime
import json
from collections import defaultdict

import redis
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django_tables2 import RequestConfig

import invoices.date_utils as date_utils
from flex_hours.utils import sync_public_holidays
from invoices.chart_utils import gen_treemap_data_projects, gen_treemap_data_users
from invoices.file_gen_utils import generate_hours_pdf_for_invoice, generate_hours_xls_for_invoice
from invoices.filters import HourListFilter, InvoiceFilter, ProjectsFilter
from invoices.invoice_utils import calculate_entry_stats, generate_amazon_invoice_data, get_aws_entries
from invoices.models import (AmazonInvoiceRow, AmazonLinkedAccount, Comments, DataUpdate, Event, HourEntry, Invoice,
                             InvoiceFixedEntry, Project, ProjectFixedEntry, SlackNotificationBundle, TenkfUser)
from invoices.slack import refresh_slack_channels, refresh_slack_users
from invoices.tables import FrontpageInvoices, HourListTable, ProjectDetailsTable, ProjectsTable
from invoices.tenkfeet_api import TenkFeetApi
from invoices.utils import sync_10000ft_projects, sync_10000ft_users

REDIS = redis.from_url(settings.REDIS)


def handler404(request):
    response = render(request, "404.html")
    response.status_code = 404
    return response


def handler500(request):
    response = render(request, "500.html")
    response.status_code = 500
    return response


@login_required
def search(request):
    q = request.GET.get("q")
    if not q:
        return render(request, "search.html")

    users = TenkfUser.objects.filter(archived=False).filter(Q(email__icontains=q) | Q(display_name__icontains=q))
    projects = Project.objects.filter(Q(name__icontains=q) | Q(client__icontains=q))
    if len(users) == 1 and len(projects) == 0:
        return HttpResponseRedirect(reverse("person_details", args=(users[0].guid,)))
    elif len(projects) == 1:
        return HttpResponseRedirect(reverse("project", args=(projects[0].guid,)))
    return render(request, "search.html", {"q": q, "users": users, "projects": projects})


@login_required
def amazon_overview(request):
    # TODO: this is really inefficient, as it is making a separate DB query for every single Amazon account
    if request.GET.get("year") and request.GET.get("month"):
        try:
            today = datetime.datetime(int(request.GET.get("year")), int(request.GET.get("month")), 1)
        except ValueError:
            return HttpResponseBadRequest("Invalid year or month")
    else:
        today = datetime.date.today()
    aws_accounts = AmazonLinkedAccount.objects.prefetch_related("project_set", "tenkfuser_set")
    linked_accounts = sum([aws_account.has_linked_properties() for aws_account in aws_accounts])
    total_billing = linked_billing = unlinked_billing = employee_billing = project_billing = 0

    for aws_account in aws_accounts:
        aws_account.billing = aws_account.billing_for_month(today.year, today.month)
        total_billing += aws_account.billing

        if aws_account.has_linked_properties():
            linked_billing += aws_account.billing
            if aws_account.project_set.count() > 0:
                project_billing += aws_account.billing
            if aws_account.tenkfuser_set.count() > 0:
                employee_billing += aws_account.billing
        else:
            unlinked_billing += aws_account.billing
    billing_data = (
        ("Type", "USD"),
        ("Project billing", project_billing),
        ("Employee billing", employee_billing),
        ("Unaccounted billing", unlinked_billing),
    )
    linking_data = (
        ("a", "b"),
        ("Linked accounts", linked_accounts),
        ("Unlinked accounts", AmazonLinkedAccount.objects.count() - linked_accounts),
    )
    months = AmazonInvoiceRow.objects.dates("invoice_month", "month", order="DESC")
    context = {
        "today": today,
        "months": months,
        "aws_accounts": aws_accounts,
        "billing_data_json": json.dumps(billing_data),
        "linking_data_json": json.dumps(linking_data),
    }
    return render(request, "amazon_overview.html", context)


@login_required
def amazon_invoice(request, linked_account_id, year, month):
    year = int(year)
    month = int(month)
    linked_account = get_object_or_404(AmazonLinkedAccount, linked_account_id=linked_account_id)
    invoice_rows = AmazonInvoiceRow.objects.filter(linked_account=linked_account).filter(invoice_month__year=year, invoice_month__month=month)
    invoice_data = generate_amazon_invoice_data(invoice_rows)
    months = AmazonInvoiceRow.objects.filter(linked_account=linked_account).dates("invoice_month", "month", order="DESC")
    linked_projects = linked_account.project_set.all()
    linked_users = linked_account.tenkfuser_set.all()
    context = {"year": year, "month": month, "months": months, "linked_account": linked_account, "linked_users": linked_users, "linked_projects": linked_projects}
    context.update(invoice_data)

    return render(request, "amazon_invoice.html", context)


@login_required
def hours_browser(request):
    if not request.GET:
        today = datetime.date.today()
        month_start_date = date_utils.month_start_date(today.year, today.month)
        month_end_date = date_utils.month_end_date(today.year, today.month)
        return HttpResponseRedirect("{}?date__gte={}&date__lte={}".format(reverse("hours_browser"), month_start_date, month_end_date))
    hours = HourEntry.objects.filter(incurred_hours__gt=0).exclude(project="[Leave Type]").select_related("user_m", "project_m")
    filters = HourListFilter(request.GET, queryset=hours)
    table = HourListTable(filters.qs)
    RequestConfig(request, paginate={
        "per_page": 250
    }).configure(table)

    context = {
        "table": table,
        "filters": filters,
    }

    return render(request, "all_hours.html", context=context)


@login_required
def person_details(request, user_guid):
    person = get_object_or_404(TenkfUser, guid=user_guid)
    year_ago = (datetime.date.today() - datetime.timedelta(days=365)).replace(day=1, month=1)
    entries = person.hourentry_set
    filters = request.GET.get("filters", "").split(",")
    if "exclude_leaves" in filters:
        entries = entries.exclude(client="[none]")
    if "exclude_nonbillable" in filters:
        entries = entries.exclude(calculated_is_billable=False)

    entries = entries.filter(date__gte=year_ago).order_by("date").values("date").annotate(hours=Sum("incurred_hours")).annotate(money=Sum("incurred_money"))

    calendar_charts = []
    hours_calendar_data = [(entry["date"].year, entry["date"].month - 1, entry["date"].day, entry["hours"], "{:.2f}h".format(entry["hours"])) for entry in entries]
    money_calendar_data = [(entry["date"].year, entry["date"].month - 1, entry["date"].day, entry["money"], "{:.2f}€".format(entry["money"])) for entry in entries]
    calendar_charts.append(("hours_calendar", "Incurred hours per day", "Hours", hours_calendar_data))
    calendar_charts.append(("money_calendar", "Incurred billing per day", "Money", money_calendar_data))

    treemaps = []

    treemaps.append(gen_treemap_data_projects(person.hourentry_set.all()))
    treemaps.append(gen_treemap_data_projects(person.hourentry_set.filter(calculated_is_billable=True), "incurred_money", "Money"))

    months = HourEntry.objects.filter(user_m=person).exclude(incurred_hours=0).dates("date", "month", order="DESC")

    return render(request, "person_details.html", {"entries": entries, "person": person, "calendar_charts": calendar_charts, "months": months, "treemap_charts": treemaps})


@login_required
def person_details_month(request, year, month, user_guid):
    year = int(year)
    month = int(month)
    person = get_object_or_404(TenkfUser, guid=user_guid)
    entries = person.hourentry_set.exclude(incurred_hours=0).filter(date__year=year, date__month=month).select_related("project_m", "user_m").order_by("date")
    months = HourEntry.objects.filter(user_m=person).exclude(incurred_hours=0).dates("date", "month", order="DESC")
    return render(request, "person.html", {"person": person, "hour_entries": entries, "months": months, "month": month, "year": year, "stats": calculate_entry_stats(entries, [])})


@login_required
def users_list(request):
    now = timezone.now()
    year = int(request.GET.get("year", now.year))
    month = int(request.GET.get("month", now.month))
    people_data = {}
    for person in TenkfUser.objects.filter(archived=False):
        people_data[person.email] = {"billable": {"incurred_hours": 0, "incurred_money": 0}, "non-billable": {"incurred_hours": 0, "incurred_money": 0}, "person": person, "issues": 0}
    for entry in HourEntry.objects.exclude(incurred_hours=0).filter(date__year=year, date__month=month).exclude(project="[Leave Type]"):
        if entry.user_email not in people_data:
            continue  # TODO: logging
        if entry.calculated_is_billable:
            k = "billable"
        else:
            k = "non-billable"
        people_data[entry.user_email][k]["incurred_hours"] += entry.incurred_hours
        people_data[entry.user_email][k]["incurred_money"] += entry.incurred_money
        if not entry.calculated_has_notes or not entry.calculated_has_phase or not entry.calculated_has_category:
            people_data[entry.user_email]["issues"] += 1
    for person in people_data.values():
        incurred_hours = person["billable"]["incurred_hours"] + person["non-billable"]["incurred_hours"]
        person["incurred_hours"] = incurred_hours
        if incurred_hours > 0:
            person["invoicing_ratio"] = person["billable"]["incurred_hours"] / incurred_hours * 100
            person["bill_rate_avg"] = person["billable"]["incurred_money"] / incurred_hours
        if person["billable"]["incurred_hours"] > 0:
            person["bill_rate_avg_billable"] = person["billable"]["incurred_money"] / person["billable"]["incurred_hours"]
    return render(request, "people.html", {"people": people_data, "year": year, "month": month})


def parse_date(date_string):
    return datetime.datetime.strptime(date_string, "%Y-%m-%d").date()


@staff_member_required
def hours_sickleaves(request):
    class DatePeriod(object):
        def __init__(self, item=None):
            self.items = []
            if item:
                self.items.append(item)

        def num_days(self):
            if len(self.items) == 2:
                return (self.items[1] - self.items[0]).days + 1

    start_date = datetime.date.today() - datetime.timedelta(days=365)
    short_period_start_date = datetime.date.today() - datetime.timedelta(days=120)
    sick_leaves = HourEntry.objects.filter(date__gte=start_date).exclude(user_m=None).filter(leave_type="Sick leave").order_by("user_m", "date").values("user_m__email", "user_m__display_name", "user_m__pk", "date").annotate(incurred_hours_sum=Sum("incurred_hours"))

    per_person_info = defaultdict(lambda: {"short": 0, "long": 0, "short_periods": []})
    for item in sick_leaves:
        per_person_info[item["user_m__pk"]]["user_pk"] = item["user_m__pk"]
        per_person_info[item["user_m__pk"]]["user_email"] = item["user_m__email"]
        per_person_info[item["user_m__pk"]]["user_name"] = item["user_m__display_name"]
        per_person_info[item["user_m__pk"]]["long"] += 1
        if item["date"] > short_period_start_date:
            per_person_info[item["user_m__pk"]]["short_periods"].append(item["date"])

    for person in per_person_info.values():
        previous_date = None
        collected_periods = []
        current_period = DatePeriod()
        item = None
        for item in person["short_periods"]:
            if previous_date is None:
                previous_date = item
                person["short"] += 1
                current_period.items.append(item)
                continue
            if item - previous_date > datetime.timedelta(days=3):
                current_period.items.append(previous_date)
                collected_periods.append(current_period)
                current_period = DatePeriod(item)
                person["short"] += 1
            previous_date = item
        if item:
            current_period.items.append(item)
            collected_periods.append(current_period)
        person["collected_periods"] = collected_periods

    sick_leaves_exceeding_limits = sorted([k for k in per_person_info.values() if k["short"] > 3 or k["long"] > 20], key=lambda k: k["user_name"])
    sick_leaves_not_exceeding_limits = sorted([k for k in per_person_info.values() if k["short"] <= 3 and k["long"] <= 20], key=lambda k: k["user_name"])

    return render(request, "hours/sickleaves.html", {"sick_leaves_exceeding_limits": sick_leaves_exceeding_limits, "sick_leaves_not_exceeding_limits": sick_leaves_not_exceeding_limits})


@staff_member_required
def queue_slack_notification(request):
    if request.method == "POST":
        return_url = request.POST.get("back") or reverse("queue_slack_notification")
        notification_type = request.POST.get("type")
        if not notification_type:
            return HttpResponseBadRequest()
        REDIS.publish("request-refresh", json.dumps({"type": "slack-{}-notification".format(notification_type)}))

        messages.add_message(request, messages.INFO, "Slack notifications for {} queued.".format(notification_type))
        return HttpResponseRedirect(return_url)

    notification_history = SlackNotificationBundle.objects.all()
    last_unsubmitted_notification_at = last_unapproved_notification_at = None
    for item in notification_history:
        if not last_unsubmitted_notification_at and item.notification_type == "unsubmitted":
            last_unsubmitted_notification_at = item.sent_at
        if not last_unapproved_notification_at and item.notification_type == "unapproved":
            last_unapproved_notification_at = item.sent_at
        if last_unapproved_notification_at and last_unsubmitted_notification_at:
            break
    context = {
        "slack_notification_history": notification_history,
        "last_unsubmitted_notification_at": last_unsubmitted_notification_at,
        "last_unapproved_notification_at": last_unapproved_notification_at,
    }
    return render(request, "slack_notifications.html", context)


@login_required
def queue_update(request):
    if request.method == "POST":
        return_url = request.POST.get("back") or reverse("frontpage")
        end_date = parse_date(request.POST.get("end_date", (datetime.date.today() + datetime.timedelta(days=2)).strftime("%Y-%m-%d")))
        start_date = parse_date(request.POST.get("start_date", (datetime.datetime.now() - datetime.timedelta(days=60)).strftime("%Y-%m-%d")))
        try:
            now = timezone.now()
            last_update_at = DataUpdate.objects.exclude(aborted=True).exclude(finished_at=None).latest("finished_at")
            finished = now - last_update_at.finished_at
            if finished < datetime.timedelta(seconds=15):
                messages.add_message(request, messages.WARNING, "Data was just updated. Please try again later.")
                return HttpResponseRedirect(return_url)

            running = DataUpdate.objects.exclude(aborted=True).filter(finished_at=None).exclude(started_at=None)
            if running.count() > 0 and now - running.latest().created_at < datetime.timedelta(minutes=10):
                messages.add_message(request, messages.WARNING, "Update is currently running. Please try again later.")
                return HttpResponseRedirect(return_url)
        except DataUpdate.DoesNotExist:
            pass
        REDIS.publish("request-refresh", json.dumps({"type": "data-update", "start_date": start_date.strftime("%Y-%m-%d"), "end_date": end_date.strftime("%Y-%m-%d")}))
        update_obj = DataUpdate()
        update_obj.save()
        messages.add_message(request, messages.INFO, "Update queued. This is normally finished within 10 seconds. Refresh the page to see new data.")
        return HttpResponseRedirect(return_url)
    return HttpResponseBadRequest()


@login_required
def get_invoice_xls(request, invoice_id, xls_type):
    if xls_type == "hours":
        xls, title = generate_hours_xls_for_invoice(request, invoice_id)
    else:
        return HttpResponseBadRequest("Invalid XLS type")

    response = HttpResponse(xls, content_type="application/vnd.ms-excel")
    response["Content-Disposition"] = "attachment; filename='Hours for {}.xlsx'".format(title)
    return response


@login_required
def get_invoice_pdf(request, invoice_id, pdf_type):
    if pdf_type == "hours":
        pdf, title = generate_hours_pdf_for_invoice(request, invoice_id)
    else:
        return HttpResponseBadRequest("Invalid PDF type")

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = "attachment; filename='Hours for {}.pdf'".format(title)
    return response


@login_required
def your_unsubmitted_hours(request):
    user = TenkfUser.objects.get(email=request.user.email)
    if request.method == "POST":
        if request.POST.get("action") == "submit":
            ids = request.POST.get("ids")
            if not ids:
                return HttpResponseBadRequest("Missing IDs")
            ids = ids.split(",")
            entries = HourEntry.objects.filter(user_m=user).filter(status="Unsubmitted").filter(upstream_id__in=ids).exclude(project_m__archived=True).exclude(incurred_hours=0).exclude(updated_at=None).filter(date__gte=datetime.date.today() - datetime.timedelta(days=60))
            tenkfeet_api = TenkFeetApi(settings.TENKFEET_AUTH)
            update_entries = []
            for entry in entries:
                updated_at = entry.updated_at.isoformat().replace("+00:00", "Z")
                update_entries.append({
                    "id": entry.upstream_id,
                    "updated_at": updated_at
                })
                print(entry.upstream_id, entry.updated_at, entry.upstream_approvable_updated_at)
                print(update_entries)
            response = tenkfeet_api.submit_hours(update_entries)
            print(response)
            if "data" in response:
                update_items = []
                for item in response["data"]:
                    if item["status"] == "pending":
                        update_items.append(item["approvable_id"])
                HourEntry.objects.filter(upstream_id__in=update_items).update(status="Pending Approval")
            start_date = min([entry.date for entry in entries])
            end_date = max([entry.date for entry in entries])
            if end_date - start_date < datetime.timedelta(days=180):
                update_data = {
                    "type": "data-update",
                    "start_date": start_date.strftime("%Y-%m-%d"),
                    "end_date": end_date.strftime("%Y-%m-%d"),
                }
                REDIS.publish("request-refresh", json.dumps(update_data))
                messages.add_message(request, messages.INFO, "Hours submitted and update queued - updating this page will take a few moments (usually <10s, but in some rare cases up to 30 minutes)")
            else:
                messages.add_message(request, messages.INFO, "Hours submitted. Data entry was not queued, as entries are spread over 6 months period.")

    unsubmitted_entries = HourEntry.objects.filter(user_m=user).filter(status="Unsubmitted").exclude(project_m__archived=True).exclude(incurred_hours=0).order_by("-date")
    return render(request, "unsubmitted_hours.html", {"person": user, "unsubmitted_entries": unsubmitted_entries, "ids": ",".join(str(entry.upstream_id) for entry in unsubmitted_entries if entry.can_submit_automatically)})


@login_required
def your_stats(request):
    try:
        your_last_hour_marking = HourEntry.objects.filter(user_email=request.user.email).values_list("date", flat=True).latest("date")
    except HourEntry.DoesNotExist:
        your_last_hour_marking = "No entries"

    today = datetime.date.today()
    your_hours_this_week = HourEntry.objects.filter(user_email=request.user.email).filter(date__gte=today - datetime.timedelta(days=6), date__lte=today).aggregate(hours=Sum("incurred_hours"))["hours"] or 0

    your_unsubmitted_entries = HourEntry.objects.filter(user_email=request.user.email).exclude(incurred_hours=0).filter(status="Unsubmitted").count()

    billing_rate_data = HourEntry.objects.filter(user_email="olli.jarva@solinor.com").filter(date__gte=today - datetime.timedelta(days=30)).values("user_email").order_by("user_email").annotate(billable_hours=Sum("incurred_hours", filter=Q(calculated_is_billable=True))).annotate(nonbillable_hours=Sum("incurred_hours", filter=Q(calculated_is_billable=False)))
    your_billing_rate = "?"
    if billing_rate_data:
        total_hours = billing_rate_data[0]["nonbillable_hours"] + billing_rate_data[0]["billable_hours"]
        if total_hours > 0:
            your_billing_rate = float(billing_rate_data[0]["billable_hours"]) / total_hours * 100

    return JsonResponse({
        "your_last_hour_marking": your_last_hour_marking,
        "your_last_hour_marking_day": your_last_hour_marking.strftime("%A"),
        "your_hours_this_week": your_hours_this_week,
        "your_billing_rate": your_billing_rate,
        "your_unsubmitted_entries": your_unsubmitted_entries,
    })


@login_required
def frontpage_invoice_table(request):
    all_invoices = Invoice.objects.exclude(Q(incurred_hours=0) & Q(incurred_money=0)).exclude(project_m__project_state="Internal").exclude(client__in=["Solinor", "[none]"])
    filters = InvoiceFilter(request.GET, queryset=all_invoices)
    table = FrontpageInvoices(filters.qs)
    RequestConfig(request, paginate={
        "per_page": 100
    }).configure(table)
    context = {
        "invoices": table,
        "filters": filters,
    }
    return render(request, "snippets/invoices_table.html", context)


@login_required
def frontpage(request):
    last_month = datetime.date.today().replace(day=1) - datetime.timedelta(days=1)
    your_invoices = Invoice.objects.exclude(Q(incurred_hours=0) & Q(incurred_money=0)).filter(tags__icontains="{} {}".format(request.user.first_name, request.user.last_name)).filter(year=last_month.year).filter(month=last_month.month).exclude(client__in=["Solinor", "[none]"])

    try:
        last_update_finished_at = REDIS.get("last-data-update").decode()
    except TypeError:
        last_update_finished_at = "?"
    last_update_finished_at = parse_datetime(last_update_finished_at) or "?"
    context = {
        "your_invoices": your_invoices,
        "last_update_finished_at": last_update_finished_at,
    }
    return render(request, "frontpage.html", context)


@login_required
def invoice_hours(request, invoice_id):
    invoice = get_object_or_404(Invoice, invoice_id=invoice_id)
    entries = HourEntry.objects.filter(invoice=invoice).filter(incurred_hours__gt=0).select_related("user_m")

    previous_invoices = []
    if invoice.project_m:
        previous_invoices = Invoice.objects.filter(project_m=invoice.project_m)

    context = {
        "invoice": invoice,
        "entries": entries,
        "previous_invoices": previous_invoices,
        "recent_invoice": abs((datetime.date.today() - datetime.date(invoice.year, invoice.month, 1)).days) < 60,
    }
    return render(request, "invoice_hours.html", context)


@login_required
def projects_list(request):
    projects = Project.objects.annotate(incurred_money=Sum("invoice__incurred_money"), incurred_hours=Sum("invoice__incurred_hours")).exclude(incurred_hours=0).prefetch_related("admin_users")
    show_only = request.GET.get("show_only", "").split(",")
    if "no_lead" in show_only:
        projects = projects.annotate(admin_users_count=Count("admin_users")).filter(admin_users_count=0)
    if "running" in show_only:
        today = datetime.date.today()
        projects = projects.filter(ends_at__gte=today).filter(starts_at__lte=today)

    filters = ProjectsFilter(request.GET, queryset=projects)
    table = ProjectsTable(filters.qs)
    RequestConfig(request, paginate={
        "per_page": 250
    }).configure(table)
    context = {
        "projects": table,
        "filters": filters,
    }
    return render(request, "projects.html", context)


@login_required
def project_details(request, project_id):
    project = get_object_or_404(Project, guid=project_id)
    invoices = Invoice.objects.filter(project_m=project).exclude(Q(incurred_hours=0) & Q(incurred_money=0))
    filters = ProjectsFilter(request.GET, queryset=invoices)
    table = ProjectDetailsTable(filters.qs)
    RequestConfig(request, paginate={
        "per_page": 250
    }).configure(table)
    context = {
        "invoices": table,
        "filters": filters,
        "project": project,
    }
    return render(request, "project_details.html", context)


@login_required
def hours_charts(request):
    treemaps = []
    linecharts = []
    calendar_charts = []
    year_ago = (datetime.date.today() - datetime.timedelta(days=365)).replace(month=1, day=1)
    treemaps.append(gen_treemap_data_projects(HourEntry.objects.all()))
    treemaps.append(gen_treemap_data_projects(HourEntry.objects.filter(calculated_is_billable=True), "incurred_money", "Gross income per project"))
    treemaps.append(gen_treemap_data_users(HourEntry.objects.all()))
    treemaps.append(gen_treemap_data_users(HourEntry.objects.filter(calculated_is_billable=True), "incurred_money", "Gross income per person"))

    entries = HourEntry.objects.filter(date__gte=year_ago).order_by("date").values("date").annotate(hours=Sum("incurred_hours"))
    hours_calendar_data = [(entry["date"].year, entry["date"].month - 1, entry["date"].day, entry["hours"], "{:.2f}h".format(entry["hours"])) for entry in entries]
    entries = HourEntry.objects.filter(date__gte=year_ago).filter(calculated_is_billable=True).order_by("date").values("date").annotate(money=Sum("incurred_money"))
    money_calendar_data = [(entry["date"].year, entry["date"].month - 1, entry["date"].day, entry["money"], "{:.2f}€".format(entry["money"])) for entry in entries if entry["money"] > 0]

    calendar_charts.append(("hours_calendar", "Incurred hours per day", "Hours", hours_calendar_data))
    calendar_charts.append(("money_calendar", "Incurred billing per day", "Money", money_calendar_data))

    entries = HourEntry.objects.filter(date__gte=year_ago).filter(calculated_is_billable=True).annotate(month=TruncMonth("date")).order_by("month").values("month").annotate(hours=Sum("incurred_hours")).annotate(money=Sum("incurred_money")).values("month", "hours", "money")
    monthly_avg_billing = [["Date", "Bill rate avg"]] + [["{}-{}".format(entry["month"].year, entry["month"].month), entry["money"] / entry["hours"]] for entry in entries]
    linecharts.append(("billing_rate_avg", "Billing rate avg (billable hours)", json.dumps(monthly_avg_billing)))

    entries = HourEntry.objects.filter(date__gte=year_ago).filter(calculated_is_billable=True).annotate(month=TruncMonth("date")).order_by("month").values("month").annotate(hours=Sum("incurred_hours")).annotate(money=Sum("incurred_money")).values("month", "hours", "money")
    money_per_month_data = [["Date", "Gross income (billing)"]] + [["{}-{}".format(entry["month"].year, entry["month"].month), entry["money"]] for entry in entries]
    linecharts.append(("incurred_money", "Gross income (billing) per month", json.dumps(money_per_month_data)))
    entries = HourEntry.objects.filter(date__gte=year_ago).annotate(month=TruncMonth("date")).order_by("month").values("month").annotate(hours=Sum("incurred_hours")).annotate(money=Sum("incurred_money")).values("month", "hours", "money")
    hours_per_month_data = [["Date", "Incurred hours"]] + [["{}-{}".format(entry["month"].year, entry["month"].month), entry["hours"]] for entry in entries]
    linecharts.append(("incurred_hours", "Incurred hours per month", json.dumps(hours_per_month_data)))
    return render(request, "hours_charts.html", {"treemap_charts": treemaps, "line_charts": linecharts, "calendar_charts": calendar_charts})


@login_required
def users_charts(request):
    linecharts = []
    calendar_charts = []
    year_ago = (datetime.date.today() - datetime.timedelta(days=365)).replace(month=1, day=1)

    entries = HourEntry.objects.filter(date__gte=year_ago).filter(leave_type__in=["Annual holiday", "Flex time Leave", "Other paid leave", "Parental leave", "Unpaid leave", "Vuosiloma"]).order_by("date").values("date").annotate(hours=Count("incurred_hours"))
    hours_calendar_data = [(entry["date"].year, entry["date"].month - 1, entry["date"].day, entry["hours"], "{:.2f}h".format(entry["hours"])) for entry in entries]
    calendar_charts.append(("annual_holiday_calendar", "People enjoying holidays per day", "People", hours_calendar_data))

    entries = HourEntry.objects.filter(date__gte=year_ago).filter(leave_type="Sick leave").order_by("date").values("date").annotate(hours=Count("incurred_hours"))
    hours_calendar_data = [(entry["date"].year, entry["date"].month - 1, entry["date"].day, entry["hours"], "{:.2f}h".format(entry["hours"])) for entry in entries]
    calendar_charts.append(("sick_leaves_calendar", "People on sick leave per day", "People", hours_calendar_data))

    return render(request, "people_charts.html", {"calendar_charts": calendar_charts, "line_charts": linecharts})


@login_required
def hours_overview(request):
    today = datetime.date.today()
    period_start = today - datetime.timedelta(days=30)
    hour_markings = HourEntry.objects.filter(date__gte=period_start).exclude(user_m=None).values("user_m__guid", "user_name", "date").annotate(hours=Sum("incurred_hours"))
    days = []
    current_day = period_start
    while True:
        days.append({"date": current_day, "hours": 0, "weekday": current_day.strftime("%a")})
        current_day += datetime.timedelta(days=1)
        if current_day > today:
            break
    people = {}
    for hour_marking in hour_markings:
        guid = hour_marking["user_m__guid"]
        if guid not in people:
            people[guid] = {"name": hour_marking["user_name"],
                            "guid": guid,
                            "days": copy.deepcopy(days),
                            "sum_of_hours": 0}
        for i, current_day in enumerate(people[guid]["days"]):
            if current_day["date"] == hour_marking["date"]:
                people[guid]["days"][i]["hours"] += hour_marking["hours"]
                people[guid]["sum_of_hours"] += hour_marking["hours"]
    people = sorted(people.values(), key=lambda k: k.get("name", ""))
    return render(request, "people_hourmarkings.html", {"people": people, "days": days, "today": today})


@login_required
def project_charts(request, project_id):
    project = get_object_or_404(Project, guid=project_id)
    linecharts = []
    calendar_charts = []
    year_ago = (datetime.date.today() - datetime.timedelta(days=365)).replace(month=1, day=1)
    entries = project.hourentry_set.filter(date__gte=year_ago).order_by("date").values("date").annotate(hours=Sum("incurred_hours"))
    hours_calendar_data = [(entry["date"].year, entry["date"].month - 1, entry["date"].day, entry["hours"], "{:.2f}h".format(entry["hours"])) for entry in entries]
    entries = project.hourentry_set.filter(date__gte=year_ago).filter(calculated_is_billable=True).order_by("date").values("date").annotate(money=Sum("incurred_money"))
    money_calendar_data = [(entry["date"].year, entry["date"].month - 1, entry["date"].day, entry["money"], "{:.2f}€".format(entry["money"])) for entry in entries if entry["money"] > 0]
    calendar_charts.append(("hours_calendar", "Incurred hours per day", "Hours", hours_calendar_data))
    calendar_charts.append(("money_calendar", "Incurred billing per day", "Money", money_calendar_data))

    entries = HourEntry.objects.filter(project_m=project).filter(calculated_is_billable=True).annotate(month=TruncMonth("date")).order_by("month").values("month").annotate(hours=Sum("incurred_hours")).annotate(money=Sum("incurred_money")).values("month", "hours", "money")
    monthly_avg_billing = [["Date", "Bill rate avg"]] + [["{}-{}".format(entry["month"].year, entry["month"].month), entry["money"] / entry["hours"]] for entry in entries]
    linecharts.append(("billing_rate_avg", "Billing rate avg", json.dumps(monthly_avg_billing)))
    money_per_month_data = [["Date", "Gross income"]] + [["{}-{}".format(entry["month"].year, entry["month"].month), entry["money"]] for entry in entries]
    linecharts.append(("incurred_money", "Gross income per month", json.dumps(money_per_month_data)))
    entries = HourEntry.objects.filter(project_m=project).annotate(month=TruncMonth("date")).order_by("month").values("month").annotate(hours=Sum("incurred_hours")).annotate(money=Sum("incurred_money")).values("month", "hours", "money")
    hours_per_month_data = [["Date", "Incurred hours"]] + [["{}-{}".format(entry["month"].year, entry["month"].month), entry["hours"]] for entry in entries]
    linecharts.append(("incurred_hours", "Incurred hours per month", json.dumps(hours_per_month_data)))

    return render(request, "project_charts.html", {"calendar_charts": calendar_charts, "project": project, "line_charts": linecharts})


@login_required
def invoice_charts(request, invoice_id):
    invoice = get_object_or_404(Invoice, invoice_id=invoice_id)
    if invoice.project_m:
        previous_invoices = Invoice.objects.filter(project_m=invoice.project_m).order_by("-year", "-month")
    else:
        previous_invoices = []
    first_day = datetime.datetime.strptime(request.GET.get("first_day", invoice.month_start_date.strftime("%Y-%m-%d")), "%Y-%m-%d")
    last_day = datetime.datetime.strptime(request.GET.get("last_day", invoice.month_end_date.strftime("%Y-%m-%d")), "%Y-%m-%d")

    def get_chart_data(queryset):
        data = defaultdict(float)
        for item in queryset:
            data[item[0]] += item[1]
        data = sorted(data.items(), key=lambda k: k[0])
        return [["a", "b"]] + data

    def get_2d_chart_data(queryset):
        def per_person_dict():
            return defaultdict(float)

        data = defaultdict(per_person_dict)
        for item in queryset:
            data[item[0]][item[1]] += item[2]
        return data

    charts = {
        "per_category_hours": {
            "queryset": HourEntry.objects.values_list("category").annotate(hours=Sum("incurred_hours")),
            "callback": get_chart_data,
            "title": "Incurred hours per category",
        },
        "per_category_billing": {
            "queryset": HourEntry.objects.values_list("category").filter(calculated_is_billable=True).annotate(hours=Sum("incurred_money")),
            "callback": get_chart_data,
            "title": "Incurred billing per category",
        },
        "per_person_hours": {
            "queryset": HourEntry.objects.values_list("user_name").annotate(hours=Sum("incurred_hours")),
            "callback": get_chart_data,
            "title": "Incurred hours per person",
        },
        "per_person_billing": {
            "queryset": HourEntry.objects.values_list("user_name").filter(calculated_is_billable=True).annotate(hours=Sum("incurred_money")),
            "callback": get_chart_data,
            "title": "Incurred billing per person",
        },
    }
    for chart_name in charts:
        chart_data = charts[chart_name]
        chart_data["queryset"] = chart_data["queryset"].filter(invoice=invoice).filter(date__gte=first_day).filter(date__lte=last_day)
        chart_data["data"] = chart_data["callback"](chart_data["queryset"])
        chart_data["json_data"] = json.dumps(chart_data["data"])

    per_person_categories = get_2d_chart_data(HourEntry.objects.values_list("user_name", "category").annotate(hours=Sum("incurred_hours")).filter(invoice=invoice).filter(date__gte=first_day).filter(date__lte=last_day))

    categories = set()
    for data in per_person_categories.values():
        categories.update(data.keys())

    per_person_categories_data = []
    i = 0
    for user_name, data in per_person_categories.items():
        for item in categories:
            data[item] += 0
        data = sorted(data.items(), key=lambda k: k[0])
        per_person_categories_data.append((i, user_name, json.dumps([["a", "b"]] + data)))
        i += 1

    context = {
        "invoice": invoice,
        "charts": charts,
        "per_person_categories_data": per_person_categories_data,
        "previous_invoices": previous_invoices,
    }
    return render(request, "invoice_charts.html", context)


@login_required
def invoice_page(request, invoice_id, **_):
    invoice = get_object_or_404(Invoice, invoice_id=invoice_id)

    if request.method == "POST":
        invoice_number = request.POST.get("invoiceNumber") or None
        if invoice_number:
            invoice_number = invoice_number.strip()
        comment = Comments(comments=request.POST.get("changesForInvoice"),
                           checked=request.POST.get("invoiceChecked", False) in (True, "true", "on"),
                           checked_non_billable_ok=request.POST.get("nonBillableHoursOk", False) in (True, "true", "on"),
                           checked_bill_rates_ok=request.POST.get("billableIncorrectPriceOk", False) in (True, "true", "on"),
                           checked_phases_ok=request.POST.get("nonPhaseSpecificOk", False) in (True, "true", "on"),
                           checked_no_category_ok=request.POST.get("noCategoryOk", False) in (True, "true", "on"),
                           checked_changes_last_month=request.POST.get("remarkableChangesOk", False) in (True, "true", "on"),
                           invoice_number=invoice_number,
                           invoice_sent_to_customer=request.POST.get("invoiceSentToCustomer", False) in (True, "true", "on"),
                           user=request.user.email,
                           invoice=invoice)
        comment.save()
        invoice.is_approved = comment.checked
        invoice.has_comments = comment.has_comments()
        invoice_sent_earlier = invoice.invoice_state in ("P", "S")
        invoice.update_state(comment)
        invoice.save()
        messages.add_message(request, messages.INFO, "Saved.")
        if not invoice_sent_earlier and invoice.invoice_state in ("P", "S") and invoice.project_m:
            for project_fixed_entry in ProjectFixedEntry.objects.filter(project=invoice.project_m):
                if InvoiceFixedEntry.objects.filter(invoice=invoice, price=project_fixed_entry.price, description=project_fixed_entry.description).count() == 0:
                    InvoiceFixedEntry(invoice=invoice, price=project_fixed_entry.price, description=project_fixed_entry.description).save()
        if invoice_sent_earlier and invoice.invoice_state not in ("P", "S"):
            InvoiceFixedEntry.objects.filter(invoice=invoice).delete()
        return HttpResponseRedirect(reverse("invoice", args=[invoice.invoice_id]))

    today = datetime.date.today()
    due_date = today + datetime.timedelta(days=14)

    entries = HourEntry.objects.filter(invoice=invoice).filter(incurred_hours__gt=0)
    aws_entries = None
    if invoice.project_m:
        aws_accounts = invoice.project_m.amazon_account.all()
        aws_entries = get_aws_entries(aws_accounts, invoice.month_start_date, invoice.month_end_date)
    entry_data = calculate_entry_stats(entries, invoice.get_fixed_invoice_rows(), aws_entries)

    try:
        latest_comments = Comments.objects.filter(invoice=invoice).latest()
    except Comments.DoesNotExist:
        latest_comments = None

    previous_invoices = []
    if invoice.project_m:
        previous_invoices = Invoice.objects.filter(project_m=invoice.project_m)

    context = {
        "today": today,
        "due_date": due_date,
        "entries": entries,
        "form_data": latest_comments,
        "invoice": invoice,
        "previous_invoices": previous_invoices,
        "recent_invoice": abs((datetime.date.today() - datetime.date(invoice.year, invoice.month, 1)).days) < 60,
    }
    context.update(entry_data)

    previous_invoice_month = invoice.month - 1
    previous_invoice_year = invoice.year
    if previous_invoice_month == 0:
        previous_invoice_month = 12
        previous_invoice_year -= 1
    try:
        last_month_invoice = Invoice.objects.get(project=invoice.project, client=invoice.client, year=previous_invoice_year, month=previous_invoice_month)
        context["last_month_invoice"] = last_month_invoice
        context["diff_last_month"] = last_month_invoice.compare(invoice)
    except Invoice.DoesNotExist:
        pass

    return render(request, "invoice_page.html", context)


@staff_member_required
@login_required
def admin_sync(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if not action:
            return HttpResponseBadRequest("No action specified")
        if action == "sync_public_holidays":
            sync_public_holidays()
        if action == "sync_10000ft_users":
            sync_10000ft_users()
        if action == "sync_10000ft_projects":
            sync_10000ft_projects()
        if action == "sync_slack_channels":
            refresh_slack_channels()
        if action == "sync_slack_users":
            refresh_slack_users()
    events = Event.objects.all()
    return render(request, "admin_sync.html", {"events": events})
