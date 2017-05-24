from invoices.models import *
from django.db.models import Sum

import datetime
import json

def gen_treemap_data(queryset):
    data = [['Project', 'Client', 'Hours', 'Diff from last month'], ["All", None, 0, 0]]
    today = datetime.date.today()
    month_ago = today - datetime.timedelta(days=30)
    two_months_ago = month_ago - datetime.timedelta(days=30)
    for entry in queryset.filter(date__gte=month_ago).order_by("client").values("client").distinct("client"):
        data.append((entry["client"], "All", 0, 0))

    entries_for_past_month = queryset.filter(date__gte=month_ago, date__lte=today).order_by("project").values("project").annotate(hours=Sum("incurred_hours")).values("project", "client", "hours")
    entries_before_past_month =  queryset.filter(date__lte=month_ago, date__gte=two_months_ago).order_by("project").values("project").annotate(hours=Sum("incurred_hours")).values("project", "client", "hours")

    per_person_entries_for_past_month = queryset.exclude(client="[none]").filter(date__gte=month_ago, date__lte=today).order_by("project").values("project", "user_name").annotate(hours=Sum("incurred_hours")).values("user_name", "project", "client", "hours")
    per_person_entries_before_past_month = queryset.exclude(client="[none]").filter(date__lte=month_ago, date__gte=two_months_ago).order_by("project").values("project", "user_name").annotate(hours=Sum("incurred_hours")).values("user_name", "project", "client", "hours")

    per_project_data = {}
    for entry in entries_for_past_month:
        k = "%s - %s" % (entry["client"], entry["project"])
        per_project_data[k] = {"1m": entry}

    for entry in entries_before_past_month:
        k = "%s - %s" % (entry["client"], entry["project"])
        if k in per_project_data:
            per_project_data[k]["2m"] = entry

    for entry in per_project_data.values():
        if "2m" in entry:
            diff = entry["2m"]["hours"] - entry["1m"]["hours"]
        else:
            diff = 0
        data.append((entry["1m"]["project"], entry["1m"]["client"], entry["1m"]["hours"], diff))

    per_user_data = {}
    for entry in per_person_entries_for_past_month:
        k = "%s - %s - %s" % (entry["user_name"], entry["client"], entry["project"])
        per_user_data[k] = {"1m": entry}

    for entry in per_person_entries_before_past_month:
        k = "%s - %s - %s" % (entry["user_name"], entry["client"], entry["project"])
        if k in per_user_data:
            per_user_data[k]["2m"] = entry

    for entry in per_user_data.values():
        if "2m" in entry:
            diff = entry["2m"]["hours"] - entry["1m"]["hours"]
        else:
            diff = 0
        data.append((u"%s - %s" % (entry["1m"]["user_name"], entry["1m"]["project"]), entry["1m"]["project"], entry["1m"]["hours"], diff))

    return ("projects_treemap", "Projects for past 30 days", json.dumps(data))
