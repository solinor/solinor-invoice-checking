from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect
import datetime
from invoices.models import HourEntry, Invoice, Comments
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

    entries = HourEntry.objects.filter(project=invoice_data.project, client=invoice_data.client, date__year__gte=year, date__month=month)
    phases = {}
    billable_incorrect_price = []
    non_billable_hours = []
    non_phase_specific = []
    total_hours = 0
    total_money = 0
    for entry in entries:
        if entry.phase_name not in phases:
            phases[entry.phase_name] = {}
        if entry.user_name not in phases[entry.phase_name]:
            phases[entry.phase_name][entry.user_name] = {"incurred_hours": 0, "incurred_money": 0}
        phases[entry.phase_name][entry.user_name]["incurred_hours"] += entry.incurred_hours
        phases[entry.phase_name][entry.user_name]["incurred_money"] += entry.incurred_money

        if entry.bill_rate < 50 or entry.bill_rate > 170 and entry.is_billable_phase():
            billable_incorrect_price.append(entry)

        if not entry.is_billable_phase():
            non_billable_hours.append(entry)
        total_money += entry.incurred_money
        total_hours += entry.incurred_hours
        if entry.phase_name == "[Non Phase Specific]":
            non_phase_specific.append(entry)

    try:
        latest_comments = Comments.objects.filter(invoice=invoice_data).latest()
    except Comments.DoesNotExist:
        latest_comments = None

    context = {
        "today": today,
        "due_date": due_date,
        "client": invoice_data.client,
        "project": invoice_data.project,
        "phases": phases,
        "billable_incorrect_price": billable_incorrect_price,
        "non_billable_hours": non_billable_hours,
        "total_hours": total_hours,
        "total_money": total_money,
        "entries": entries,
        "non_phase_specific": non_phase_specific,
        "billable_incorrect_price_count": len(billable_incorrect_price),
        "non_billable_hours_count": len(non_billable_hours),
        "non_phase_specific_count": len(non_phase_specific),
        "form_data": latest_comments,
    }

    return render(request, "invoice_page.html", context)
