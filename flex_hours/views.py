# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from invoices.models import FeetUser, HourEntry
from flex_hours.models import *
import datetime

def calc_flex_hours(user):
    hours = HourEntry.objects.filter(user_m=user)
    holidays = PublicHoliday.objects.all()
    contracts = WorkContract.objects.filter(user=user)
    corrections = FlexTimeCorrection.objects.filter(user=user)

    today = datetime.date.today()
    current_date = contracts[0].start_date - datetime.timedelta(days=1)
    working_hours = 0
    while current_date <= today:
        current_date += datetime.timedelta(days=1)
        if current_date.isoweekday() > 5:  # weekend
            continue
        is_holiday = False
        for holiday in holidays:
            if holiday.date == current_date:
                is_holiday = True
                break
        if is_holiday:  # public holiday
            continue

        contract_found = False
        for contract in contracts:
            if current_date >= contract.start_date and current_date <= contract.end_date:
                contract_found = True
                break
        if not contract_found:
            raise Exception("Days without contract! %s %s" % (user, current_date))
        print current_date, current_date.isoweekday()
        if contract.flex_enabled:
            working_hours += 7.5 * (float(contract.worktime_percent) / 100)

    hours_worked = 0
    for hour in hours:
        skip_marking = False
        for contract in contracts:
            if hour.date >= contract.start_date and hour.date <= contract.end_date:
                if not contract.flex_enabled:
                    skip_marking = True
        if skip_marking:
            continue
        if hour.leave_type == "Flex time Leave":
            continue
        hours_worked += hour.incurred_hours
    print hours_worked
    return hours_worked - working_hours

# Create your views here.
@login_required
def all_flex_hours(request):
    user = FeetUser.objects.get(last_name="Jarva")
    calc_flex_hours(user)
    context = {}
    return render(request, "flex_hours.html", context)
