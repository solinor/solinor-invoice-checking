from django.shortcuts import render, get_object_or_404
from django.template.loader import render_to_string
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseForbidden
import datetime
from invoices.models import HourEntry, Invoice, Comments, calculate_entry_stats
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from invoices.filters import InvoiceFilter
from django.conf import settings
import requests
import os
import pdfkit

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
    your_invoices = Invoice.objects.filter(tags__icontains="%s %s" % (request.user.first_name, request.user.last_name)).filter(year=last_month.year).filter(month=last_month.month)
    context = {
        "invoices": f,
        "your_invoices": your_invoices,
    }
    return render(request, "frontpage.html", context)

@login_required
def invoice_page(request, year, month, invoice):
    invoice_data = get_object_or_404(Invoice, id=invoice)

    if request.method == "POST":

        comment = Comments(comments=request.POST.get("changesForInvoice"),
                           checked=request.POST.get("invoiceChecked"),
                           checked_non_billable_ok=request.POST.get("nonBillableHoursOk"),
                           checked_bill_rates_ok=request.POST.get("billableIncorrectPriceOk"),
                           checked_phases_ok=request.POST.get("nonPhaseSpecificOk"),
                           checked_changes_last_month=request.POST.get("remarkableChangesOk"),
                           user=request.user.email,
                           invoice=invoice_data)
        comment.save()
        invoice_data.is_approved = comment.checked
        invoice_data.has_comments = comment.has_comments()
        invoice_data.save()
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
