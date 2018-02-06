import datetime
import json
import pickle

import dateutil.rrule
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q, Sum
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.dateparse import parse_date, parse_datetime

from flex_hours.models import FlexTimeCorrection, PublicHoliday, WorkContract
from invoices.models import Event, HourEntry, TenkfUser
from invoices.slack import slack
from invoices.tenkfeet_api import TenkFeetApi


class FlexHourException(Exception):
    pass


class FlexHourNoContractException(FlexHourException):
    pass


class FlexNotEnabledException(FlexHourException):
    pass


def send_flex_saldo_notifications(year, month):
    end_date = datetime.date(year, month, 1) - datetime.timedelta(days=1)
    previous_month = (end_date - datetime.timedelta(days=32))

    c = 0
    for user in TenkfUser.objects.all():
        try:
            flex_info = calculate_flex_saldo(user, end_date, only_active=True)
        except FlexHourException as error:
            print("Unable to calculate the report for {}: {}".format(user, error))
            continue
        if not flex_info.get("active", True):
            continue
        saldo = flex_info["cumulative_saldo"]
        context = {"saldo": saldo, "kiky_saldo": flex_info["kiky"]["saldo"]}

        if flex_info["monthly_summary"]:
            for item in flex_info["monthly_summary"]:
                if item["month"].strftime("%Y-%m") == previous_month.strftime("%Y-%m"):
                    context["last_month_diff"] = item["cumulative_saldo"] - saldo
                    break
        notification_text = render_to_string("notifications/flex_saldo.txt", context).strip()

        if notification_text:
            attachment = {
                "author_name": "Solinor Finance",
                "author_link": "https://" + settings.DOMAIN,
                "fallback": "Flex saldo report",
                "title": "Flex saldo report",
                "title_link": "https://" + settings.DOMAIN + reverse("your_flex_hours"),
                "text": notification_text,
                "fields": [
                    {"title": "Flex saldo at the end of last month", "value": "{:.2f}h".format(saldo), "short": False},
                    {"title": "Change from month before", "value": "{:.2f}h".format(context["last_month_diff"]), "short": False},
                    {"title": "KIKY saldo", "value": "{:.2f}h".format(context["kiky_saldo"]), "short": False},
                ]
            }
            if user.slack_id:
                c += 1
                slack.chat.post_message(user.slack_id, attachments=[attachment], as_user="finance-bot")
                for admin in settings.SLACK_NOTIFICATIONS_ADMIN:
                    slack.chat.post_message(admin, text="Following message was sent to {}:".format(user.full_name), attachments=[attachment], as_user="finance-bot")
            else:
                print("Unable to send flex saldo notification to {} - no slack ID available.".format(user.guid))
    Event(event_type="send_flex_saldo_notifications", succeeded=True, message="Sent {} flex saldo notifications".format(c)).save()


def fetch_contract(contracts, current_day):
    """Return contract that is valid for given day, or None"""
    for contract in contracts:
        if contract.start_date <= current_day and (contract.end_date is None or contract.end_date >= current_day):
            return contract
    return None


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


def find_last_process_date(data_list, contracts, today):
    """Finds the last day for calculating flex saldo

    Stop at the last hour marking, last contract end date. Never process future entries.
    """
    last_hour_marking_day = None
    if data_list:
        last_hour_marking_day = data_list[-1]["date"]  # datetime.date for the last hour marking
    last_contract = fetch_last_contract(contracts)
    last_process_day = today
    if last_hour_marking_day and last_contract:
        last_process_day = min(max(last_hour_marking_day, last_contract.end_date), today)
    return last_process_day


def calculate_kiky_stats(person, contracts, first_process_day, last_process_day):
    hours = HourEntry.objects.exclude(status="Unsubmitted").filter(user_m=person).filter(date__gte=datetime.date(2017, 9, 1)).filter(project="KIKY - Make Finland Great again").aggregate(Sum("incurred_hours"))["incurred_hours__sum"]
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


