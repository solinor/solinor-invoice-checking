# -*- coding: utf-8 -*-

import datetime
import redis
import json
import calendar

from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseBadRequest, Http404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.conf import settings
from django.utils import timezone
from django.db.models import Count, Sum

from django_tables2 import MultiTableMixin, RequestConfig, SingleTableView

from invoices.models import HourEntry, Invoice, Comments, calculate_entry_stats, DataUpdate, FeetUser, Project, AuthToken, InvoiceFixedEntry, ProjectFixedEntry
from invoices.filters import InvoiceFilter, ProjectsFilter, CustomerHoursFilter
from invoices.pdf_utils import generate_hours_pdf_for_invoice
from invoices.tables import *

REDIS = redis.from_url(settings.REDIS)


def validate_auth_token(auth_token):
    token = get_object_or_404(AuthToken, token=auth_token)
    if token.valid_until:
        if token.valid_until > timezone.now():
            raise Http404()
    return token


def customer_view(request, auth_token):
    token = validate_auth_token(auth_token)
    invoices = Invoice.objects.filter(project_m=token.project).filter(total_hours__gt=0)
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
    invoice_data = calculate_entry_stats(hours, fixed_invoice_rows)

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
def person_details(request, year, month, user_guid):
    year = int(year)
    month = int(month)
    person = get_object_or_404(FeetUser, guid=user_guid)
    entries = HourEntry.objects.filter(user_m=person).exclude(incurred_hours=0).filter(date__year=year, date__month=month).order_by("date")
    if len(entries) > 0:
        user_name = entries[0].user_name
    else:
        user_name = user_email
    return render(request, "person.html", {"person": person, "hour_entries": entries, "stats": calculate_entry_stats(entries)})


@login_required
def people_list(request):
    now = timezone.now()
    year = int(request.GET.get("year", now.year))
    month = int(request.GET.get("month", now.month))
    people_data = {}
    for person in FeetUser.objects.filter(archived=False):
        people_data[person.email] = {"billable": {"incurred_hours": 0, "incurred_money": 0}, "non-billable": {"incurred_hours": 0, "incurred_money": 0},  "person": person, "issues": 0}
    for entry in HourEntry.objects.exclude(incurred_hours=0).filter(date__year=year, date__month=month).exclude(project="[Leave Type]"):
        if entry.user_email not in people_data:
            continue  # TODO: logging
        if entry.calculated_is_billable:
            k = "billable"
        else:
            k = "non-billable"
        people_data[entry.user_email][k]["incurred_hours"] += entry.incurred_hours
        people_data[entry.user_email][k]["incurred_money"] += entry.incurred_money
        if not entry.calculated_has_notes or not entry.calculated_has_phase:
            people_data[entry.user_email]["issues"] += 1
    for person in people_data.values():
        total_hours = person["billable"]["incurred_hours"] + person["non-billable"]["incurred_hours"]
        person["total_hours"] = total_hours
        if total_hours > 0:
            person["invoicing_ratio"] = person["billable"]["incurred_hours"] / total_hours * 100
            person["bill_rate_avg"] = person["billable"]["incurred_money"] / total_hours
        if person["billable"]["incurred_hours"] > 0:
            person["bill_rate_avg_billable"] = person["billable"]["incurred_money"] / person["billable"]["incurred_hours"]
    return render(request, "people.html", {"people": people_data, "year": year, "month": month})

def parse_date(date_string):
    return datetime.datetime.strptime(date_string, "%Y-%m-%d").date()

@login_required
def queue_update(request):
    if request.method == "POST":
        return_url = request.POST.get("back") or reverse("frontpage")
        start_date = parse_date(request.POST.get("start_date", datetime.datetime.now().strftime("%Y-%m-%d")))
        end_date = parse_date(request.POST.get("end_date", (datetime.datetime.now() - datetime.timedelta(days=60)).strftime("%Y-%m-%d")))
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
def get_pdf(request, invoice, pdf_type):
    if pdf_type == "hours":
        pdf, title = generate_hours_pdf_for_invoice(request, invoice)
    else:
        return HttpResponseBadRequest("Invalid PDF type")

    response = HttpResponse(pdf, content_type="application/pdf")
    response['Content-Disposition'] = u'attachment; filename="Hours for %s.pdf"' % title
    return response

@login_required
def frontpage(request):
    last_month = datetime.date.today().replace(day=1) - datetime.timedelta(days=1)
    all_invoices = Invoice.objects.exclude(total_hours=0).exclude(client__in=["Solinor", "[none]"])
    filters = InvoiceFilter(request.GET, queryset=all_invoices)
    table = FrontpageInvoices(filters.qs)
    RequestConfig(request, paginate={
        'per_page': 250
    }).configure(table)
    your_invoices = Invoice.objects.exclude(total_hours=0).filter(tags__icontains="%s %s" % (request.user.first_name, request.user.last_name)).filter(year=last_month.year).filter(month=last_month.month).exclude(client__in=["Solinor", "[none]"])
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
def invoice_hours(request, invoice):
    invoice_data = get_object_or_404(Invoice, invoice_id=invoice)
    entries = HourEntry.objects.filter(invoice=invoice_data).filter(incurred_hours__gt=0)
    context = {
        "invoice": invoice_data,
        "entries": entries,
    }
    return render(request, "invoice_hours.html", context)


