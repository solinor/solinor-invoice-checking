import datetime

from django.http import HttpResponseServerError

from flex_hours.models import FlexTimeCorrection, PublicHoliday, WorkContract
from invoices.models import HourEntry


def calculate_flex_saldo(person):
    contracts = WorkContract.objects.all().filter(user=person)
    events = FlexTimeCorrection.objects.all().filter(user=person)
    holidays = PublicHoliday.objects.all()

    latest_set_to = start_hour_markings_from_date = None
    for event in events:
        if event.set_to:
            if not latest_set_to or latest_set_to.date < event.date:
                latest_set_to = event
                start_hour_markings_from_date = event.date
    if not start_hour_markings_from_date:
        first_contract = None
        for contract in contracts:
            if not first_contract or first_contract.start_date > contract.start_date:
                first_contract = contract
        if not first_contract:
            return HttpResponseServerError("No contracts for %s" % person)
        start_hour_markings_from_date = first_contract.start_date

    today = datetime.date.today()
    hour_markings = HourEntry.objects.filter(user_m=person).filter(date__gte=start_hour_markings_from_date).exclude(leave_type="Flex time Leave")
    current_day = start_hour_markings_from_date
    flex_hour_events = []
    flex_diff_entries = []
    if latest_set_to:
        flex_hours = float(latest_set_to.set_to)
    else:
        flex_hours = 0
    while current_day <= today:
        message_for_today = ""
        for event in events:
            if event.date == current_day and event.adjust_by:
                flex_hours += float(event.adjust_by)
                flex_hour_events.append({"date": current_day, "message": "Flex hours manually adjusted by %sh" % event.adjust_by})
        plus_hours_today = flex_hour_deduct = 0
        for hour_marking in hour_markings:
            if hour_marking.date == current_day:
                plus_hours_today += float(hour_marking.incurred_hours)
        should_add_plus_hours = True
        for contract in contracts:
            if contract.start_date <= current_day and (contract.end_date is None or contract.end_date > current_day):
                if not contract.flex_enabled:
                    should_add_plus_hours = False
                break
        else:
            return HttpResponseServerError("No existing work contract for %s" % person)

        if 0 < current_day.isoweekday() < 6:
            for holiday in holidays:
                if holiday.date == current_day:
                    message_for_today += "Public holiday: %s. " % holiday.name
                    break
            else:
                flex_hour_deduct = (float(contract.worktime_percent or 100) / 100) * 7.5
                if contract.flex_enabled:
                    flex_hours -= flex_hour_deduct
                    message_for_today += "Deducting normal workday: -7.5 * %s%% = -%sh. " % (contract.worktime_percent or 100, flex_hour_deduct)
        elif plus_hours_today:
            message_for_today += "Weekend. "

        if should_add_plus_hours and plus_hours_today:
            flex_hours += plus_hours_today
            message_for_today += "Adding hour markings: %sh. " % plus_hours_today
        elif not contract.flex_enabled and (plus_hours_today or flex_hour_deduct):
            message_for_today += "Flex time is not enabled. Would have been +%sh and -%sh for today." % (plus_hours_today, flex_hour_deduct)

        if message_for_today:
            flex_hour_events.append({"date": current_day, "message": message_for_today})
        flex_diff_entries.append(("new Date(%s,%s,%s)" % (current_day.year, current_day.month - 1, current_day.day), plus_hours_today - flex_hour_deduct))
        current_day += datetime.timedelta(days=1)
    context = {
        "person": person,
        "contracts": contracts,
        "flex_time_events": events,
        "flex_hours": flex_hours,
        "flex_hour_events": flex_hour_events,
        "hour_markings": hour_markings,
        "flex_diff_entries": flex_diff_entries,
    }
    return context