def get_holidays(today):
    cache_key = "holidays-{:%Y-%m-%d}".format(today)
    holidays = cache.get(cache_key)
    if holidays:
        return pickle.loads(holidays)
    holidays = {k.date: k.name for k in PublicHoliday.objects.filter(date__lte=today)}
    cache.set(cache_key, pickle.dumps(holidays), 10)
    return holidays


def calculate_flex_saldo(person, flex_last_day=None, only_active=False, ignore_events=False):
    if not flex_last_day:
        flex_last_day = datetime.date.today() - datetime.timedelta(days=1)  # The default is to exclude today to have stable flex saldo (assuming everyone marks hours daily)
    contracts = WorkContract.objects.filter(user=person)
    if ignore_events:
        events = []
    else:
        events = FlexTimeCorrection.objects.filter(user=person)
    today = datetime.date.today()

    if only_active:
        if not fetch_contract(contracts, flex_last_day):
            return {"active": False}

    # Find the first date
    start_hour_markings_from_date, cumulative_saldo = find_first_process_date(events, contracts)

    holidays = get_holidays(today)

    data_list = list(HourEntry.objects.exclude(status="Unsubmitted").filter(user_m=person).filter(date__gte=start_hour_markings_from_date).exclude(date__gte=today).values("date").order_by("date")
                     .annotate(incurred_working_hours=Sum("incurred_hours", filter=~Q(phase_name__icontains="overtime") & Q(leave_type="[project]") & ~Q(project="KIKY - Make Finland Great again")))
                     .annotate(incurred_leave_hours=Sum("incurred_hours", filter=~Q(leave_type="Flex time Leave") & ~Q(leave_type="[project]") & ~Q(leave_type="Unpaid leave")))
                     .annotate(incurred_unpaid_leave=Sum("incurred_hours", filter=Q(leave_type="Unpaid leave")))
                     .annotate(incurred_overtime=Sum("incurred_hours", filter=Q(phase_name__icontains="overtime"))))

    hour_markings_data = {k["date"]: k for k in data_list}

    last_process_day = find_last_process_date(data_list, contracts, flex_last_day)
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
        if current_day in hour_markings_data:
            plus_hours_today = hour_markings_data[current_day]["incurred_working_hours"] or 0
        contract = fetch_contract(contracts, current_day)
        if not contract:
            raise FlexHourNoContractException("Hour markings for {} for {}, but no contract.".format(current_day, person))

        day_entry["flex_enabled"] = contract.flex_enabled
        day_entry["worktime_percent"] = contract.worktime_percent

        if 0 < current_day.isoweekday() < 6:
            if current_day in holidays:
                is_holiday = True
                day_entry["day_type"] = "Public holiday: {}".format(holidays[current_day])
            elif contract.flex_enabled:
                    flex_hour_deduct = contract.workday_length
                    day_entry["expected_hours_today"] = flex_hour_deduct
                    month_entry["expected_worktime"] += flex_hour_deduct
                    month_entry["diff"] -= flex_hour_deduct
        else:
            is_weekend = True
            day_entry["day_type"] = "Weekend"

        if contract.flex_enabled:
            if current_day in hour_markings_data:
                current_day_entry = hour_markings_data[current_day]
                if current_day_entry["incurred_unpaid_leave"]:
                    unpaid_hours = current_day_entry["incurred_unpaid_leave"]
                    day_entry["unpaid_leaves"] = unpaid_hours
                    day_entry["expected_hours_today"] -= unpaid_hours
                    month_entry["expected_worktime"] -= unpaid_hours
                    month_entry["diff"] += unpaid_hours

                if plus_hours_today:
                    day_entry["worktime"] = plus_hours_today
                    month_entry["worktime"] += plus_hours_today
                    month_entry["diff"] += plus_hours_today

                if current_day_entry["incurred_leave_hours"] and not is_weekend and not is_holiday:
                    leave_hours = current_day_entry["incurred_leave_hours"]
                    plus_hours_today += leave_hours
                    day_entry["leave"] = leave_hours
                    month_entry["leave"] += leave_hours
                    month_entry["diff"] += leave_hours

                if current_day_entry["incurred_overtime"]:
                    month_entry["overtime"] += current_day_entry["incurred_overtime"]
                    day_entry["overtime"] = current_day_entry["incurred_overtime"]

        day_entry["sum"] = - flex_hour_deduct + day_entry.get("worktime", 0) + day_entry.get("leave", 0) + day_entry.get("unpaid_leaves", 0)

        cumulative_saldo += day_entry["sum"]
        day_entry["cumulative_saldo"] = cumulative_saldo
        month_entry["cumulative_saldo"] = cumulative_saldo

        calculation_log.append(day_entry)
        if contract.flex_enabled:
            daily_diff.append((current_day.year, current_day.month - 1, current_day.day, plus_hours_today - flex_hour_deduct, "{:%Y-%m-%d} ({:%A}): {:.2f}h".format(current_day, current_day, plus_hours_today - flex_hour_deduct)))
        current_day += datetime.timedelta(days=1)
    calculation_log.reverse()
    if month_entry.get("month"):
        per_month_stats.append(month_entry)
    per_month_stats.reverse()
    kiky_stats = calculate_kiky_stats(person, contracts, start_hour_markings_from_date, last_process_day)

    if per_month_stats:
        months = [["{:%Y-%m}".format(entry["month"]), entry["cumulative_saldo"]] for entry in per_month_stats]
        months.reverse()
        monthly_summary_linechart_data = json.dumps([["Date", "Flex saldo (h)"]] + months)
    else:
        monthly_summary_linechart_data = None

    context = {
        "person": person,
        "contracts": contracts,
        "flex_time_events": events,
        "cumulative_saldo": cumulative_saldo + kiky_stats.get("saldo", 0),
        "calculation_log": calculation_log,
        "daily_diff": daily_diff,
        "monthly_summary": per_month_stats,
        "monthly_summary_linechart": monthly_summary_linechart_data,
        "calendar_height": min(3, len(years)) * 175,
        "kiky": kiky_stats,
    }
    return context


