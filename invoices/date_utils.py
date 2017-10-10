import datetime
import calendar

def month_start_date(year, month):
    return datetime.date(year, month, 1)

def month_end_date(year, month):
    date = datetime.date(year, month, 1)
    return date.replace(day=calendar.monthrange(year, month)[1])

def week_start_date(year, week):
    d = "%d-W%d" % (year, week)
    return datetime.datetime.strptime(d + '-1', "%Y-W%W-%w")

def week_end_date(year, week):
    date = week_start_date(year, week)
    return date + datetime.timedelta(days=7)
