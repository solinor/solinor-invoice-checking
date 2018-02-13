# -*- coding: utf-8 -*-

import copy
import datetime
import json
import pickle
from collections import defaultdict

import redis
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.staticfiles.templatetags.staticfiles import static
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django_tables2 import RequestConfig

from flex_hours.utils import sync_public_holidays
from invoices.chart_utils import gen_treemap_data_projects, gen_treemap_data_users
from invoices.filters import ClientsFilter, HourListFilter, InvoiceFilter, ProjectsFilter
from invoices.hours.file_exports import generate_hours_pdf_for_invoice, generate_hours_xls_for_invoice
from invoices.hours.sickleaves import get_early_care_sickleaves
from invoices.hours.stats import calculate_clientbase_stats, hours_overview_stats
from invoices.invoice_utils import calculate_entry_stats, generate_amazon_invoice_data, get_aws_entries
from invoices.models import (AmazonInvoiceRow, AmazonLinkedAccount, Client, Comments, DataUpdate, Event, HourEntry,
                             Invoice, InvoiceFixedEntry, Project, ProjectFixedEntry, SlackNotificationBundle, TenkfUser)
from invoices.syncing.slack import sync_slack_channels, sync_slack_users
from invoices.syncing.tenkfeet import sync_10000ft_projects, sync_10000ft_users
from invoices.tables import ClientsTable, HourListTable, InvoicesTable, ProjectDetailsTable, ProjectsTable
from invoices.tenkfeet_api import TenkFeetApi
from invoices.utils import daterange, month_end_date, month_start_date

REDIS = redis.from_url(settings.REDIS)


def handler404(request):
    response = render(request, "404.html")
    response.status_code = 404
    return response


def handler500(request):
    response = render(request, "500.html")
    response.status_code = 500
    return response


def manifest(request):  # pylint:disable=unused-argument
    data = {
        "name": "Solinor Finance",
        "display": "standalone",
        "background_color": "#fff",
        "description": "Invoices, flex saldos, hour reports and checks.",
        "short_name": "SolFinance",
        "theme_color": "#222",
        "start_url": "/",
        "icons": [
            {
                "src": static("icons/icon-72x72.png"),
                "sizes": "72x72",
                "type": "image/png"
            },
            {
                "src": static("icons/icon-96x96.png"),
                "sizes": "96x96",
                "type": "image/png"
            },
            {
                "src": static("icons/icon-128x128.png"),
                "sizes": "128x128",
                "type": "image/png"
            },
            {
                "src": static("icons/icon-144x144.png"),
                "sizes": "144x144",
                "type": "image/png"
            },
            {
                "src": static("icons/icon-152x152.png"),
                "sizes": "152x152",
                "type": "image/png"
            },
            {
                "src": static("icons/icon-192x192.png"),
                "sizes": "192x192",
                "type": "image/png"
            },
            {
                "src": static("icons/icon-384x384.png"),
                "sizes": "384x384",
                "type": "image/png"
            },
            {
                "src": static("icons/icon-512x512.png"),
                "sizes": "512x512",
                "type": "image/png"
            },
        ],
    }
    return HttpResponse(json.dumps(data), content_type="application/manifest+json")


@login_required
def search(request):
    query = request.GET.get("q")
    if not query:
        return render(request, "search.html")

    users = TenkfUser.objects.filter(archived=False).filter(Q(email__icontains=query) | Q(display_name__icontains=query))
    projects = Project.objects.filter(Q(name__icontains=query) | Q(client_m__name__icontains=query)).select_related("client_m")
    if len(users) == 1 and not projects:
        return HttpResponseRedirect(reverse("person_overview", args=(users[0].guid,)))
    elif projects:
        return HttpResponseRedirect(reverse("project", args=(projects[0].guid,)))
    return render(request, "search.html", {"q": query, "users": users, "projects": projects})


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
    return render(request, "amazon/overview.html", context)


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

    return render(request, "amazon/invoice.html", context)


