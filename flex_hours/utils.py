import datetime

from django.db.models import Sum

from flex_hours.models import FlexTimeCorrection, PublicHoliday, WorkContract
from invoices.models import HourEntry


class FlexHourException(Exception):
    pass


class FlexHourNoContractException(FlexHourException):
    pass


def fetch_contract(contracts, current_day):
    for contract in contracts:
        if contract.start_date <= current_day and (contract.end_date is None or contract.end_date >= current_day):
            return contract


def fetch_first_contract(contracts):
    first_contract = None
    for contract in contracts:
        if not first_contract or first_contract.start_date > contract.start_date:
            first_contract = contract
    return first_contract


def calculate_flex_saldo(person):
    contracts = WorkContract.objects.all().filter(user=person)
    events = FlexTimeCorrection.objects.all().filter(user=person)
    today = datetime.date.today()

    latest_set_to = start_hour_markings_from_date = None
    for event in events:
        if event.set_to:
            if not latest_set_to or latest_set_to.date < event.date:
                latest_set_to = event
                start_hour_markings_from_date = event.date
    if not start_hour_markings_from_date:
        first_contract = fetch_first_contract(contracts)
        if not first_contract:
            raise FlexHourNoContractException("Unable to fetch first contract for %s" % person)
        start_hour_markings_from_date = first_contract.start_date

    holidays_list = PublicHoliday.objects.filter(date__gte=start_hour_markings_from_date).filter(date__lte=today)
    holidays = {k.date: k.name for k in holidays_list}

    hour_markings = HourEntry.objects.filter(user_m=person).filter(date__gte=start_hour_markings_from_date).exclude(date__gte=today).exclude(leave_type="Flex time Leave").order_by("date").values("date").annotate(incurred_hours=Sum("incurred_hours")).values_list("date", "incurred_hours")
    current_day = start_hour_markings_from_date
    calculation_log = []
    daily_diff_entries = []
    if latest_set_to:
        flex_hours = float(latest_set_to.set_to)
    else:
        flex_hours = 0
    while current_day <= today:
        message_for_today = ""
        for event in events:
            if event.date == current_day and event.adjust_by:
                flex_hours += float(event.adjust_by)
                calculation_log.append({"date": current_day, "message": "Flex hours manually adjusted by %sh" % event.adjust_by})
        plus_hours_today = flex_hour_deduct = 0
        for hour_marking_date, incurred_hours in hour_markings:
            if hour_marking_date == current_day:
                plus_hours_today += float(incurred_hours)
        contract = fetch_contract(contracts, current_day)
        if not contract:
            raise FlexHourNoContractException("Hour markings for %s for %s, but no contract." % (current_day, person))

        if 0 < current_day.isoweekday() < 6:
            if current_day in holidays:
                message_for_today += "Public holiday: %s. " % holidays[current_day]
            else:
                flex_hour_deduct = (float(contract.worktime_percent or 100) / 100) * 7.5
                if contract.flex_enabled:
                    flex_hours -= flex_hour_deduct
                    message_for_today += "Deducting normal workday: -7.5 * %s%% = -%sh. " % (contract.worktime_percent or 100, flex_hour_deduct)
        elif plus_hours_today:
            message_for_today += "Weekend. "

        if contract.flex_enabled and plus_hours_today:
            flex_hours += plus_hours_today
            message_for_today += "Adding hour markings: %sh. " % plus_hours_today
        elif not contract.flex_enabled and (plus_hours_today or flex_hour_deduct):
            message_for_today += "Flex time is not enabled. Would have been +%sh and -%sh for today." % (plus_hours_today, flex_hour_deduct)

        if message_for_today:
            calculation_log.append({"date": current_day, "message": message_for_today})
        daily_diff_entries.append((current_day.year, current_day.month - 1, current_day.day, plus_hours_today - flex_hour_deduct))
        current_day += datetime.timedelta(days=1)
    context = {
        "person": person,
        "contracts": contracts,
        "flex_time_events": events,
        "flex_hours": flex_hours,
        "calculation_log": calculation_log,
        "hour_markings": hour_markings,
        "daily_diff_entries": daily_diff_entries,
    }
    return context
