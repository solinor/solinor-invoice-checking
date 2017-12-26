import logging

import requests
from django.utils import timezone


class TenkFeetApi(object):
    def __init__(self, apikey):
        self.apikey = apikey
        self.logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

    def fetch_endpoint(self, next_page):
        entries = []
        while next_page:
            self.logger.debug("Processing page %s", next_page)
            url = "https://api.10000ft.com%s&auth=%s" % (next_page, self.apikey)
            tenkfeet_data = requests.get(url).json()
            next_page = tenkfeet_data["paging"]["next"]
            entries.extend(tenkfeet_data["data"])
        self.logger.info("Fetched %s entries from 10kf", len(entries))
        return entries

    def fetch_projects(self):
        self.logger.info("Fetching projects")
        next_page = "/api/v1/projects?per_page=250&page=1&with_archived=true"
        return self.fetch_endpoint(next_page)

    def fetch_hour_entries(self, now, start_date, end_date):
        self.logger.info("Fetching hour entries: %s - %s", start_date, end_date)
        now = timezone.now()
        url = "https://api.10000ft.com/api/v1/reports.json?startdate=%s&enddate=%s&today=%s&auth=%s" % (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d"), self.apikey)
        tenkfeet_data = requests.get(url).json()["time_entries"]
        self.logger.info("Fetched %s hour entries", len(tenkfeet_data))
        return tenkfeet_data

    def fetch_users(self):
        self.logger.info("Fetching users")
        next_page = "/api/v1/users?per_page=250&page=1"
        return self.fetch_endpoint(next_page)