@login_required
def hours_browser(request):
    if not request.GET:
        today = datetime.date.today()
        start_date = month_start_date(today.year, today.month)
        end_date = month_end_date(today.year, today.month)
        url = reverse("hours_browser")
        return HttpResponseRedirect(f"{url}?date__gte={start_date}&date__lte={end_date}")
    hours = HourEntry.objects.exclude(status="Unsubmitted").filter(incurred_hours__gt=0).exclude(invoice__project_m__name="[Leave Type]").select_related("user_m", "invoice__project_m", "invoice__project_m__client_m")
    filters = HourListFilter(request.GET, queryset=hours)
    table = HourListTable(filters.qs)
    RequestConfig(request, paginate={
        "per_page": 250
    }).configure(table)

    context = {
        "table": table,
        "filters": filters,
    }
    return render(request, "hours/browser.html", context=context)


@login_required
def person_overview(request, user_guid):
    person = get_object_or_404(TenkfUser, guid=user_guid)
    year_ago = (datetime.date.today() - datetime.timedelta(days=365)).replace(day=1, month=1)
    entries = person.hourentry_set.exclude(status="Unsubmitted")
    filters = request.GET.get("filters", "").split(",")
    if "exclude_leaves" in filters:
        entries = entries.exclude(project_m__name="[Leave Type]")
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

    months = HourEntry.objects.exclude(status="Unsubmitted").filter(user_m=person).exclude(incurred_hours=0).dates("date", "month", order="DESC")

    return render(request, "users/person_overview.html", {"entries": entries, "person": person, "calendar_charts": calendar_charts, "months": months, "treemap_charts": treemaps})


@login_required
def person_details_month(request, year, month, user_guid):
    year = int(year)
    month = int(month)
    person = get_object_or_404(TenkfUser, guid=user_guid)
    base_query = person.hourentry_set.exclude(status="Unsubmitted").exclude(incurred_hours=0)

    entries = base_query.filter(date__year=year, date__month=month).select_related("invoice__project_m", "user_m").order_by("date")
    months = base_query.dates("date", "month", order="DESC")
    return render(request, "users/person_details_month.html", {"person": person, "hour_entries": entries, "months": months, "month": month, "year": year, "stats": calculate_entry_stats(entries, [])})


@login_required
def users_list(request):
    now = timezone.now()
    year = int(request.GET.get("year", now.year))
    month = int(request.GET.get("month", now.month))
    people_data = {}
    for person in TenkfUser.objects.filter(archived=False):
        people_data[person.email] = {"billable": {"incurred_hours": 0, "incurred_money": 0}, "non-billable": {"incurred_hours": 0, "incurred_money": 0}, "person": person, "issues": 0}
    for entry in HourEntry.objects.filter(user_m__archived=False).exclude(status="Unsubmitted").exclude(incurred_hours=0).filter(date__year=year, date__month=month).exclude(invoice__project_m__name="[Leave Type]"):
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
    return render(request, "users/list.html", {"people": people_data, "year": year, "month": month})


def parse_date(date_string):
    return datetime.datetime.strptime(date_string, "%Y-%m-%d").date()


@login_required
@permission_required("invoices.can_see_sick_leaves")
def hours_sickleaves(request):
    return render(request, "hours/sickleaves.html", get_early_care_sickleaves())


