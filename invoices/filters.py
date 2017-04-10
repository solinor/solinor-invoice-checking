import django_filters
from invoices.models import Invoice, Project


class InvoiceFilter(django_filters.FilterSet):

    ordering = django_filters.OrderingFilter(
        fields=(
            ("incorrect_entries_count", "incorrect_entries_count"),
            ("total_hours", "total_hours"),
            ("total_money", "total_money"),
            ("bill_rate_avg", "bill_rate_avg"),
        ),
        field_labels={
            "incorrect_entries_count": "Issues",
            "total_hours": "Hours",
            "total_money": "Price",
            "bill_rate_avg": "Bill rate (avg)",
        }
    )

    class Meta:
        model = Invoice
        fields = {
            "year": ["exact"],
            "month": ["exact"],
            "invoice_state": ["exact"],
        }


class ProjectsFilter(django_filters.FilterSet):

    class Meta:
        model = Project
        fields = {
            "client": ["icontains"]
        }
