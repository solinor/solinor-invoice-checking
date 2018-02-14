import datetime
from collections import defaultdict

from django.db.models import Q, Sum
from django.http import HttpResponseBadRequest

from invoices.models import HourEntry
from invoices.utils import daterange


def calculate_clientbase_stats(sorting, active_field):
    field_spec = {
        "workdays_fte_avg": ("FTE average for workdays", "How many hours are done on average?", "Hours worked divided by 100% working time for that month"),
        "active_days_fte_avg": ("FTE average for days with hour markings", "How many hours are done when something happens on this project?", "Hours divided by 100% working time for days with hour markings"),
        "workdays_people_avg": ("Average number of people working for workdays", "How many people are working, if work would be distributed evenly for each workday?", "Sum of number of people marking hours divided by number of working days for that month"),
        "active_days_people_avg": ("Average number of people working for days with hour markings", "How many people are working when something happens on this project?", "Sum of number of people marking hours divided by number of days with hour markings"),
    }
    if sorting not in field_spec.keys():
        return HttpResponseBadRequest("Invalid sorting key")
    if active_field:
        if active_field not in field_spec.keys():
            return HttpResponseBadRequest("Invalid field key")
        active_field_spec = field_spec[active_field]

    months_count = 13
    end_date = datetime.date.today().replace(day=1) - datetime.timedelta(days=1)
    start_date = (end_date - datetime.timedelta(days=months_count * 30 - 15)).replace(day=1)

    hour_entries = HourEntry.objects.exclude(invoice__project_m__project_state="Internal").exclude(invoice__project_m__client_m__name__in=["Solinor", "[none]"]).exclude(incurred_hours=0).filter(date__gte=start_date, date__lte=end_date).values("invoice__project_m__client_m__name", "user_email", "incurred_hours", "date")
    raw_stats = defaultdict(lambda: defaultdict(lambda: {"people": set(), "hours": 0}))
    for hour_entry in hour_entries:
        if hour_entry["date"].isoweekday() > 5:  # Ignore weekends
            continue
        raw_stats[hour_entry["invoice__project_m__client_m__name"]][hour_entry["date"]]["people"].add(hour_entry["user_email"])
        raw_stats[hour_entry["invoice__project_m__client_m__name"]][hour_entry["date"]]["hours"] += hour_entry["incurred_hours"]

    stats = defaultdict(lambda: defaultdict(lambda: {"active_days": 0, "total_days": 0, "people_sum": 0, "hours_sum": 0, "workdays_fte_avg": 0, "workdays_people_avg": 0, "active_days_fte_avg": 0, "active_days_people_avg": 0}))
    for client, client_data in raw_stats.items():
        for current_day in daterange(start_date, end_date):
            if current_day.isoweekday() > 5:  # Ignore weekends
                continue
            fday = current_day.strftime("%Y-%m")
            stats[client][fday]["total_days"] += 1

            if current_day in client_data:
                entry = client_data[current_day]
                if entry["people"] and entry["hours"]:
                    stats[client][fday]["active_days"] += 1
                    stats[client][fday]["people_sum"] += len(entry["people"])
                    stats[client][fday]["hours_sum"] += entry["hours"]

    final_stats = []
    months = set()
    for client, client_data in stats.items():
        for month, month_data in client_data.items():
            months.add(month)
            if month_data["total_days"]:
                month_data["workdays_fte_avg"] = month_data["hours_sum"] / (month_data["total_days"] * 7.5)
                month_data["workdays_people_avg"] = month_data["people_sum"] / month_data["total_days"]

            if month_data["active_days"]:
                month_data["active_days_fte_avg"] = month_data["hours_sum"] / (month_data["active_days"] * 7.5)
                month_data["active_days_people_avg"] = month_data["people_sum"] / month_data["active_days"]
            if active_field:
                month_data["active_field"] = month_data[active_field]
        sorted_months = sorted(client_data.items(), key=lambda k: k[0])
        final_stats.append({
            "client": client,
            "data": sorted_months,
        })
    final_stats = sorted(final_stats, key=lambda k: [i[1][sorting] for i in reversed(k["data"])], reverse=True)
    context = {
        "stats": final_stats,
        "months": sorted(months),
        "sorting": sorting,
        "field_spec": field_spec,
    }
    if active_field:
        context["active_field"] = active_field
        context["active_field_spec"] = active_field_spec
    return context