@login_required
def projects_list(request):
    projects = Project.objects.exclude(client="Solinor").annotate(incurred_money=Sum("invoice__total_money"), incurred_hours=Sum("invoice__total_hours")).exclude(incurred_hours=0)
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

    projects_processed = []
    for i, project in enumerate(projects):
        if project.incurred_hours and project.incurred_hours > 0 and project.incurred_money:
            project.bill_rate_avg = project.incurred_money / project.incurred_hours
    for i, project in enumerate(filters.qs):
        if project.incurred_hours and project.incurred_hours > 0 and project.incurred_money:
            project.bill_rate_avg = project.incurred_money / project.incurred_hours
    context = {
        "projects": filters,
    }
    return render(request, "projects.html", context)

@login_required
def project_details(request, project_id):
    project = get_object_or_404(Project, guid=project_id)
    invoices = Invoice.objects.filter(project_m=project).exclude(total_hours=0)
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
def invoice_page(request, invoice, **_):
    invoice_data = get_object_or_404(Invoice, invoice_id=invoice)

    if request.method == "POST":
        invoice_number = request.POST.get("invoiceNumber") or None
        if invoice_number:
            invoice_number = invoice_number.strip()
        comment = Comments(comments=request.POST.get("changesForInvoice"),
                           checked=request.POST.get("invoiceChecked", False),
                           checked_non_billable_ok=request.POST.get("nonBillableHoursOk", False),
                           checked_bill_rates_ok=request.POST.get("billableIncorrectPriceOk", False),
                           checked_phases_ok=request.POST.get("nonPhaseSpecificOk", False),
                           checked_changes_last_month=request.POST.get("remarkableChangesOk", False),
                           invoice_number=invoice_number,
                           invoice_sent_to_customer=request.POST.get("invoiceSentToCustomer", False),
                           user=request.user.email,
                           invoice=invoice_data)
        comment.save()
        invoice_data.is_approved = comment.checked
        invoice_data.has_comments = comment.has_comments()
        invoice_sent_earlier = invoice_data.invoice_state in ("P", "S")
        invoice_data.update_state(comment)
        invoice_data.save()
        messages.add_message(request, messages.INFO, 'Saved.')
        if not invoice_sent_earlier and invoice_data.invoice_state in ("P", "S") and invoice_data.project_m:
            for project_fixed_entry in ProjectFixedEntry.objects.filter(project=invoice_data.project_m):
                if InvoiceFixedEntry.objects.filter(invoice=invoice_data, price=project_fixed_entry.price, description=project_fixed_entry.description).count() == 0:
                    InvoiceFixedEntry(invoice=invoice_data, price=project_fixed_entry.price, description=project_fixed_entry.description).save()
        if invoice_sent_earlier and invoice_data.invoice_state not in ("P", "S"):
            InvoiceFixedEntry.objects.filter(invoice=invoice_data).delete()
        return HttpResponseRedirect(reverse("invoice", args=[invoice]))

    today = datetime.date.today()
    due_date = today + datetime.timedelta(days=14)

    entries = HourEntry.objects.filter(invoice=invoice_data).filter(incurred_hours__gt=0)

    fixed_invoice_rows = list(InvoiceFixedEntry.objects.filter(invoice=invoice_data))
    if invoice_data.invoice_state not in ("P", "S") and invoice_data.project_m:
        fixed_invoice_rows.extend(list(ProjectFixedEntry.objects.filter(project=invoice_data.project_m)))
    entry_data = calculate_entry_stats(entries, fixed_invoice_rows)

    try:
        latest_comments = Comments.objects.filter(invoice=invoice_data).latest()
    except Comments.DoesNotExist:
        latest_comments = None

    month_start_date = datetime.date(invoice_data.year, invoice_data.month, 1)
    month_end_date = month_start_date.replace(day=calendar.monthrange(invoice_data.year, invoice_data.month)[1])

    context = {
        "today": today,
        "due_date": due_date,
        "client": invoice_data.client,
        "project": invoice_data.project,
        "entries": entries,
        "form_data": latest_comments,
        "year": invoice_data.year,
        "month": invoice_data.month,
        "month_start_date": month_start_date,
        "month_end_date": month_end_date,
        "invoice_id": invoice,
        "invoice": invoice_data,
        "recent_invoice": abs((datetime.date.today() - datetime.date(invoice_data.year, invoice_data.month, 1)).days) < 60,
    }
    context.update(entry_data)

    previous_invoice_month = invoice_data.month - 1
    previous_invoice_year = invoice_data.year
    if previous_invoice_month == 0:
        previous_invoice_month = 12
        previous_invoice_year -= 1
    try:
        last_month_invoice = Invoice.objects.get(project=invoice_data.project, client=invoice_data.client, year=previous_invoice_year, month=previous_invoice_month)
        context["last_month_invoice"] = last_month_invoice
        context["diff_last_month"] = last_month_invoice.compare(invoice_data)
    except Invoice.DoesNotExist:
        pass

    return render(request, "invoice_page.html", context)
