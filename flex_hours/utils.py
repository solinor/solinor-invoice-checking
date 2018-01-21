import datetime

import dateutil.rrule
from django.db.models import Sum

from flex_hours.models import FlexTimeCorrection, PublicHoliday, WorkContract
from invoices.models import HourEntry


class FlexHourException(Exception):
    pass


class FlexHourNoContractException(FlexHourException):
    pass


def fetch_contract(contracts, current_day):
    """Return contract that is valid for given day, or None"""
    for contract in contracts:
        if contract.start_date <= current_day and (contract.end_date is None or contract.end_date >= current_day):
            return contract


def fetch_first_contract(contracts):
    first_contract = None
    for contract in contracts:
        if not first_contract or first_contract.start_date > contract.start_date:
            first_contract = contract
    return first_contract


def fetch_last_contract(contracts):
    last_contract = None
    for contract in contracts:
        if not last_contract or last_contract.end_date < contract.end_date:
            last_contract = contract
    return last_contract


def find_first_process_date(events, contracts):
    """Finds the first day for calculating flex saldo

    Start from the latest set_to adjustment, and if not set, from the first contract.
    """
    latest_set_to = start_hour_markings_from_date = None
    for event in events:
        if event.set_to is not None:
            if not latest_set_to or start_hour_markings_from_date < event.date:
                latest_set_to = event.set_to
                start_hour_markings_from_date = event.date
    if start_hour_markings_from_date:
        return start_hour_markings_from_date, float(latest_set_to)

    first_contract = fetch_first_contract(contracts)
    if not first_contract:
        raise FlexHourNoContractException("Unable to find the first contract")
    return first_contract.start_date, 0


def find_last_process_date(hour_markings_list, contracts, today):
    """Finds the last day for calculating flex saldo

    Stop at the last hour marking, last contract end date. Never process future entries.
    """
    last_hour_marking_day = None
    if hour_markings_list:
        last_hour_marking_day = hour_markings_list[-1][0]  # datetime.date for the last hour marking
    last_contract = fetch_last_contract(contracts)
    last_process_day = today
    if last_hour_marking_day and last_contract:
        last_process_day = min(max(last_hour_marking_day, last_contract.end_date), today)
    return last_process_day


def calculate_kiky_stats(person, contracts, first_process_day, last_process_day):
    hours = HourEntry.objects.filter(user_m=person).filter(date__gte=datetime.date(2017, 9, 1)).filter(project="KIKY - Make Finland Great again").aggregate(Sum("incurred_hours"))["incurred_hours__sum"]
    if hours is None:
        hours = 0
    first_process_day = max(datetime.date(2017, 11, 1), first_process_day.replace(day=1))
    months_list = list(dateutil.rrule.rrule(dateutil.rrule.MONTHLY, dtstart=first_process_day, until=last_process_day))
    deduction = 0
    for month in months_list:
        contract = fetch_contract(contracts, month.date())
        if not contract:  # If there is no valid contract for the first day of the month, month is excluded from KIKY deductions
            continue
        if not contract.flex_enabled:  # If the contract for the first day of the month has flex saldo disabled, month is excluded from KIKY deductions
            continue
        percentage = float(contract.worktime_percent) / 100
        deduction += percentage * 2

    months = len(months_list)
    return {
        "hours_done": hours,
        "deduction": deduction,
        "eligible_months": months,
        "unused_hours": max(0, hours - deduction),
        "saldo": min(0, hours - deduction),
    }


