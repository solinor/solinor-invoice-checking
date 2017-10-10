# -*- coding: utf-8 -*-

import datetime
import json
import copy
from collections import defaultdict

import redis


from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseBadRequest, Http404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.conf import settings
from django.utils import timezone
from django.db.models import Count, Sum, Q
from django.db.models.functions import TruncMonth

from django_tables2 import RequestConfig

from invoices.models import HourEntry, Invoice, WeeklyReport, Comments, DataUpdate, FeetUser, Project, AuthToken, InvoiceFixedEntry, ProjectFixedEntry, AmazonInvoiceRow, AmazonLinkedAccount
from invoices.filters import InvoiceFilter, ProjectsFilter, CustomerHoursFilter, HourListFilter
from invoices.pdf_utils import generate_hours_pdf_for_invoice
from invoices.tables import HourListTable, CustomerHoursTable, FrontpageInvoices, ProjectsTable, ProjectDetailsTable
from invoices.invoice_utils import generate_amazon_invoice_data, calculate_entry_stats, get_aws_entries
import invoices.date_utils as date_utils
from invoices.chart_utils import gen_treemap_data_projects, gen_treemap_data_users

REDIS = redis.from_url(settings.REDIS)


def validate_auth_token(auth_token):
    token = get_object_or_404(AuthToken, token=auth_token)
    if token.valid_until:
        if token.valid_until > timezone.now():
            raise Http404()
    return token

