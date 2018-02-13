import datetime
from collections import defaultdict

from django.conf import settings
from django.db.models import Sum

from invoices.models import HourEntry


class DatePeriod(object):
    def __init__(self, item=None):
        self.items = []
        if item:
            self.items.append(item)

    def num_days(self):
        if len(self.items) == 2:
            return (self.items[1] - self.items[0]).days + 1
        return None


def get_early_care_sickleaves():
    start_date = datetime.date.today() - datetime.timedelta(days=365)
    short_period_start_date = datetime.date.today() - datetime.timedelta(days=120)
    sick_leaves = HourEntry.objects.exclude(status="Unsubmitted").filter(date__gte=start_date).exclude(user_m=None).exclude(user_m__archived=True).filter(leave_type="Sick leave").order_by("user_m", "date").values("user_m__email", "user_m__display_name", "user_m__pk", "date").annotate(incurred_hours_sum=Sum("incurred_hours"))

    per_person_info = defaultdict(lambda: {"short": 0, "long": 0, "short_periods": []})
    for item in sick_leaves:
        user_details = per_person_info[item["user_m__pk"]]
        user_details["user_pk"] = item["user_m__pk"]
        user_details["user_email"] = item["user_m__email"]
        user_details["user_name"] = item["user_m__display_name"]
        user_details["long"] += 1
        if item["date"] > short_period_start_date:
            per_person_info[item["user_m__pk"]]["short_periods"].append(item["date"])

    for person in per_person_info.values():
        previous_date = None
        collected_periods = []
        current_period = DatePeriod()
        item = None
        for item in person["short_periods"]:
            if previous_date is None:
                previous_date = item
                person["short"] += 1
                current_period.items.append(item)
                continue
            if item - previous_date > datetime.timedelta(days=5):
                current_period.items.append(previous_date)
                collected_periods.append(current_period)
                current_period = DatePeriod(item)
                person["short"] += 1
            previous_date = item
        if item:
            current_period.items.append(item)
            collected_periods.append(current_period)
        person["collected_periods"] = collected_periods

    sick_leaves_exceeding_limits = sorted([k for k in per_person_info.values() if k["short"] > settings.SICK_LEAVE_SHORT_PERIOD_LIMIT or k["long"] > settings.SICK_LEAVE_LONG_PERIOD_LIMIT], key=lambda k: k["user_name"])
    sick_leaves_not_exceeding_limits = sorted([k for k in per_person_info.values() if k["short"] <= settings.SICK_LEAVE_SHORT_PERIOD_LIMIT and k["long"] <= settings.SICK_LEAVE_LONG_PERIOD_LIMIT], key=lambda k: k["user_name"])

    return {
        "sick_leaves_exceeding_limits": sick_leaves_exceeding_limits,
        "sick_leaves_not_exceeding_limits": sick_leaves_not_exceeding_limits,
        "short_period_limit": settings.SICK_LEAVE_SHORT_PERIOD_LIMIT,
        "long_period_limit": settings.SICK_LEAVE_LONG_PERIOD_LIMIT,
    }