def hours_overview_stats(email):
    base_query = HourEntry.objects.exclude(status="Unsubmitted").filter(user_email=email).exclude(incurred_hours=0)
    try:
        your_last_hour_marking = base_query.values_list("date", flat=True).latest("date")
    except HourEntry.DoesNotExist:
        your_last_hour_marking = "No entries"

    today = datetime.date.today()
    month_ago = today - datetime.timedelta(days=30)
    two_months = today - datetime.timedelta(days=60)
    your_hours_this_week = base_query.filter(date__gte=today - datetime.timedelta(days=6), date__lte=today).aggregate(hours=Sum("incurred_hours"))["hours"] or 0

    your_unsubmitted_entries = HourEntry.objects.filter(user_email=email).exclude(incurred_hours=0).filter(status="Unsubmitted").count()

    billing_rate_data = base_query.filter(date__gte=month_ago, date__lte=today).values("user_email").order_by("user_email").annotate(billable_hours=Sum("incurred_hours", filter=Q(calculated_is_billable=True))).annotate(nonbillable_hours=Sum("incurred_hours", filter=Q(calculated_is_billable=False)))
    your_billing_ratio = "?"
    if billing_rate_data:
        total_hours = (billing_rate_data[0]["nonbillable_hours"] or 0) + (billing_rate_data[0]["billable_hours"] or 0)
        if total_hours > 0:
            your_billing_ratio = float(billing_rate_data[0]["billable_hours"] or 0) / total_hours * 100

    start_date = today - datetime.timedelta(days=95)
    daily_billing_ratio = {item["date"]: item for item in base_query.filter(date__gte=start_date, date__lte=today).values("date").order_by("date").annotate(billable_hours=Sum("incurred_hours", filter=Q(calculated_is_billable=True))).annotate(nonbillable_hours=Sum("incurred_hours", filter=Q(calculated_is_billable=False)))}
    your_daily_billing_ratio = []
    ratio = 0
    for i, date in enumerate(daterange(start_date, today)):
        date_entry = daily_billing_ratio.get(date)
        if date_entry:
            total_hours = (date_entry["billable_hours"] or 0) + (date_entry["nonbillable_hours"] or 0)
            if total_hours > 0:
                ratio = (date_entry["billable_hours"] or 0) / total_hours * 100

        your_daily_billing_ratio.append(ratio)
    your_daily_billing_ratio = [(your_daily_billing_ratio[i] + your_daily_billing_ratio[i + 1] + your_daily_billing_ratio[i + 2] + your_daily_billing_ratio[i + 3] + your_daily_billing_ratio[i + 4]) / 5 for i in range(0, len(your_daily_billing_ratio) - 5, 5)]

    company_billing_money = HourEntry.objects.exclude(status="Unsubmitted").filter(calculated_is_billable=True).filter(date__gte=month_ago, date__lte=today).aggregate(item=Sum("incurred_money"))["item"] or 0
    company_billing_unsubmitted_money = HourEntry.objects.filter(status="Unsubmitted").filter(date__gte=two_months, date__lte=today).aggregate(item=Sum("incurred_money"))["item"] or 0
    company_unsubmitted_entries = HourEntry.objects.filter(status="Unsubmitted").filter(date__gte=two_months, date__lte=today).count()

    company_billing_unapproved_money = HourEntry.objects.filter(status="Pending Approval").filter(date__gte=two_months, date__lte=today).aggregate(item=Sum("incurred_money"))["item"] or 0
    company_unapproved_entries = HourEntry.objects.filter(status="Pending Approval").filter(date__gte=two_months, date__lte=today).count()

    company_billable_hours = HourEntry.objects.exclude(status="Unsubmitted").filter(date__gte=month_ago, date__lte=today).filter(calculated_is_billable=True).aggregate(item=Sum("incurred_hours"))["item"] or 0
    company_nonbillable_hours = HourEntry.objects.exclude(status="Unsubmitted").filter(date__gte=month_ago, date__lte=today).filter(calculated_is_billable=False).aggregate(item=Sum("incurred_hours"))["item"] or 0

    company_billing_ratio = "?"
    if company_billable_hours or company_nonbillable_hours:
        total_hours = company_nonbillable_hours + company_billable_hours
        company_billing_ratio = company_nonbillable_hours / total_hours * 100

    return {
        "your_last_hour_marking": your_last_hour_marking,
        "your_last_hour_marking_day": your_last_hour_marking.strftime("%A"),
        "your_hours_this_week": your_hours_this_week,
        "your_billing_ratio": your_billing_ratio,
        "your_unsubmitted_entries": your_unsubmitted_entries,
        "your_daily_billing_ratio": your_daily_billing_ratio[-90:],
        "company_billing_money": company_billing_money,
        "company_billing_ratio": company_billing_ratio,
        "company_billing_unsubmitted_money": company_billing_unsubmitted_money,
        "company_unsubmitted_entries": company_unsubmitted_entries,
        "company_billing_unapproved_money": company_billing_unapproved_money,
        "company_unapproved_entries": company_unapproved_entries,
        "company_error_entries_date_gte": two_months,
    }
