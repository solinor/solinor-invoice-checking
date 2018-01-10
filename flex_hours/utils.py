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


def fetch_last_contract(contracts):
    last_contract = None
    for contract in contracts:
        if not last_contract or last_contract.end_date < contract.end_date:
            last_contract = contract
    return last_contract


def find_first_process_date(events, contracts):
    latest_set_to = start_hour_markings_from_date = None
    for event in events:
        if event.set_to:
            if not latest_set_to or latest_set_to.date < event.date:
                latest_set_to = event.set_to
                start_hour_markings_from_date = event.date
    if start_hour_markings_from_date:
        return start_hour_markings_from_date, float(latest_set_to)

    first_contract = fetch_first_contract(contracts)
    if not first_contract:
        raise FlexHourNoContractException("Unable to find the first contract")
    return first_contract.start_date, 0


def find_last_process_date(hour_markings_list, contracts):
    today = datetime.date.today()
    last_hour_marking_day = None
    if hour_markings_list:
        last_hour_marking_day = hour_markings_list[-1][0]
    last_contract = fetch_last_contract(contracts)
    last_process_day = today
    if last_hour_marking_day and last_contract:
        last_process_day = min(max(last_hour_marking_day, last_contract.end_date), today)
    return last_process_day


def calculate_flex_saldo(person):
    contracts = WorkContract.objects.all().filter(user=person)
    events = FlexTimeCorrection.objects.all().filter(user=person)
    today = datetime.date.today()

    # Find the first date
    start_hour_markings_from_date, flex_hours = find_first_process_date(events, contracts)

    holidays_list = PublicHoliday.objects.filter(date__gte=start_hour_markings_from_date).filter(date__lte=today)
    holidays = {k.date: k.name for k in holidays_list}

    hour_markings_list = list(HourEntry.objects.filter(user_m=person).filter(date__gte=start_hour_markings_from_date).exclude(date__gte=today).filter(leave_type="[project]").order_by("date").values("date").annotate(incurred_hours=Sum("incurred_hours")).values_list("date", "incurred_hours"))
    leave_markings_list = list(HourEntry.objects.filter(user_m=person).filter(date__gte=start_hour_markings_from_date).exclude(date__gte=today).exclude(leave_type="Flex time Leave").exclude(leave_type="[project]").exclude(leave_type="Unpaid leave").order_by("date").values("date").annotate(incurred_hours=Sum("incurred_hours")).values_list("date", "incurred_hours"))
    hour_markings = {k[0]: float(k[1]) for k in hour_markings_list}
    leave_markings = {k[0]: float(k[1]) for k in leave_markings_list}

    last_process_day = find_last_process_date(hour_markings_list, contracts)
    current_day = start_hour_markings_from_date
    calculation_log = []
    daily_diff_entries = []
    while current_day <= last_process_day:
        is_weekend = is_holiday = False
        message_for_today = ""
        for event in events:
            if event.date == current_day and event.adjust_by:
                flex_hours += float(event.adjust_by)
                calculation_log.append({"date": current_day, "message": "Flex hours manually adjusted by %sh" % event.adjust_by})
        plus_hours_today = flex_hour_deduct = 0
        if current_day in hour_markings:
            plus_hours_today = hour_markings[current_day]
        contract = fetch_contract(contracts, current_day)
        if not contract:
            raise FlexHourNoContractException("Hour markings for %s for %s, but no contract." % (current_day, person))

        if 0 < current_day.isoweekday() < 6:
            if current_day in holidays:
                is_holiday = True
                message_for_today += "Public holiday: %s. " % holidays[current_day]
            else:
                flex_hour_deduct = (float(contract.worktime_percent or 100) / 100) * 7.5
                if contract.flex_enabled:
                    flex_hours -= flex_hour_deduct
                    message_for_today += "Deducting normal workday: -7.5 * %s%% = -%sh. " % (contract.worktime_percent or 100, flex_hour_deduct)
        elif plus_hours_today:
            is_weekend = True
            message_for_today += "Weekend. "

        if contract.flex_enabled and plus_hours_today:
            flex_hours += plus_hours_today
            message_for_today += "Adding hour markings: %sh. " % plus_hours_today
        elif not contract.flex_enabled and (plus_hours_today or flex_hour_deduct):
            message_for_today += "Flex time is not enabled. Would have been +%sh and -%sh for today." % (plus_hours_today, flex_hour_deduct)
        if current_day in leave_markings:
            leave_hours = leave_markings[current_day]
            if is_weekend:
                message = " Also, %s hours as leave markings, not counted for weekend."
            elif is_holiday:
                message = " Also, %s hours as leave markings, not counted for public holidays."
            else:
                message = " Also, %s hours as leave markings."
                flex_hours += leave_hours
                plus_hours_today += leave_hours
            message_for_today += message % leave_hours

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
        "hour_markings": hour_markings_list,
        "daily_diff_entries": daily_diff_entries,
    }
    return context
