import datetime
import json

from django.db.models import Sum


def gen_treemap_data_users(queryset, sum_by="incurred_hours", title="Hours"):
    data = [["User", "Project", title, "Diff from last month"], ["All", None, 0, 0]]
    today = datetime.date.today()
    month_ago = today - datetime.timedelta(days=30)
    two_months_ago = month_ago - datetime.timedelta(days=30)

    entries_for_past_month = queryset.exclude(client="[none]").exclude(client="").filter(date__gte=month_ago, date__lte=today).order_by("user_name").values("user_name").annotate(hours=Sum(sum_by)).values("user_name", "hours")
    entries_before_past_month = queryset.exclude(client="[none]").exclude(client="").filter(date__lte=month_ago, date__gte=two_months_ago).order_by("user_name").values("user_name").annotate(hours=Sum(sum_by)).values("user_name", "hours")

    per_user_data = {}
    for entry in entries_for_past_month:
        k = entry["user_name"]
        per_user_data[k] = {"1m": entry}

    for entry in entries_before_past_month:
        k = entry["user_name"]
        if k in per_user_data:
            per_user_data[k]["2m"] = entry

    for entry in per_user_data.values():
        if "2m" in entry:
            diff = entry["1m"]["hours"] - entry["2m"]["hours"]
        else:
            diff = 0
        data.append((entry["1m"]["user_name"], "All", entry["1m"]["hours"], diff))


    entries_for_past_month = queryset.exclude(client="[none]").exclude(client="").filter(date__gte=month_ago, date__lte=today).order_by("project", "user_name").values("project", "user_name").annotate(hours=Sum(sum_by)).values("user_name", "project", "hours")
    entries_before_past_month = queryset.exclude(client="[none]").exclude(client="").filter(date__lte=month_ago, date__gte=two_months_ago).order_by("project", "user_name").values("project", "user_name").annotate(hours=Sum(sum_by)).values("user_name", "project", "hours")

    per_user_data = {}
    for entry in entries_for_past_month:
        k = "%s - %s" % (entry["project"], entry["user_name"])
        per_user_data[k] = {"1m": entry}

    for entry in entries_before_past_month:
        k = "%s - %s" % (entry["project"], entry["user_name"])
        if k in per_user_data:
            per_user_data[k]["2m"] = entry

    for entry in per_user_data.values():
        if "2m" in entry:
            diff = entry["1m"]["hours"] - entry["2m"]["hours"]
        else:
            diff = 0
        data.append((u"%s - %s" % (entry["1m"]["project"], entry["1m"]["user_name"]), entry["1m"]["user_name"], entry["1m"]["hours"], diff))


    return (u"hours_treemap-%s-%s" % (sum_by, title), u"%s for past 30 days" % title, json.dumps(data))



def gen_treemap_data_projects(queryset, sum_by="incurred_hours", title="Hours"):
    data = [['Project', 'Client', title, 'Diff from last month'], ["All", None, 0, 0]]
    today = datetime.date.today()
    month_ago = today - datetime.timedelta(days=30)
    two_months_ago = month_ago - datetime.timedelta(days=30)
    for entry in queryset.filter(date__gte=month_ago).exclude(client="").order_by("client").values("client").distinct("client"):
        data.append((entry["client"], "All", 0, 0))

    entries_for_past_month = queryset.exclude(client="[none]").exclude(client="").filter(date__gte=month_ago, date__lte=today).order_by("project").values("project").annotate(hours=Sum(sum_by)).values("project", "client", "hours")
    entries_before_past_month = queryset.exclude(client="[none]").exclude(client="").filter(date__lte=month_ago, date__gte=two_months_ago).order_by("project").values("project").annotate(hours=Sum(sum_by)).values("project", "client", "hours")

    per_person_entries_for_past_month = queryset.exclude(client="[none]").exclude(client="").filter(date__gte=month_ago, date__lte=today).order_by("project", "user_name").values("project", "user_name").annotate(hours=Sum(sum_by)).values("user_name", "project", "client", "hours")
    per_person_entries_before_past_month = queryset.exclude(client="[none]").exclude(client="").filter(date__lte=month_ago, date__gte=two_months_ago).order_by("project", "user_name").values("project", "user_name").annotate(hours=Sum(sum_by)).values("user_name", "project", "client", "hours")

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
            diff = entry["1m"]["hours"] - entry["2m"]["hours"]
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
            diff = entry["1m"]["hours"] - entry["2m"]["hours"]
        else:
            diff = 0
        data.append((u"%s - %s" % (entry["1m"]["user_name"], entry["1m"]["project"]), entry["1m"]["project"], entry["1m"]["hours"], diff))

    return (u"projects_treemap-%s-%s" % (sum_by, title), u"%s for past 30 days" % title, json.dumps(data))
