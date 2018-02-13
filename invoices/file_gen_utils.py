import datetime
import tempfile
from collections import defaultdict

import pdfkit
import xlsxwriter
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string

from invoices.models import HourEntry, Invoice


def generate_hours_xls_for_invoice(request, invoice_id):
    invoice = get_object_or_404(Invoice, invoice_id=invoice_id)
    title = f"{invoice.project_m.client_m.name} - {invoice.project_m.name} - {invoice.date:%Y-%m}"

    entries = HourEntry.objects.exclude(status="Unsubmitted").filter(invoice=invoice).filter(incurred_hours__gt=0)
    with tempfile.TemporaryDirectory() as dirname:
        filename = dirname + "/hourlist.xlsx"
        workbook = xlsxwriter.Workbook(filename)
        date_format = workbook.add_format({"num_format": "yyyy-mm-dd", "align": "left"})
        bold = workbook.add_format({"bold": True})
        money = workbook.add_format({"num_format": "# ##0.00€"})
        worksheet = workbook.add_worksheet()
        worksheet.write("A1", "Date", bold)
        worksheet.write("B1", "Person", bold)
        worksheet.write("C1", "Hour rate €", bold)
        worksheet.write("D1", "Hours", bold)
        worksheet.write("E1", "Incurred €", bold)
        worksheet.write("F1", "Phase name", bold)
        worksheet.write("G1", "Category", bold)
        worksheet.write("H1", "Notes", bold)
        worksheet.freeze_panes(1, 0)
        worksheet.set_column("A:A", 12)
        worksheet.set_column("B:B", 30)
        worksheet.set_column("F:G", 20)
        worksheet.set_column("H:H", 50)

        for i, entry in enumerate(entries):
            row_number = i + 1
            worksheet.write_datetime(row_number, 0, datetime.datetime.combine(entry.date, datetime.datetime.min.time()), date_format)
            worksheet.write_string(row_number, 1, entry.user_name)
            worksheet.write(row_number, 2, entry.bill_rate, money)
            worksheet.write(row_number, 3, entry.incurred_hours)
            worksheet.write(row_number, 4, entry.incurred_money, money)
            worksheet.write_string(row_number, 5, entry.phase_name)
            worksheet.write_string(row_number, 6, entry.category)
            worksheet.write_string(row_number, 7, entry.notes)
        workbook.close()
        return open(filename, "rb").read(), title


def generate_pdf(title, content):
    pdfkit_config = pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_CMD)
    wk_options = {
        "page-size": "a4",
        "orientation": "landscape",
        "title": title,
        # In order to specify command-line options that are simple toggles
        # using this dict format, we give the option the value None
        "no-outline": None,
        "disable-javascript": None,
        "encoding": "UTF-8",
        "margin-left": "0.2cm",
        "margin-right": "0.2cm",
        "margin-top": "0.3cm",
        "margin-bottom": "0.3cm",
        "lowquality": None,
    }
    return pdfkit.from_string(content,
                              False,
                              options=wk_options,
                              configuration=pdfkit_config
                              )


def generate_hours_pdf_for_invoice(request, invoice_id):
    invoice = get_object_or_404(Invoice, invoice_id=invoice_id)
    title = f"{invoice.project_m.client_m.name} - {invoice.project_m.name} - {invoice.date:%Y-%m}"
    title = title.replace("\xe4", "a").replace("\xb6", "o").replace("\x84", "A").replace("\x96", "O").replace("\xf6", "o")

    entries = HourEntry.objects.exclude(status="Unsubmitted").filter(invoice=invoice).filter(incurred_hours__gt=0)
    phases = defaultdict(lambda: {"items": [], "hours_sum": 0, "money_sum": 0})
    for entry in entries:
        phases[entry.phase_name]["items"].append(entry)
        phases[entry.phase_name]["hours_sum"] += entry.incurred_hours
        phases[entry.phase_name]["money_sum"] += entry.incurred_money

    context = {
        "invoice": invoice,
        "phases": dict(phases),
        "money_sum": sum(entry.incurred_money for entry in entries),
        "hours_sum": sum(entry.incurred_hours for entry in entries),
    }

    # We can generate the pdf from a url, file or, as shown here, a string
    content = render_to_string("hours/pdf_export.html", context=context, request=request)
    return generate_pdf(title, content), title
