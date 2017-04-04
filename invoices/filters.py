import django_filters
from invoices.models import HourEntry, Invoice

choices = (
    (True, "Yes"),
    (False, "No")
)

class InvoiceFilter(django_filters.FilterSet):
    is_approved = django_filters.ChoiceFilter(null_label="Unknown", choices=choices)

    class Meta:
        model = Invoice
        fields = {
            "year": ["exact"],
            "month": ["exact"],
            "total_hours": ["gt", "lt"],
            "incorrect_entries_count": ["gt"],
            "is_approved": ["exact"],
        }
#        ["year", "month", "client", "project", "total_hours", "total_money", "incorrect_entries_count"] # , "is_approved", "has_comments"]