def sync_public_holidays():
    def process_10000ft_holiday(holiday):
        holiday["date"] = parse_date(holiday["date"])
        holiday["created_at"] = parse_datetime(holiday["created_at"])
        holiday["updated_at"] = parse_datetime(holiday["updated_at"])
        del holiday["id"]
        return holiday

    tenkfeet_api = TenkFeetApi(settings.TENKFEET_AUTH)
    holidays = [process_10000ft_holiday(holiday) for holiday in tenkfeet_api.fetch_holidays()]
    stored_holidays = {holiday.date: holiday for holiday in PublicHoliday.objects.all()}
    deleted = added = updated = 0
    for holiday in holidays:
        saved_holiday = stored_holidays.get(holiday["date"])
        if saved_holiday:
            if saved_holiday.updated_at != holiday["updated_at"]:
                print("Updating {}".format(holiday["date"]))
                updated += 1
                for arg, val in holiday.items():
                    setattr(saved_holiday, arg, val)
                saved_holiday.save()
            del stored_holidays[holiday["date"]]
        else:
            print("Creating {}".format(holiday["date"]))
            added += 1
            new_holiday = PublicHoliday(**holiday)
            new_holiday.save()
    removed_holidays = [holiday for holiday in stored_holidays]
    if removed_holidays:
        print("Deleting {}".format(", ".join([holiday.strftime("%Y-%m-%d") for holiday in removed_holidays])))
        deleted, _ = PublicHoliday.objects.filter(date__in=removed_holidays).delete()
    Event(event_type="sync_public_holidays", succeeded=True, message="Added {}, updated {}, deleted {}".format(added, updated, deleted)).save()
