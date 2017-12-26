# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required

from flex_hours.utils import calculate_flex_saldo


@login_required
def person_flex_hours(request, user_guid):
    person = get_object_or_404(FeetUser, guid=user_guid)
    context = calculate_flex_saldo(person)
    return render(request, "person_flex_hours.html", context)
