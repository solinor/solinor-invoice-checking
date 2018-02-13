import calendar
import datetime
import logging

from django.utils.dateparse import parse_date as parse_date_django
from django.utils.dateparse import parse_datetime as parse_datetime_django

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


def parse_date(timestamp):
    if timestamp:
        return parse_date_django(timestamp)
    return None


def parse_datetime(timestamp):
    if timestamp:
        return parse_datetime_django(timestamp)
    return None


def parse_float(data):
    try:
        return float(data)
    except TypeError:
        return 0.0


def month_start_date(year, month):
    return datetime.date(year, month, 1)


def month_end_date(year, month):
    date = datetime.date(year, month, 1)
    return date.replace(day=calendar.monthrange(year, month)[1])


def daterange(start_date, end_date):
    for day_count in range(int((end_date - start_date).days) + 1):
        yield start_date + datetime.timedelta(day_count)
