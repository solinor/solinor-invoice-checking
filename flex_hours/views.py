# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json

from django.conf import settings
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render

from flex_hours.utils import FlexHourException, calculate_flex_saldo
from invoices.models import TenkfUser


def get_flex_hours_for_user(request, person, json_responses=False, only_active=False):
    try:
        context = calculate_flex_saldo(person, only_active=only_active)
        context.update({"max_minus": settings.FLEX_MAX_MINUS, "max_plus": settings.FLEX_MAX_PLUS})
    except FlexHourException as error:
        if json_responses:
            return JsonResponse({"flex_enabled": False})
        return render(request, "error.html", {"error": error, "message": "This is normal for flex hour calculations when some required information is missing. If this is your page, please contact HR to get this fixed."})
    if json_responses:
        if not context.get("active", True):
            return HttpResponse(json.dumps({"flex_enabled": False}), content_type="application/json")
        monthly_saldos = reversed([month.get("cumulative_saldo", 0) for month in context["monthly_summary"]][0:12])
        return JsonResponse({"monthly_saldos": monthly_saldos, "flex_enabled": True, "flex_hours": context["cumulative_saldo"], "kiky_saldo": context.get("kiky", {}).get("saldo")})
    return render(request, "person_flex_hours.html", context)


@permission_required("flex_hours.can_see_flex_saldos")
def flex_overview(request):
    people = TenkfUser.objects.exclude(archived=True)
    return render(request, "flex_hours.html", {"people": people, "max_minus": settings.FLEX_MAX_MINUS, "max_plus": settings.FLEX_MAX_PLUS})


@login_required
def person_flex_hours(request, user_guid):
    person = get_object_or_404(TenkfUser, guid=user_guid)
    return get_flex_hours_for_user(request, person)


@login_required
def your_flex_hours(request):
    person = get_object_or_404(TenkfUser, email=request.user.email)
    return get_flex_hours_for_user(request, person)


@login_required
def your_flex_hours_json(request):
    person = get_object_or_404(TenkfUser, email=request.user.email)
    return get_flex_hours_for_user(request, person, json_responses=True)


@login_required
def person_flex_hours_json(request, user_guid):
    person = get_object_or_404(TenkfUser, guid=user_guid)
    return get_flex_hours_for_user(request, person, json_responses=True, only_active=request.GET.get("onlyActive", False) == "true")