@login_required
@permission_required("invoices.can_send_notifications")
def queue_slack_notification(request):
    today = datetime.date.today()
    end_date = today - datetime.timedelta(days=today.isoweekday())
    start_date = end_date - datetime.timedelta(days=60)

    if request.method == "POST":
        return_url = request.POST.get("back") or reverse("queue_slack_notification")
        notification_type = request.POST.get("type")
        if not notification_type:
            return HttpResponseBadRequest()
        start_date = datetime.datetime.strptime(request.POST.get("start_date"), "%Y-%m-%d") if request.POST.get("start_date") else start_date
        end_date = datetime.datetime.strptime(request.POST.get("end_date"), "%Y-%m-%d") if request.POST.get("end_date") else end_date
        REDIS.publish("request-refresh", json.dumps({"type": f"slack-{notification_type}-notification",
                                                     "start_date": start_date.strftime("%Y-%m-%d"),
                                                     "end_date": end_date.strftime("%Y-%m-%d")}))

        messages.add_message(request, messages.INFO, f"Slack notifications for {notification_type} queued.")
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
        "unsubmitted_end_date": end_date,
        "unsubmitted_start_date": start_date,
        "unapproved_end_date": end_date,
        "unapproved_start_date": start_date,
    }
    return render(request, "queue_slack_notifications.html", context)


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
def get_invoice_xls(request, invoice_id, xls_type):  # pylint:disable=unused-argument
    if xls_type == "hours":
        xls, title = generate_hours_xls_for_invoice(invoice_id)
    else:
        return HttpResponseBadRequest("Invalid XLS type")

    response = HttpResponse(xls, content_type="application/vnd.ms-excel")
    response["Content-Disposition"] = f"attachment; filename=\"Hours for {title}.xlsx\""
    return response


@login_required
def get_invoice_pdf(request, invoice_id, pdf_type):
    if pdf_type == "hours":
        pdf, title = generate_hours_pdf_for_invoice(request, invoice_id)
    else:
        return HttpResponseBadRequest("Invalid PDF type")

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f"attachment; filename=\"Hours for {title}.pdf\""
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
            entries = HourEntry.objects.filter(user_m=user).filter(status="Unsubmitted").filter(upstream_id__in=ids).exclude(invoice__project_m__archived=True).exclude(incurred_hours=0).exclude(updated_at=None).filter(date__gte=datetime.date.today() - datetime.timedelta(days=60))
            tenkfeet_api = TenkFeetApi(settings.TENKFEET_AUTH)
            update_entries = []
            for entry in entries:
                updated_at = entry.updated_at.isoformat().replace("+00:00", "Z")
                update_entries.append({
                    "id": entry.upstream_id,
                    "updated_at": updated_at
                })
            response = tenkfeet_api.submit_hours(update_entries)
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

    unsubmitted_entries = HourEntry.objects.filter(user_m=user).filter(status="Unsubmitted").exclude(invoice__project_m__archived=True).exclude(incurred_hours=0).order_by("-date")
    return render(request, "hours/unsubmitted.html", {"person": user, "unsubmitted_entries": unsubmitted_entries, "ids": ",".join(str(entry.upstream_id) for entry in unsubmitted_entries if entry.can_submit_automatically)})


@login_required
def frontpage_stats(request):
    return JsonResponse(hours_overview_stats(request.user.email))


@login_required
def invoices_list(request):
    all_invoices = Invoice.objects.exclude(Q(incurred_hours=0) & Q(incurred_money=0)).exclude(project_m__project_state="Internal").exclude(project_m__client_m__name__in=["Solinor", "[none]"]).select_related("project_m", "project_m__client_m").prefetch_related("project_m__admin_users")
    filters = InvoiceFilter(request.GET, queryset=all_invoices)
    table = InvoicesTable(filters.qs)
    RequestConfig(request, paginate={
        "per_page": 100
    }).configure(table)
    try:
        last_update_finished_at = REDIS.get("last-data-update").decode()
    except TypeError:
        last_update_finished_at = "?"
    last_update_finished_at = parse_datetime(last_update_finished_at) or "?"
    context = {
        "invoices": table,
        "filters": filters,
        "last_update_finished_at": last_update_finished_at,
    }
    return render(request, "invoices/list.html", context)


@login_required
def clients_list(request):
    clients = Client.objects.annotate().annotate(incurred_money=Sum("project__invoice__incurred_money"), incurred_hours=Sum("project__invoice__incurred_hours")).exclude(incurred_hours=0)
    filters = ClientsFilter(request.GET, queryset=clients)
    table = ClientsTable(filters.qs)
    RequestConfig(request, paginate={
        "per_page": 250
    }).configure(table)
    return render(request, "clients/list.html", {"clients": table, "filters": filters})


