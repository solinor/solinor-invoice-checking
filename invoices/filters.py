import django_filters

from invoices.models import HourEntry, Invoice, Project


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
