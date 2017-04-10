import django_filters
from invoices.models import Invoice, Project


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
            "client": ["icontains"]
        }
