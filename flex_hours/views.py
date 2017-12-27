# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from flex_hours.utils import FlexHourException, calculate_flex_saldo
from invoices.models import TenkfUser


@login_required
def person_flex_hours(request, user_guid):
    person = get_object_or_404(TenkfUser, guid=user_guid)
    try:
        context = calculate_flex_saldo(person)
    except FlexHourException as error:
        return render(request, "error.html", {"error": error, "message": "This is normal for flex hour calculations when some required information is missing. If this is your page, please contact HR to get this fixed."})
    return render(request, "person_flex_hours.html", context)
