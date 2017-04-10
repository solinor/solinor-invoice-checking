# -*- coding: utf-8 -*-

import datetime
import redis

from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseBadRequest
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.conf import settings
from django.utils import timezone

from invoices.models import HourEntry, Invoice, Comments, calculate_entry_stats, DataUpdate, FeetUser
from invoices.filters import InvoiceFilter
from invoices.pdf_utils import generate_hours_pdf_for_invoice

REDIS = redis.from_url(settings.REDIS)


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
    return render(request, "person.html", {"person": person, "hour_entries": entries})


@login_required
def people_list(request):
    now = timezone.now()
    year = int(request.GET.get("year", now.year))
    month = int(request.GET.get("month", now.month))
    people_data = {}
    for person in FeetUser.objects.filter(archived=False):
        people_data[person.email] = {"billable": {"incurred_hours": 0, "incurred_money": 0}, "non-billable": {"incurred_hours": 0, "incurred_money": 0},  "person": person}
    for entry in HourEntry.objects.exclude(incurred_hours=0).filter(date__year=year, date__month=month).exclude(project="[Leave Type]"):
        if entry.user_email not in people_data:
            continue  # TODO: logging
        if entry.calculated_is_billable:
            k = "billable"
        else:
            k = "non-billable"
        people_data[entry.user_email][k]["incurred_hours"] += entry.incurred_hours
        people_data[entry.user_email][k]["incurred_money"] += entry.incurred_money
    for person in people_data.values():
        total_hours = person["billable"]["incurred_hours"] + person["non-billable"]["incurred_hours"]
        person["total_hours"] = total_hours
        if total_hours > 0:
            person["invoicing_ratio"] = person["billable"]["incurred_hours"] / total_hours * 100
            person["bill_rate_avg"] = person["billable"]["incurred_money"] / total_hours
        if person["billable"]["incurred_hours"] > 0:
            person["bill_rate_avg_billable"] = person["billable"]["incurred_money"] / person["billable"]["incurred_hours"]
    return render(request, "people.html", {"people": people_data, "year": year, "month": month})

@login_required
def queue_update(request):
    if request.method == "POST":
        return_url = request.POST.get("back") or reverse("frontpage")
        try:
            now = timezone.now()
            last_update_at = DataUpdate.objects.exclude(aborted=True).exclude(finished_at=None).latest("finished_at")
            finished = now - last_update_at.finished_at
            if finished < datetime.timedelta(minutes=1):
                messages.add_message(request, messages.WARNING, 'Data was just updated. Please try again later.')
                return HttpResponseRedirect(return_url)

            running = DataUpdate.objects.exclude(aborted=True).filter(finished_at=None).exclude(started_at=None)
            if running.count() > 0 and now - running.latest().created_at < datetime.timedelta(minutes=10):
                messages.add_message(request, messages.WARNING, 'Update is currently running. Please try again later.')
                return HttpResponseRedirect(return_url)
        except DataUpdate.DoesNotExist:
            pass
        REDIS.publish("request-refresh", "True")
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
    your_invoices = Invoice.objects.exclude(total_hours=0).filter(tags__icontains="%s %s" % (request.user.first_name, request.user.last_name)).filter(year=last_month.year).filter(month=last_month.month).exclude(client__in=["Solinor", "[none]"])
    try:
        last_update_finished_at = DataUpdate.objects.exclude(finished_at=None).latest("finished_at").finished_at
    except DataUpdate.DoesNotExist:
        last_update_finished_at = "?"
    context = {
        "invoices": filters,
        "your_invoices": your_invoices,
        "last_update_finished_at": last_update_finished_at,
    }
    return render(request, "frontpage.html", context)

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
        invoice_data.update_state(comment)
        invoice_data.save()
        messages.add_message(request, messages.INFO, 'Saved.')
        return HttpResponseRedirect(reverse("invoice", args=[invoice]))

    today = datetime.date.today()
    due_date = today + datetime.timedelta(days=14)

    entries = HourEntry.objects.filter(project=invoice_data.project, client=invoice_data.client, date__year__gte=invoice_data.year, date__month=invoice_data.month).filter(incurred_hours__gt=0)

    entry_data = calculate_entry_stats(entries)


    try:
        latest_comments = Comments.objects.filter(invoice=invoice_data).latest()
    except Comments.DoesNotExist:
        latest_comments = None

    context = {
        "today": today,
        "due_date": due_date,
        "client": invoice_data.client,
        "project": invoice_data.project,
        "entries": entries,
        "form_data": latest_comments,
        "year": invoice_data.year,
        "month": invoice_data.month,
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