@login_required
def amazon_overview(request):
    today = datetime.date.today()
    aws_accounts = AmazonLinkedAccount.objects.all().prefetch_related("project_set", "feetuser_set")
    linked_accounts = sum([aws_account.has_linked_properties() for aws_account in aws_accounts])
    total_billing = linked_billing = unlinked_billing = employee_billing = project_billing = 0

    for aws_account in aws_accounts:
        aws_account.billing = aws_account.billing_for_month(today.year, today.month)
        total_billing += aws_account.billing

        if aws_account.has_linked_properties():
            linked_billing += aws_account.billing
            if aws_account.project_set.all().count() > 0:
                project_billing += aws_account.billing
            if aws_account.feetuser_set.all().count() > 0:
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
        ("Unlinked accounts", AmazonLinkedAccount.objects.all().count() - linked_accounts),
    )
    context = {
        "today": today,
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
    invoice_data = generate_amazon_invoice_data(linked_account, invoice_rows, year, month)
    months = AmazonInvoiceRow.objects.filter(linked_account=linked_account).dates("invoice_month", "month", order="DESC")
    linked_projects = linked_account.project_set.all()
    linked_users = linked_account.feetuser_set.all()
    context = {"year": year, "month": month, "months": months, "linked_account": linked_account, "linked_users": linked_users, "linked_projects": linked_projects}
    context.update(invoice_data)

    return render(request, "amazon_invoice.html", context)


@login_required
def hours_list(request):
    if not request.GET:
        today = datetime.date.today()
        month_start_date = date_utils.month_start_date(today.year, today.month)
        month_end_date = date_utils.month_end_date(today.year, today.month)
        return HttpResponseRedirect("%s?date__gte=%s&date__lte=%s" % (reverse("hours_list"), month_start_date, month_end_date))
    hours = HourEntry.objects.filter(incurred_hours__gt=0).exclude(project="[Leave Type]").select_related("user_m", "project_m")
    filters = HourListFilter(request.GET, queryset=hours)
    table = HourListTable(filters.qs)
    RequestConfig(request, paginate={
        'per_page': 250
    }).configure(table)

    context = {
        "table": table,
        "filters": filters,
    }

    return render(request, "all_hours.html", context=context)


def customer_view(request, auth_token):
    token = validate_auth_token(auth_token)
    invoices = Invoice.objects.filter(project_m=token.project).filter(incurred_hours__gt=0)
    context = {
        "project": token.project,
        "invoices": invoices,
        "auth_token": auth_token,
    }
    return render(request, "customer_main.html", context)

def customer_view_invoice(request, auth_token, year, month):
    token = validate_auth_token(auth_token)
    year = int(year)
    month = int(month)
    invoice = get_object_or_404(Invoice, year=year, month=month, project_m=token.project)
    hours = HourEntry.objects.filter(project_m=token.project).filter(incurred_hours__gt=0).filter(date__year=year, date__month=month).order_by("date")
    fixed_invoice_rows = list(InvoiceFixedEntry.objects.filter(invoice=invoice))
    if invoice.invoice_state not in ("P", "S"):
        fixed_invoice_rows.append(list(ProjectFixedEntry.objects.filter(project=token.project)))
    invoice_data = calculate_entry_stats(hours, invoice.get_fixed_invoice_rows())

    today = datetime.date.today()

    context = {
        "project": token.project,
        "invoice": invoice,
        "auth_token": auth_token,
        "month": month,
        "year": year,
        "due_date": "Invoice preview",
        "today": "Invoice preview",
        "customer_preview": True,
        "current_month": year == today.year and month == today.month,
    }
    context.update(invoice_data)
    return render(request, "customer_invoice.html", context)


def customer_view_hours(request, auth_token, year, month):
    token = validate_auth_token(auth_token)
    year = int(year)
    month = int(month)
    hours = HourEntry.objects.filter(project_m=token.project).filter(incurred_hours__gt=0).filter(date__year=year, date__month=month).order_by("date")
    filters = CustomerHoursFilter(request.GET, queryset=hours)
    table = CustomerHoursTable(filters.qs)
    RequestConfig(request, paginate={
        'per_page': 250
    }).configure(table)

    today = datetime.date.today()

    context = {
        "project": token.project,
        "auth_token": auth_token,
        "year": year,
        "month": month,
        "table": table,
        "filters": filters,
        "current_month": year == today.year and month == today.month,
    }
    return render(request, "customer_hours.html", context)


@login_required
def person_details(request, user_guid):
    person = get_object_or_404(FeetUser, guid=user_guid)
    year_ago = (datetime.date.today() - datetime.timedelta(days=365)).replace(day=1, month=1)
    entries = person.hourentry_set
    filters = request.GET.get("filters", "").split(",")
    if "exclude_leaves" in filters:
        entries = entries.exclude(client="[none]")
    if "exclude_nonbillable" in filters:
        entries = entries.exclude(calculated_is_billable=False)

    entries = entries.filter(date__gte=year_ago).order_by("date").values("date").annotate(hours=Sum("incurred_hours")).annotate(money=Sum("incurred_money"))

    calendar_charts = []
    hours_calendar_data = [("new Date(%s, %s, %s)" % (entry["date"].year, entry["date"].month - 1, entry["date"].day), entry["hours"]) for entry in entries]
    money_calendar_data = [("new Date(%s, %s, %s)" % (entry["date"].year, entry["date"].month - 1, entry["date"].day), entry["money"]) for entry in entries]
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
    person = get_object_or_404(FeetUser, guid=user_guid)
    entries = person.hourentry_set.exclude(incurred_hours=0).filter(date__year=year, date__month=month).select_related("project_m", "user_m").order_by("date")
    months = HourEntry.objects.filter(user_m=person).exclude(incurred_hours=0).dates("date", "month", order="DESC")
    return render(request, "person.html", {"person": person, "hour_entries": entries, "months": months, "month": month, "year": year, "stats": calculate_entry_stats(entries, [])})


@login_required
def people_list(request):
    now = timezone.now()
    year = int(request.GET.get("year", now.year))
    month = int(request.GET.get("month", now.month))
    people_data = {}
    for person in FeetUser.objects.filter(archived=False):
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

@login_required
def queue_update(request):
    if request.method == "POST":
        return_url = request.POST.get("back") or reverse("frontpage")
        end_date = parse_date(request.POST.get("end_date", datetime.datetime.now().strftime("%Y-%m-%d")))
        start_date = parse_date(request.POST.get("start_date", (datetime.datetime.now() - datetime.timedelta(days=60)).strftime("%Y-%m-%d")))
        try:
            now = timezone.now()
            last_update_at = DataUpdate.objects.exclude(aborted=True).exclude(finished_at=None).latest("finished_at")
            finished = now - last_update_at.finished_at
            if finished < datetime.timedelta(seconds=15):
                messages.add_message(request, messages.WARNING, 'Data was just updated. Please try again later.')
                return HttpResponseRedirect(return_url)

            running = DataUpdate.objects.exclude(aborted=True).filter(finished_at=None).exclude(started_at=None)
            if running.count() > 0 and now - running.latest().created_at < datetime.timedelta(minutes=10):
                messages.add_message(request, messages.WARNING, 'Update is currently running. Please try again later.')
                return HttpResponseRedirect(return_url)
        except DataUpdate.DoesNotExist:
            pass
        REDIS.publish("request-refresh", json.dumps({"start_date": start_date.strftime("%Y-%m-%d"), "end_date": end_date.strftime("%Y-%m-%d")}))
        update_obj = DataUpdate()
        update_obj.save()
        messages.add_message(request, messages.INFO, 'Update queued. This is normally finished within 10 seconds. Refresh the page to see new data.')
        return HttpResponseRedirect(return_url)
    return HttpResponseBadRequest()


@login_required
def get_pdf(request, invoice_id, pdf_type):
    if pdf_type == "hours":
        pdf, title = generate_hours_pdf_for_invoice(request, invoice_id)
    else:
        return HttpResponseBadRequest("Invalid PDF type")

    response = HttpResponse(pdf, content_type="application/pdf")
    response['Content-Disposition'] = u'attachment; filename="Hours for %s.pdf"' % title
    return response

@login_required
def frontpage(request):
    last_month = datetime.date.today().replace(day=1) - datetime.timedelta(days=1)
    all_invoices = Invoice.objects.exclude(Q(incurred_hours=0) & Q(incurred_money=0)).exclude(project_m__project_state="Internal").exclude(client__in=["Solinor", "[none]"])
    filters = InvoiceFilter(request.GET, queryset=all_invoices)
    table = FrontpageInvoices(filters.qs)
    RequestConfig(request, paginate={
        'per_page': 250
    }).configure(table)
    your_invoices = Invoice.objects.exclude(Q(incurred_hours=0) & Q(incurred_money=0)).filter(tags__icontains="%s %s" % (request.user.first_name, request.user.last_name)).filter(year=last_month.year).filter(month=last_month.month).exclude(client__in=["Solinor", "[none]"])
    try:
        last_update_finished_at = DataUpdate.objects.exclude(finished_at=None).latest("finished_at").finished_at
    except DataUpdate.DoesNotExist:
        last_update_finished_at = "?"
    context = {
        "invoices": table,
        "filters": filters,
        "your_invoices": your_invoices,
        "last_update_finished_at": last_update_finished_at,
    }
    return render(request, "frontpage.html", context)


@login_required
def invoice_hours(request, invoice_id):
    invoice = get_object_or_404(Invoice, invoice_id=invoice_id)
    entries = HourEntry.objects.filter(invoice=invoice).filter(incurred_hours__gt=0).select_related("user_m")
    context = {
        "invoice": invoice,
        "entries": entries,
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
        'per_page': 250
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
        'per_page': 250
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
    treemaps.append(gen_treemap_data_projects(HourEntry.objects.filter(calculated_is_billable=True), "incurred_money", "Money"))
    treemaps.append(gen_treemap_data_users(HourEntry.objects.all()))
    treemaps.append(gen_treemap_data_users(HourEntry.objects.filter(calculated_is_billable=True), "incurred_money", "Money"))

    entries = HourEntry.objects.filter(date__gte=year_ago).order_by("date").values("date").annotate(hours=Sum("incurred_hours"))
    hours_calendar_data = [("new Date(%s, %s, %s)" % (entry["date"].year, entry["date"].month - 1, entry["date"].day), entry["hours"]) for entry in entries]
    entries = HourEntry.objects.filter(date__gte=year_ago).filter(calculated_is_billable=True).order_by("date").values("date").annotate(money=Sum("incurred_money"))
    money_calendar_data = [("new Date(%s, %s, %s)" % (entry["date"].year, entry["date"].month - 1, entry["date"].day), entry["money"]) for entry in entries if entry["money"] > 0]

    calendar_charts.append(("hours_calendar", "Incurred hours per day", "Hours", hours_calendar_data))
    calendar_charts.append(("money_calendar", "Incurred billing per day", "Money", money_calendar_data))

    entries = HourEntry.objects.filter(date__gte=year_ago).filter(calculated_is_billable=True).annotate(month=TruncMonth("date")).order_by("month").values("month").annotate(hours=Sum("incurred_hours")).annotate(money=Sum("incurred_money")).values("month", "hours", "money")
    monthly_avg_billing = [["Date", "Bill rate avg"]] + [["%s-%s" % (entry["month"].year, entry["month"].month), entry["money"] / entry["hours"]] for entry in entries]
    linecharts.append(("billing_rate_avg", "Billing rate avg (billable hours)", json.dumps(monthly_avg_billing)))

    entries = HourEntry.objects.filter(date__gte=year_ago).filter(calculated_is_billable=True).annotate(month=TruncMonth("date")).order_by("month").values("month").annotate(hours=Sum("incurred_hours")).annotate(money=Sum("incurred_money")).values("month", "hours", "money")
    money_per_month_data = [["Date", "Incurred money"]] + [["%s-%s" % (entry["month"].year, entry["month"].month), entry["money"]] for entry in entries]
    linecharts.append(("incurred_money", "Incurred money per month", json.dumps(money_per_month_data)))
    entries = HourEntry.objects.filter(date__gte=year_ago).annotate(month=TruncMonth("date")).order_by("month").values("month").annotate(hours=Sum("incurred_hours")).annotate(money=Sum("incurred_money")).values("month", "hours", "money")
    hours_per_month_data = [["Date", "Incurred hours"]] + [["%s-%s" % (entry["month"].year, entry["month"].month), entry["hours"]] for entry in entries]
    linecharts.append(("incurred_hours", "Incurred hours per month", json.dumps(hours_per_month_data)))
    return render(request, "hours_charts.html", {"treemap_charts": treemaps, "line_charts": linecharts, "calendar_charts": calendar_charts})

@login_required
def people_charts(request):
    linecharts = []
    calendar_charts = []
    year_ago = (datetime.date.today() - datetime.timedelta(days=365)).replace(month=1, day=1)

    entries = HourEntry.objects.filter(date__gte=year_ago).filter(leave_type__in=["Annual holiday", "Flex time Leave", "Other paid leave", "Parental leave", "Unpaid leave", "Vuosiloma"]).order_by("date").values("date").annotate(hours=Count("incurred_hours"))
    hours_calendar_data = [("new Date(%s, %s, %s)" % (entry["date"].year, entry["date"].month - 1, entry["date"].day), entry["hours"]) for entry in entries]
    calendar_charts.append(("annual_holiday_calendar", "People enjoying holidays per day", "People", hours_calendar_data))

    entries = HourEntry.objects.filter(date__gte=year_ago).filter(leave_type="Sick leave").order_by("date").values("date").annotate(hours=Count("incurred_hours"))
    hours_calendar_data = [("new Date(%s, %s, %s)" % (entry["date"].year, entry["date"].month - 1, entry["date"].day), entry["hours"]) for entry in entries]
    calendar_charts.append(("sick_leaves_calendar", "People on sick leave per day", "People", hours_calendar_data))

    return render(request, "people_charts.html", {"calendar_charts": calendar_charts, "line_charts": linecharts})


@login_required
def people_hourmarkings(request):
    today = datetime.date.today()
    period_start = today - datetime.timedelta(days=30)
    hour_markings = HourEntry.objects.filter(date__gte=period_start).exclude(user_m=None).values("user_m__guid", "user_name", "date").annotate(hours=Sum("incurred_hours"))
    days = []
    d = period_start
    while True:
        days.append({"date": d, "hours": 0, "weekday": d.strftime("%a")})
        d += datetime.timedelta(days=1)
        if d > today:
            break
    people = {}
    for hour_marking in hour_markings:
        guid = hour_marking["user_m__guid"]
        if guid not in people:
            people[guid] = {"name": hour_marking["user_name"],
                            "days": copy.deepcopy(days),
                            "sum_of_hours": 0}
        for i, d in enumerate(people[guid]["days"]):
            if d["date"] == hour_marking["date"]:
                people[guid]["days"][i]["hours"] += hour_marking["hours"]
                people[guid]["sum_of_hours"] += hour_marking["hours"]
    return render(request, "people_hourmarkings.html", {"people": people, "days": days, "today": today})


@login_required
def project_charts(request, project_id):
    project = get_object_or_404(Project, guid=project_id)
    linecharts = []
    calendar_charts = []
    year_ago = (datetime.date.today() - datetime.timedelta(days=365)).replace(month=1, day=1)
    entries = project.hourentry_set.filter(date__gte=year_ago).order_by("date").values("date").annotate(hours=Sum("incurred_hours"))
    hours_calendar_data = [("new Date(%s, %s, %s)" % (entry["date"].year, entry["date"].month - 1, entry["date"].day), entry["hours"]) for entry in entries]
    entries = project.hourentry_set.filter(date__gte=year_ago).filter(calculated_is_billable=True).order_by("date").values("date").annotate(money=Sum("incurred_money"))
    money_calendar_data = [("new Date(%s, %s, %s)" % (entry["date"].year, entry["date"].month - 1, entry["date"].day), entry["money"]) for entry in entries if entry["money"] > 0]
    calendar_charts.append(("hours_calendar", "Incurred hours per day", "Hours", hours_calendar_data))
    calendar_charts.append(("money_calendar", "Incurred billing per day", "Money", money_calendar_data))


    entries = HourEntry.objects.filter(project_m=project).filter(calculated_is_billable=True).annotate(month=TruncMonth("date")).order_by("month").values("month").annotate(hours=Sum("incurred_hours")).annotate(money=Sum("incurred_money")).values("month", "hours", "money")
    monthly_avg_billing = [["Date", "Bill rate avg"]] + [["%s-%s" % (entry["month"].year, entry["month"].month), entry["money"] / entry["hours"]] for entry in entries]
    linecharts.append(("billing_rate_avg", "Billing rate avg", json.dumps(monthly_avg_billing)))
    money_per_month_data = [["Date", "Incurred money"]] + [["%s-%s" % (entry["month"].year, entry["month"].month), entry["money"]] for entry in entries]
    linecharts.append(("incurred_money", "Incurred money per month", json.dumps(money_per_month_data)))
    entries = HourEntry.objects.filter(project_m=project).annotate(month=TruncMonth("date")).order_by("month").values("month").annotate(hours=Sum("incurred_hours")).annotate(money=Sum("incurred_money")).values("month", "hours", "money")
    hours_per_month_data = [["Date", "Incurred hours"]] + [["%s-%s" % (entry["month"].year, entry["month"].month), entry["hours"]] for entry in entries]
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
        d = defaultdict(float)
        for item in queryset:
            d[item[0]] += item[1]
        d = sorted(d.items(), key=lambda k: k[0])
        return [["a", "b"]] + d

    def get_2d_chart_data(queryset):
        def per_person_dict():
            return defaultdict(float)

        d = defaultdict(per_person_dict)
        for item in queryset:
            d[item[0]][item[1]] += item[2]
        return d

    charts = {
        "per_category_hours": {
            "queryset": HourEntry.objects.values_list("category").annotate(hours=Sum("incurred_hours")),
            "callback": get_chart_data,
            "title": "Incurred hours per category",
        },
        "per_category_billing": {
            "queryset": HourEntry.objects.values_list("category").filter(calculated_is_billable=True).annotate(hours=Sum("incurred_money")),
            "callback": get_chart_data,
            "title": "Incurred money per category",
        },
        "per_person_hours": {
            "queryset": HourEntry.objects.values_list("user_name").annotate(hours=Sum("incurred_hours")),
            "callback": get_chart_data,
            "title": "Incurred hours per person",
        },
        "per_person_billing": {
            "queryset": HourEntry.objects.values_list("user_name").filter(calculated_is_billable=True).annotate(hours=Sum("incurred_money")),
            "callback": get_chart_data,
            "title": "Incurred money per person",
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
        messages.add_message(request, messages.INFO, 'Saved.')
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
    weekly_reports = []
    recent_weekly_report = None
    if invoice.project_m:
        previous_invoices = Invoice.objects.filter(project_m=invoice.project_m)
        weekly_reports = WeeklyReport.objects.filter(project_m=invoice.project_m, client=invoice.client)
        recent_weekly_report = weekly_reports[0]

    context = {
        "today": today,
        "due_date": due_date,
        "entries": entries,
        "form_data": latest_comments,
        "invoice": invoice,
        "previous_invoices": previous_invoices,
        "recent_invoice": abs((datetime.date.today() - datetime.date(invoice.year, invoice.month, 1)).days) < 60,
        "recent_weekly_report": recent_weekly_report
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

@login_required
def weekly_report_page(request, weekly_report_id, **_):
    weekly_report = get_object_or_404(WeeklyReport, weekly_report_id=weekly_report_id)

    today = datetime.date.today()
    due_date = today + datetime.timedelta(days=14)

    entries = HourEntry.objects.filter(weekly_report=weekly_report).filter(incurred_hours__gt=0)
    previous_weekly_reports = []

    if weekly_report.project_m:
        previous_weekly_reports = WeeklyReport.objects.filter(project_m=weekly_report.project_m, client=weekly_report.client)

    context = {
        "today": today,
        "due_date": due_date,
        "entries": entries,
        "weekly_report": weekly_report,
        "previous_weekly_reports": previous_weekly_reports,
    }

    return render(request, "weekly_report_page.html", context)
