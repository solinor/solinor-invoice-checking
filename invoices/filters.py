import django_filters
from invoices.models import HourEntry, Invoice

choices = (
    (True, "Yes"),
    (False, "No")
)

class InvoiceFilter(django_filters.FilterSet):

    o = django_filters.OrderingFilter(
        fields = (
            ("incorrect_entries_count", "incorrect_entries_count"),
            ("total_hours", "total_hours"),
            ("total_money", "total_money"),
            ("bill_rate_avg", "bill_rate_avg"),
        ),
        field_labels= {
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
#        ["year", "month", "client", "project", "total_hours", "total_money", "incorrect_entries_count"] # , "is_approved", "has_comments"]
