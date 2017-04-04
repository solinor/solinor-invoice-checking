from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseForbidden
import datetime
from invoices.models import HourEntry, Invoice, Comments, calculate_entry_stats
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from invoices.filters import InvoiceFilter
from django.conf import settings
import requests
import os

def pdf_plain(request, year, month, invoice, pdf_type, pdf_auth):
    if pdf_auth != settings.PDF_AUTH:
        return HttpResponseForbidden("Incorrect authentication token")
    invoice_data = get_object_or_404(Invoice, id=invoice)
    entries = HourEntry.objects.filter(project=invoice_data.project, client=invoice_data.client, date__year__gte=year, date__month=month).filter(incurred_hours__gt=0)
    return render(request, "pdf_template.html", {"entries": entries})

@login_required
def get_pdf(request, year, month, invoice, pdf_type):
    invoice_data = get_object_or_404(Invoice, id=invoice)
    title = "%s - %s - %s-%s" % (invoice_data.client, invoice_data.project, invoice_data.year, invoice_data.month)
    local_url = request.build_absolute_uri("/").rstrip("/") + reverse("pdf_plain", args=(year, month, invoice, pdf_type, settings.PDF_AUTH))
    data = requests.get('https://webtopdf.expeditedaddons.com/?api_key=%s&content=%s&html_width=2048&margin=10&title=%s' % (os.environ['WEBTOPDF_API_KEY'], local_url, "Hours for %s" % title))
    response = HttpResponse(data.content, content_type="application/pdf")
    response['Content-Disposition'] = 'attachment; filename="Hours for %s.pdf"' % title
    return response

@login_required
def frontpage(request):
    last_month = datetime.date.today().replace(day=1) - datetime.timedelta(days=1)
    f = InvoiceFilter(request.GET, queryset=Invoice.objects.all())
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
    }
    context.update(entry_data)

    return render(request, "invoice_page.html", context)