def calculate_flex_saldo(person, flex_last_day=None, only_active=False):
    if not flex_last_day:
        flex_last_day = datetime.date.today() - datetime.timedelta(days=1)  # The default is to exclude today to have stable flex saldo (assuming everyone marks hours daily)
    contracts = WorkContract.objects.filter(user=person)
    events = FlexTimeCorrection.objects.filter(user=person)
    today = datetime.date.today()

    if only_active:
        if not fetch_contract(contracts, flex_last_day):
            return {"active": False}

    # Find the first date
    start_hour_markings_from_date, cumulative_saldo = find_first_process_date(events, contracts)

    holidays = {k.date: k.name for k in PublicHoliday.objects.filter(date__gte=start_hour_markings_from_date).filter(date__lte=today)}

    base_query = HourEntry.objects.filter(user_m=person).filter(date__gte=start_hour_markings_from_date).exclude(date__gte=today)

    hour_markings_list = list(base_query.exclude(phase_name__icontains="overtime").filter(leave_type="[project]").exclude(project="KIKY - Make Finland Great again").order_by("date").values("date").annotate(incurred_hours=Sum("incurred_hours")).values_list("date", "incurred_hours"))
    leave_markings_list = base_query.exclude(leave_type="Flex time Leave").exclude(leave_type="[project]").exclude(leave_type="Unpaid leave").order_by("date").values("date").annotate(incurred_hours=Sum("incurred_hours")).values_list("date", "incurred_hours")
    unpaid_leaves_list = base_query.filter(leave_type="Unpaid leave").order_by("date").values("date").annotate(incurred_hours=Sum("incurred_hours")).values_list("date", "incurred_hours")
    overtime_hours_list = base_query.filter(phase_name__icontains="overtime").order_by("date").values("date").annotate(incurred_hours=Sum("incurred_hours")).values_list("date", "incurred_hours")
    hour_markings = {k[0]: float(k[1]) for k in hour_markings_list}
    leave_markings = {k[0]: float(k[1]) for k in leave_markings_list}
    overtime_markings = {k[0]: float(k[1]) for k in overtime_hours_list}
    unpaid_leave_markings = {k[0]: float(k[1]) for k in unpaid_leaves_list}

    last_process_day = find_last_process_date(hour_markings_list, contracts, flex_last_day)
    current_day = start_hour_markings_from_date
    calculation_log = []
    daily_diff = []
    per_month_stats = []
    month_entry = {}
    years = set()
    while current_day <= last_process_day:
        if month_entry.get("month") is None:
            month_entry = {"month": current_day, "leave": 0, "worktime": 0, "expected_worktime": 0, "diff": 0, "cumulative_saldo": 0, "overtime": 0, "unpaid_leaves": 0}
        if month_entry["month"].strftime("%Y-%m") != current_day.strftime("%Y-%m"):
            per_month_stats.append(month_entry)
            month_entry = {"month": current_day, "leave": 0, "worktime": 0, "expected_worktime": 0, "diff": 0, "cumulative_saldo": 0, "overtime": 0, "unpaid_leaves": 0}
            years.add(current_day.strftime("%Y"))
        day_entry = {"date": current_day, "day_type": "Weekday", "expected_hours_today": 0}
        flex_hour_deduct = 0
        is_weekend = False
        is_holiday = False
        for event in events:
            if event.date == current_day and event.adjust_by:
                cumulative_saldo += float(event.adjust_by)
                calculation_log.append({
                    "date": current_day,
                    "sum": float(event.adjust_by),
                    "cumulative_saldo": cumulative_saldo,
                })
        plus_hours_today = flex_hour_deduct = 0
        if current_day in hour_markings:
            plus_hours_today = hour_markings[current_day]
        contract = fetch_contract(contracts, current_day)
        if not contract:
            raise FlexHourNoContractException("Hour markings for %s for %s, but no contract." % (current_day, person))

        day_entry["flex_enabled"] = contract.flex_enabled
        day_entry["worktime_percent"] = contract.worktime_percent

        if 0 < current_day.isoweekday() < 6:
            if current_day in holidays:
                is_holiday = True
                day_entry["day_type"] = "Public holiday: %s" % holidays[current_day]
            elif contract.flex_enabled:
                    flex_hour_deduct = contract.workday_length
                    day_entry["expected_hours_today"] = flex_hour_deduct
                    month_entry["expected_worktime"] += flex_hour_deduct
                    month_entry["diff"] -= flex_hour_deduct
        else:
            is_weekend = True
            day_entry["day_type"] = "Weekend"

        if contract.flex_enabled:
            if current_day in unpaid_leave_markings:
                unpaid_hours = unpaid_leave_markings[current_day]
                day_entry["unpaid_leaves"] = unpaid_hours
                day_entry["expected_hours_today"] -= unpaid_hours
                month_entry["expected_worktime"] -= unpaid_hours
                month_entry["diff"] += unpaid_hours

            if plus_hours_today:
                day_entry["worktime"] = plus_hours_today
                month_entry["worktime"] += plus_hours_today
                month_entry["diff"] += plus_hours_today

            if current_day in leave_markings and not is_weekend and not is_holiday:
                leave_hours = leave_markings[current_day]
                plus_hours_today += leave_hours
                day_entry["leave"] = leave_hours
                month_entry["leave"] += leave_hours
                month_entry["diff"] += leave_hours

            if current_day in overtime_markings:
                month_entry["overtime"] += overtime_markings[current_day]
                day_entry["overtime"] = overtime_markings[current_day]

        day_entry["sum"] = - flex_hour_deduct + day_entry.get("worktime", 0) + day_entry.get("leave", 0) + day_entry.get("unpaid_leaves", 0)

        cumulative_saldo += day_entry["sum"]
        day_entry["cumulative_saldo"] = cumulative_saldo
        month_entry["cumulative_saldo"] = cumulative_saldo

        calculation_log.append(day_entry)
        if contract.flex_enabled:
            daily_diff.append((current_day.year, current_day.month - 1, current_day.day, plus_hours_today - flex_hour_deduct, "%s (%s): %sh" % (current_day.strftime("%Y-%m-%d"), current_day.strftime("%A"), plus_hours_today - flex_hour_deduct)))
        current_day += datetime.timedelta(days=1)
    calculation_log.reverse()
    if month_entry.get("month"):
        per_month_stats.append(month_entry)
    per_month_stats.reverse()
    kiky_stats = calculate_kiky_stats(person, contracts, start_hour_markings_from_date, last_process_day)
    context = {
        "person": person,
        "contracts": contracts,
        "flex_time_events": events,
        "cumulative_saldo": cumulative_saldo + kiky_stats.get("saldo", 0),
        "calculation_log": calculation_log,
        "daily_diff": daily_diff,
        "monthly_summary": per_month_stats,
        "calendar_height": min(3, len(years)) * 175,
        "kiky": kiky_stats,
    }
    return context
