import calendar
import datetime


def month_start_date(year, month):
    return datetime.date(year, month, 1)


def month_end_date(year, month):
    date = datetime.date(year, month, 1)
    return date.replace(day=calendar.monthrange(year, month)[1])


def daterange(start_date, end_date):
    for day_count in range(int((end_date - start_date).days) + 1):
        yield start_date + datetime.timedelta(day_count)
