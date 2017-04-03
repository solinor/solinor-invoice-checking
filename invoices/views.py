from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect
import datetime
from invoices.models import HourEntry, Invoice, Comments, calculate_entry_stats
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse


@login_required
def frontpage(request):
    invoices = Invoice.objects.all()
    context = {
        "invoices": invoices
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
    }
    context.update(entry_data)

    return render(request, "invoice_page.html", context)
