from django.shortcuts import render, get_object_or_404
from django.template.loader import render_to_string
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseForbidden, HttpResponseBadRequest
import datetime
from invoices.models import HourEntry, Invoice, Comments, calculate_entry_stats, DataUpdate
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from invoices.filters import InvoiceFilter
from django.conf import settings
import requests
import os
import pdfkit
import redis
from django.contrib import messages
from django.utils import timezone


REDIS = redis.from_url(os.environ.get("REDIS_URL"))


@login_required
def person(request, year, month, user_email):
    now = timezone.now()
    year = int(year)
    month = int(month)
    entries = HourEntry.objects.filter(user_email=user_email).exclude(incurred_hours=0).filter(date__year=year, date__month=month).order_by("date")
    if len(entries) > 0:
        user_name = entries[0].user_name
    else:
        user_name = user_email
    return render(request, "person.html", {"hour_entries": entries, "user_name": user_name})


@login_required
def people(request):
    now = timezone.now()
    year = int(request.GET.get("year", now.year))
    month = int(request.GET.get("month", now.month))
    people = {}
    for entry in HourEntry.objects.exclude(incurred_hours=0).filter(date__year=year, date__month=month).exclude(project="[Leave Type]"):
        if entry.user_email not in people:
            people[entry.user_email] = {"billable": {"incurred_hours": 0, "incurred_money": 0}, "non-billable": {"incurred_hours": 0, "incurred_money": 0}, "user_name": entry.user_name, "user_email": entry.user_email}
        if entry.calculated_is_billable:
            k = "billable"
        else:
            k = "non-billable"
        people[entry.user_email][k]["incurred_hours"] += entry.incurred_hours
        people[entry.user_email][k]["incurred_money"] += entry.incurred_money
    for person in people.keys():
        total_hours = people[person]["billable"]["incurred_hours"] + people[person]["non-billable"]["incurred_hours"]
        people[person]["total_hours"] = total_hours
        if total_hours > 0:
            people[person]["invoicing_ratio"] = people[person]["billable"]["incurred_hours"] / total_hours * 100
            people[person]["bill_rate_avg"] = people[person]["billable"]["incurred_money"] / total_hours
        if people[person]["billable"]["incurred_hours"] > 0:
            people[person]["bill_rate_avg_billable"] = people[person]["billable"]["incurred_money"] / people[person]["billable"]["incurred_hours"]
    return render(request, "people.html", {"people": people, "year": year, "month": month})

@login_required
def queue_update(request):
    if request.method == "POST":
        try:
            now = timezone.now()
            last_update_at = DataUpdate.objects.exclude(aborted=True).exclude(finished_at=None).latest("finished_at")
            finished = now - last_update_at.finished_at
            if finished < datetime.timedelta(minutes=1):
                messages.add_message(request, messages.WARNING, 'Data was just updated. Please try again later.')
                return HttpResponseRedirect(reverse("frontpage"))

            running = DataUpdate.objects.exclude(aborted=True).filter(finished_at=None).exclude(started_at=None)
            if running.count() > 0 and now - running.latest().created_at < datetime.timedelta(minutes=10):
                messages.add_message(request, messages.WARNING, 'Update is currently running. Please try again later.')
                return HttpResponseRedirect(reverse("frontpage"))
        except DataUpdate.DoesNotExist:
            pass
        REDIS.publish("request-refresh", "True")
        update_obj = DataUpdate()
        update_obj.save()
        messages.add_message(request, messages.INFO, 'Update queued.')
        return HttpResponseRedirect(reverse("frontpage"))
    return HttpResponseBadRequest()


@login_required
def get_pdf(request, year, month, invoice, pdf_type):
    invoice_data = get_object_or_404(Invoice, id=invoice)
    title = "%s - %s - %s-%s" % (invoice_data.client, invoice_data.project, invoice_data.year, invoice_data.month)

    pdfkit_config = pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_CMD)
    wk_options = {
        'page-size': 'a4',
        'orientation': 'landscape',
        'title': title,
        # In order to specify command-line options that are simple toggles
        # using this dict format, we give the option the value None
        'no-outline': None,
        'disable-javascript': None,
        'encoding': 'UTF-8',
        'margin-left': '0.2cm',
        'margin-right': '0.2cm',
        'margin-top': '0.3cm',
        'margin-bottom': '0.3cm',
        'lowquality': None,
    }

    entries = HourEntry.objects.filter(project=invoice_data.project, client=invoice_data.client, date__year__gte=year, date__month=month).filter(incurred_hours__gt=0)
    phases = {}
    for entry in entries:
        if entry.phase_name not in phases:
            phases[entry.phase_name] = []
        phases[entry.phase_name].append(entry)
    context = {"phases": phases}

    # We can generate the pdf from a url, file or, as shown here, a string
    content = render_to_string('pdf_template.html', context=context, request=request)
    pdf = pdfkit.from_string(content,
        False,
        options=wk_options,
        configuration=pdfkit_config,
    )

    response = HttpResponse(pdf, content_type="application/pdf")
    response['Content-Disposition'] = 'attachment; filename="Hours for %s.pdf"' % title
    return response

@login_required
def frontpage(request):
    last_month = datetime.date.today().replace(day=1) - datetime.timedelta(days=1)
    all_invoices = Invoice.objects.exclude(total_hours=0)
    f = InvoiceFilter(request.GET, queryset=all_invoices)
    your_invoices = Invoice.objects.exclude(total_hours=0).filter(tags__icontains="%s %s" % (request.user.first_name, request.user.last_name)).filter(year=last_month.year).filter(month=last_month.month)
    try:
        last_update_finished_at = DataUpdate.objects.exclude(finished_at=None).latest("finished_at").finished_at
    except DataUpdate.DoesNotExist:
        last_update_finished_at = "?"
    context = {
        "invoices": f,
        "your_invoices": your_invoices,
        "last_update_finished_at": last_update_finished_at,
    }
    return render(request, "frontpage.html", context)

@login_required
def invoice_page(request, year, month, invoice):
    invoice_data = get_object_or_404(Invoice, id=invoice)

    if request.method == "POST":

        comment = Comments(comments=request.POST.get("changesForInvoice"),
                           checked=request.POST.get("invoiceChecked", False),
                           checked_non_billable_ok=request.POST.get("nonBillableHoursOk", False),
                           checked_bill_rates_ok=request.POST.get("billableIncorrectPriceOk", False),
                           checked_phases_ok=request.POST.get("nonPhaseSpecificOk", False),
                           checked_changes_last_month=request.POST.get("remarkableChangesOk", False),
                           user=request.user.email,
                           invoice=invoice_data)
        comment.save()
        invoice_data.is_approved = comment.checked
        invoice_data.has_comments = comment.has_comments()
        invoice_data.save()
        messages.add_message(request, messages.INFO, 'Saved.')
        return HttpResponseRedirect(reverse("invoice", args=[year, month, invoice]))

    today = datetime.datetime.today()
    due_date = today + datetime.timedelta(days=14)

    entries = HourEntry.objects.filter(project=invoice_data.project, client=invoice_data.client, date__year__gte=year, date__month=month).filter(incurred_hours__gt=0)

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
        last_month_invoice = None

    return render(request, "invoice_page.html", context)
