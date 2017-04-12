import django_filters
from invoices.models import Invoice, Project, HourEntry

class CustomerHoursFilter(django_filters.FilterSet):
    class Meta:
        model = HourEntry
        fields = {
            "user_name": ["icontains"],
            "notes": ["icontains"],
        }

class InvoiceFilter(django_filters.FilterSet):
    class Meta:
        model = Invoice
        fields = {
            "year": ["exact"],
            "month": ["exact"],
            "invoice_state": ["exact"],
            "tags": ["icontains"],
            "client": ["icontains"],
        }

class ProjectsFilter(django_filters.FilterSet):

    class Meta:
        model = Project
        fields = {
            "client": ["icontains"],
        }
