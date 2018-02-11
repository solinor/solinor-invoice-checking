import django_filters

from invoices.models import Client, HourEntry, Invoice, Project


class ClientsFilter(django_filters.FilterSet):

    class Meta:
        model = Client
        fields = {
            "name": ["icontains"],
        }


class HourListFilter(django_filters.FilterSet):
    date = django_filters.DateRangeFilter()

    class Meta:
        model = HourEntry
        fields = {
            "user_name": ["icontains"],
            "calculated_has_phase": ["exact"],
            "calculated_has_notes": ["exact"],
            "calculated_is_billable": ["exact"],
            "calculated_is_approved": ["exact"],
            "calculated_has_category": ["exact"],
            "calculated_has_proper_price": ["exact"],
            "calculated_is_overtime": ["exact"],
            "date": ["gte", "lte"],
        }


class InvoiceFilter(django_filters.FilterSet):
    class Meta:
        model = Invoice
        fields = {
            "date": ["exact"],
            "invoice_state": ["exact"],
            # TODO: add better date filter, client and project filters
        }


class ProjectsFilter(django_filters.FilterSet):
    class Meta:
        model = Project
        fields = {
            # TODO: add client and project name filters
        }