@login_required
def client_details(request, client_id):
    client = get_object_or_404(Client, id=client_id)

    all_invoices = Invoice.objects.exclude(Q(incurred_hours=0) & Q(incurred_money=0)).filter(project_m__client_m=client).select_related("project_m", "project_m__client_m").prefetch_related("project_m__admin_users")
    invoice_filters = InvoiceFilter(request.GET, queryset=all_invoices)
    invoice_table = InvoicesTable(invoice_filters.qs)
    RequestConfig(request, paginate={
        "per_page": 100
    }).configure(invoice_table)

    projects = Project.objects.filter(client_m=client).annotate(incurred_money=Sum("invoice__incurred_money"), incurred_hours=Sum("invoice__incurred_hours")).exclude(incurred_hours=0).select_related("client_m").prefetch_related("admin_users")
    project_filters = ProjectsFilter(request.GET, queryset=projects)
    projects_table = ProjectsTable(project_filters.qs)
    RequestConfig(request, paginate={
        "per_page": 250
    }).configure(projects_table)

    return render(request, "clients/details.html", {"client": client, "project_filters": project_filters, "projects": projects_table, "invoice_filters": invoice_filters, "invoices": invoice_table})


@login_required
def clientbase_stats(request):
    sorting = request.GET.get("sorting", "workdays_fte_avg")
    active_field = request.GET.get("field", None)
    context = calculate_clientbase_stats(sorting, active_field)
    return render(request, "clients/stats.html", context)


