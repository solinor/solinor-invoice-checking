import datetime
import calendar

def month_start_date(year, month):
    return datetime.date(year, month, 1)

def month_end_date(year, month):
    date = datetime.date(year, month, 1)
    return date.replace(day=calendar.monthrange(year, month)[1])
