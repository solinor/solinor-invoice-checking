import datetime
import tempfile

import pdfkit
import xlsxwriter
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string

from invoices.models import HourEntry, Invoice


def generate_hours_xls_for_invoice(request, invoice_id):
    invoice = get_object_or_404(Invoice, invoice_id=invoice_id)
    title = "%s - %s - %s-%s" % (invoice.client, invoice.project, invoice.year, invoice.month)

    entries = HourEntry.objects.filter(project=invoice.project, client=invoice.client, date__year__gte=invoice.year, date__month=invoice.month).filter(incurred_hours__gt=0)
    with tempfile.TemporaryDirectory() as dirname:
        filename = dirname + '/hourlist.xlsx'
        workbook = xlsxwriter.Workbook(filename)
        date_format = workbook.add_format({'num_format': 'yyyy-mm-dd', 'align': 'left'})
        bold = workbook.add_format({'bold': True})
        money = workbook.add_format({'num_format': '# ##0.00€'})
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
    return pdfkit.from_string(content,
                              False,
                              options=wk_options,
                              configuration=pdfkit_config
                              )


def generate_hours_pdf_for_invoice(request, invoice):
    invoice_data = get_object_or_404(Invoice, invoice_id=invoice)
    title = u"%s - %s - %s-%s" % (invoice_data.client, invoice_data.project, invoice_data.year, invoice_data.month)
    title = title.replace(u"\xe4", u"a").replace(u"\xb6", u"o").replace(u"\x84", u"A").replace(u"\x96", u"O").replace(u"\xf6", "o")

    entries = HourEntry.objects.filter(project=invoice_data.project, client=invoice_data.client, date__year__gte=invoice_data.year, date__month=invoice_data.month).filter(incurred_hours__gt=0)
    phases = {}
    for entry in entries:
        if entry.phase_name not in phases:
            phases[entry.phase_name] = []
        phases[entry.phase_name].append(entry)
    context = {"phases": phases}

    # We can generate the pdf from a url, file or, as shown here, a string
    content = render_to_string('pdf_template.html', context=context, request=request)
    return generate_pdf(title, content), title
