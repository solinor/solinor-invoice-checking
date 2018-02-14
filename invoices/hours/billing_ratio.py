from django.db.models import Q, Sum


def billing_ratio_for_hourentries(qs, flat=False):
    billing_ratio_data = qs.values("user_email").order_by("user_email").annotate(billable_hours=Sum("incurred_hours", filter=Q(calculated_is_billable=True))).annotate(nonbillable_hours=Sum("incurred_hours", filter=Q(calculated_is_billable=False)))
    for item in billing_ratio_data:
        total_hours = (item["nonbillable_hours"] or 0) + (item["billable_hours"] or 0)
        if total_hours:
            item["billing_ratio"] = float(item["billable_hours"] or 0) / total_hours * 100
            if flat:
                return item["billing_ratio"]

    if flat:
        return 0

    return billing_ratio_data