@login_required
def frontpage(request):
    today = datetime.date.today()
    last_month = (today.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
    your_invoices = Invoice.objects.exclude(Q(incurred_hours=0) & Q(incurred_money=0)).filter(project_m__admin_users__email=request.user.email).filter(date=last_month).exclude(project_m__client_m__name__in=["Solinor", "[none]"]).select_related("project_m", "project_m__client_m")
    sorting = request.GET.get("sorting", "billing")

    cache_key = f"frontpage-cards-sorting-{sorting}"
    cached_data = REDIS.get(cache_key)
    if cached_data:
        cards = pickle.loads(cached_data)
    else:
        active_invoices = Invoice.objects.exclude(Q(incurred_hours=0) & Q(incurred_money=0)).exclude(project_m__project_state="Internal").exclude(project_m__client_m__name__in=["Solinor", "[none]"]).filter(date__gte=last_month).exclude(project_m=None).select_related("project_m", "project_m__client_m")
        projects = [invoice.project_m for invoice in active_invoices]
        projects_map = {invoice.project_m.guid: (invoice.project_m, invoice) for invoice in active_invoices}
        billing = defaultdict(dict)
        for item in HourEntry.objects.filter(invoice__project_m__in=projects).filter(date__gte=last_month).filter(date__lte=today).values("invoice__project_m__guid", "date").order_by("invoice__project_m__guid", "date").annotate(hours=Sum("incurred_hours")).annotate(money=Sum("incurred_money")):
            billing[item["invoice__project_m__guid"]][item["date"]] = (item["hours"], item["money"])

        people_entries = defaultdict(lambda: defaultdict(set))
        for item in HourEntry.objects.filter(invoice__project_m__in=projects).filter(date__gte=last_month).filter(date__lte=today).values("invoice__project_m__guid", "date", "user_email").order_by("invoice__project_m__guid", "date", "user_email"):
            people_entries[item["invoice__project_m__guid"]][item["date"]].add(item["user_email"])

        cards = []
        for project, invoice in projects_map.values():
            hours = []
            money = []
            people = []
            people_workdays_sum = workdays_count = 0
            for date in daterange(last_month, today):
                if date in billing[project.guid]:
                    hours.append(billing[project.guid][date][0] or 0)
                    money.append(billing[project.guid][date][1] or 0)
                else:
                    hours.append(0)
                    money.append(0)
                if date in people_entries[project.guid]:
                    people.append(len(people_entries[project.guid][date]))
                else:
                    people.append(0)
                if date.isoweekday() < 6:
                    people_workdays_sum += people[-1]
                    workdays_count += 1
            hours_sum = sum(hours)
            money_sum = sum(money)

            cards.append({
                "project": project,
                "invoice": invoice,
                "hours": hours[-45:],
                "money": money[-45:],
                "people": people[-45:],
                "hours_sum": hours_sum,
                "money_sum": money_sum,
                "people_avg": float(people_workdays_sum) / workdays_count,
            })

        if sorting == "alphabetically":
            cards = sorted(cards, key=lambda k: k["project"].full_name)
        if sorting == "hours":
            cards = sorted(cards, key=lambda k: k["hours_sum"], reverse=True)
        if sorting == "billing":
            cards = sorted(cards, key=lambda k: k["money_sum"], reverse=True)
        REDIS.setex(cache_key, pickle.dumps(cards), 120)

    context = {
        "your_invoices": your_invoices,
        "cards": cards,
    }
    return render(request, "frontpage.html", context)


@login_required
def invoice_hours(request, invoice_id):
    invoice = get_object_or_404(Invoice, invoice_id=invoice_id)
    entries = HourEntry.objects.exclude(status="Unsubmitted").filter(invoice=invoice).filter(incurred_hours__gt=0).select_related("user_m")

    previous_invoices = []
    if invoice.project_m:
        previous_invoices = Invoice.objects.filter(project_m=invoice.project_m)

    context = {
        "invoice": invoice,
        "entries": entries,
        "previous_invoices": previous_invoices,
        "recent_invoice": abs((datetime.date.today() - invoice.date).days) < 60,
    }
    return render(request, "invoices/hours.html", context)


@login_required
def projects_list(request):
    projects = Project.objects.annotate(incurred_money=Sum("invoice__incurred_money"), incurred_hours=Sum("invoice__incurred_hours")).exclude(incurred_hours=0).select_related("client_m").prefetch_related("admin_users")
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
    return render(request, "projects/list.html", context)


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
    return render(request, "projects/details.html", context)


@login_required
def hours_charts(request):
    treemaps = []
    linecharts = []
    calendar_charts = []
    year_ago = (datetime.date.today() - datetime.timedelta(days=365)).replace(month=1, day=1)
    treemaps.append(gen_treemap_data_projects(HourEntry.objects.exclude(status="Unsubmitted")))
    treemaps.append(gen_treemap_data_projects(HourEntry.objects.exclude(status="Unsubmitted").filter(calculated_is_billable=True), "incurred_money", "Gross income per project"))
    treemaps.append(gen_treemap_data_users(HourEntry.objects.exclude(status="Unsubmitted")))
    treemaps.append(gen_treemap_data_users(HourEntry.objects.exclude(status="Unsubmitted").filter(calculated_is_billable=True), "incurred_money", "Gross income per person"))

    entries = HourEntry.objects.exclude(status="Unsubmitted").filter(date__gte=year_ago).order_by("date").values("date").annotate(hours=Sum("incurred_hours"))
    hours_calendar_data = [(entry["date"].year, entry["date"].month - 1, entry["date"].day, entry["hours"], "{:.2f}h".format(entry["hours"])) for entry in entries]
    entries = HourEntry.objects.exclude(status="Unsubmitted").filter(date__gte=year_ago).filter(calculated_is_billable=True).order_by("date").values("date").annotate(money=Sum("incurred_money"))
    money_calendar_data = [(entry["date"].year, entry["date"].month - 1, entry["date"].day, entry["money"], "{:.2f}€".format(entry["money"])) for entry in entries if entry["money"] > 0]

    calendar_charts.append(("hours_calendar", "Incurred hours per day", "Hours", hours_calendar_data))
    calendar_charts.append(("money_calendar", "Incurred billing per day", "Money", money_calendar_data))

    entries = HourEntry.objects.exclude(status="Unsubmitted").filter(date__gte=year_ago).filter(calculated_is_billable=True).annotate(month=TruncMonth("date")).order_by("month").values("month").annotate(hours=Sum("incurred_hours")).annotate(money=Sum("incurred_money")).values("month", "hours", "money")
    monthly_avg_billing = [["Date", "Bill rate avg"]] + [["{}-{}".format(entry["month"].year, entry["month"].month), entry["money"] / entry["hours"]] for entry in entries]
    linecharts.append(("billing_rate_avg", "Billing rate avg (billable hours)", json.dumps(monthly_avg_billing)))

    entries = HourEntry.objects.exclude(status="Unsubmitted").filter(date__gte=year_ago).filter(calculated_is_billable=True).annotate(month=TruncMonth("date")).order_by("month").values("month").annotate(hours=Sum("incurred_hours")).annotate(money=Sum("incurred_money")).values("month", "hours", "money")
    money_per_month_data = [["Date", "Gross income (billing)"]] + [["{}-{}".format(entry["month"].year, entry["month"].month), entry["money"]] for entry in entries]
    linecharts.append(("incurred_money", "Gross income (billing) per month", json.dumps(money_per_month_data)))
    entries = HourEntry.objects.exclude(status="Unsubmitted").filter(date__gte=year_ago).annotate(month=TruncMonth("date")).order_by("month").values("month").annotate(hours=Sum("incurred_hours")).annotate(money=Sum("incurred_money")).values("month", "hours", "money")
    hours_per_month_data = [["Date", "Incurred hours"]] + [["{}-{}".format(entry["month"].year, entry["month"].month), entry["hours"]] for entry in entries]
    linecharts.append(("incurred_hours", "Incurred hours per month", json.dumps(hours_per_month_data)))
    return render(request, "hours/charts.html", {"treemap_charts": treemaps, "line_charts": linecharts, "calendar_charts": calendar_charts})


@login_required
def users_charts(request):
    linecharts = []
    calendar_charts = []
    year_ago = (datetime.date.today() - datetime.timedelta(days=365)).replace(month=1, day=1)

    entries = HourEntry.objects.exclude(status="Unsubmitted").filter(date__gte=year_ago).filter(leave_type__in=["Annual holiday", "Flex time Leave", "Other paid leave", "Parental leave", "Unpaid leave", "Vuosiloma"]).order_by("date").values("date").annotate(hours=Count("incurred_hours"))
    hours_calendar_data = [(entry["date"].year, entry["date"].month - 1, entry["date"].day, entry["hours"], "{:.2f}h".format(entry["hours"])) for entry in entries]
    calendar_charts.append(("annual_holiday_calendar", "People enjoying holidays per day", "People", hours_calendar_data))

    entries = HourEntry.objects.exclude(status="Unsubmitted").filter(date__gte=year_ago).filter(leave_type="Sick leave").order_by("date").values("date").annotate(hours=Count("incurred_hours"))
    hours_calendar_data = [(entry["date"].year, entry["date"].month - 1, entry["date"].day, entry["hours"], "{:.2f}h".format(entry["hours"])) for entry in entries]
    calendar_charts.append(("sick_leaves_calendar", "People on sick leave per day", "People", hours_calendar_data))

    return render(request, "users/charts.html", {"calendar_charts": calendar_charts, "line_charts": linecharts})


@login_required
def hours_overview(request):
    today = datetime.date.today()
    period_start = today - datetime.timedelta(days=30)
    hour_markings = HourEntry.objects.exclude(status="Unsubmitted").filter(date__gte=period_start).exclude(user_m=None).values("user_m__guid", "user_name", "date").annotate(hours=Sum("incurred_hours"))
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
    return render(request, "hours/overview.html", {"people": people, "days": days, "today": today})


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

    entries = HourEntry.objects.exclude(status="Unsubmitted").filter(invoice__project_m=project).filter(calculated_is_billable=True).annotate(month=TruncMonth("date")).order_by("month").values("month").annotate(hours=Sum("incurred_hours")).annotate(money=Sum("incurred_money")).values("month", "hours", "money")
    monthly_avg_billing = [["Date", "Bill rate avg"]] + [["{}-{}".format(entry["month"].year, entry["month"].month), entry["money"] / entry["hours"]] for entry in entries]
    linecharts.append(("billing_rate_avg", "Billing rate avg", json.dumps(monthly_avg_billing)))
    money_per_month_data = [["Date", "Gross income"]] + [["{}-{}".format(entry["month"].year, entry["month"].month), entry["money"]] for entry in entries]
    linecharts.append(("incurred_money", "Gross income per month", json.dumps(money_per_month_data)))
    entries = HourEntry.objects.exclude(status="Unsubmitted").filter(invoice__project_m=project).annotate(month=TruncMonth("date")).order_by("month").values("month").annotate(hours=Sum("incurred_hours")).annotate(money=Sum("incurred_money")).values("month", "hours", "money")
    hours_per_month_data = [["Date", "Incurred hours"]] + [["{}-{}".format(entry["month"].year, entry["month"].month), entry["hours"]] for entry in entries]
    linecharts.append(("incurred_hours", "Incurred hours per month", json.dumps(hours_per_month_data)))

    return render(request, "projects/charts.html", {"calendar_charts": calendar_charts, "project": project, "line_charts": linecharts})


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
            "queryset": HourEntry.objects.exclude(status="Unsubmitted").values_list("category").annotate(hours=Sum("incurred_hours")),
            "callback": get_chart_data,
            "title": "Incurred hours per category",
        },
        "per_category_billing": {
            "queryset": HourEntry.objects.exclude(status="Unsubmitted").values_list("category").filter(calculated_is_billable=True).annotate(hours=Sum("incurred_money")),
            "callback": get_chart_data,
            "title": "Incurred billing per category",
        },
        "per_person_hours": {
            "queryset": HourEntry.objects.exclude(status="Unsubmitted").values_list("user_name").annotate(hours=Sum("incurred_hours")),
            "callback": get_chart_data,
            "title": "Incurred hours per person",
        },
        "per_person_billing": {
            "queryset": HourEntry.objects.exclude(status="Unsubmitted").values_list("user_name").filter(calculated_is_billable=True).annotate(hours=Sum("incurred_money")),
            "callback": get_chart_data,
            "title": "Incurred billing per person",
        },
    }
    for chart_name in charts:
        chart_data = charts[chart_name]
        chart_data["queryset"] = chart_data["queryset"].filter(invoice=invoice).filter(date__gte=first_day).filter(date__lte=last_day)
        chart_data["data"] = chart_data["callback"](chart_data["queryset"])
        chart_data["json_data"] = json.dumps(chart_data["data"])

    per_person_categories = get_2d_chart_data(HourEntry.objects.exclude(status="Unsubmitted").values_list("user_name", "category").annotate(hours=Sum("incurred_hours")).filter(invoice=invoice).filter(date__gte=first_day).filter(date__lte=last_day))

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
    return render(request, "invoices/charts.html", context)


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

    entries = HourEntry.objects.exclude(status="Unsubmitted").filter(invoice=invoice).filter(incurred_hours__gt=0)
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
        "recent_invoice": abs((datetime.date.today() - invoice.date).days) < 60,
    }
    context.update(entry_data)

    previous_month = (invoice.date - datetime.timedelta(days=1)).replace(day=1)
    try:
        last_month_invoice = Invoice.objects.get(project_m=invoice.project_m, date=previous_month)
        context["last_month_invoice"] = last_month_invoice
        context["diff_last_month"] = last_month_invoice.compare(invoice)
    except Invoice.DoesNotExist:
        pass

    return render(request, "invoices/details.html", context)


@login_required
@permission_required("invoices.can_run_sync")
def admin_sync(request):
    sync_commands = {
        "sync_public_holidays": sync_public_holidays,
        "sync_10000ft_users": sync_10000ft_users,
        "sync_10000ft_projects": sync_10000ft_projects,
        "sync_slack_channels": sync_slack_channels,
        "sync_slack_users": sync_slack_users,
    }
    if request.method == "POST":
        action = request.POST.get("action")
        if not action:
            return HttpResponseBadRequest("No action specified")
        if action not in sync_commands:
            return HttpResponseBadRequest("Invalid action")
        sync_commands[action]()

    events = Event.objects.all()[:100]
    return render(request, "admin_sync.html", {"events": events})
