import logging

import requests
import schema
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime


class TenkFeetApi(object):
    NONETYPE = type(None)

    USERS_SCHEMA = schema.Schema([{
        "account_owner": bool,
        "archived": bool,
        "archived_at": schema.Or(schema.Use(parse_datetime), NONETYPE),
        "billability_target": float,
        "billable": bool,
        "billrate": float,
        "created_at": schema.Or(schema.Use(parse_datetime), NONETYPE),
        "deleted": bool,
        "deleted_at": schema.Or(schema.Use(parse_datetime), NONETYPE),
        "discipline": schema.Or(str, NONETYPE),
        "display_name": str,
        "email": schema.Or(NONETYPE, schema.And(str, schema.Use(str.lower))),
        "employee_number": schema.Or(str, NONETYPE),
        "first_name": str,
        "guid": str,  # Can be validated
        "has_login": bool,
        "hire_date": schema.Or(schema.Use(parse_date), NONETYPE),
        "id": int,
        "invitation_pending": bool,
        "last_name": str,
        "location": schema.Or(str, NONETYPE),
        "login_type": schema.Or(str, NONETYPE),
        "mobile_phone": schema.Or(str, NONETYPE),
        "office_phone": schema.Or(str, NONETYPE),
        "role": schema.Or(str, NONETYPE),
        "termination_date": schema.Or(schema.Use(parse_date), NONETYPE),
        "thumbnail": schema.Or(str, NONETYPE),  # URL - can be validated
        "type": str,
        "updated_at": schema.Or(schema.Use(parse_datetime), NONETYPE),
        "user_settings": int,
        "user_type_id": int
    }])

    PROJECTS_SCHEMA = schema.Schema([{
        "archived": bool,
        "archived_at": schema.Or(schema.Use(parse_datetime), NONETYPE),
        "client": schema.Or(str, NONETYPE),
        "created_at": schema.Or(schema.Use(parse_datetime), NONETYPE),
        "deleted_at": schema.Or(schema.Use(parse_datetime), NONETYPE),
        "description": schema.Or(str, NONETYPE),
        "ends_at": schema.Or(schema.Use(parse_date), NONETYPE),
        "guid": str,  # should be validated
        "has_pending_updates": bool,
        "id": int,
        "name": str,
        "parent_id": schema.Or(int, NONETYPE),
        "phase_name": schema.Or(str, NONETYPE),
        "project_code": str,
        "project_state": str,
        "secureurl": schema.Or(str, NONETYPE),  # should be validated
        "secureurl_expiration": schema.Or(str, NONETYPE),  # should be parsed
        "settings": int,
        "starts_at": schema.Or(schema.Use(parse_date), NONETYPE),
        "tags": {
            "data": [{"id": int, "value": str}],
            "paging": {
                "next": schema.Or(str, NONETYPE),
                "page": int,
                "per_page": int,
                "previous": schema.Or(str, NONETYPE),
                "self": str,
            },
        },
        "thumbnail": schema.Or(str, NONETYPE),
        "timeentry_lockout": int,
        "type": str,
        "updated_at": schema.Or(schema.Use(parse_datetime), NONETYPE),
        "use_parent_bill_rates": bool
    }])

    HOUR_ENTRIES_SCHEMA = schema.Schema([
        [
            int,
            str,
            int,
            str,
            str,
            str,
            str,
            str,  # Date (Friday, 29.12.2017), could be parsed
            float,
            float,
            float,
            float,
            float,
            float,
            str,
            schema.Or(str, NONETYPE),
            str,
            str,
            str,
            str,
            str,
            int,
            str,
            schema.Or(str, NONETYPE),
            schema.Or(str, NONETYPE),
            str,  # Date (2017-01-01)
            str,  # Date (2017-01-01)
            schema.Or(str, NONETYPE),
            float,
            str,  # email
            int,
            str,
            schema.Or(str, NONETYPE),
            str,
            schema.Or(str, NONETYPE),
            str,
            str,
            int,
            int,
            int,
            str,  # Date (2017-01-01)
            str,
            str,
            str,
            int,
            int,
            int,
            str,
            float,
            str,  # YYYY-MM
            str,
            int,
            str,
            schema.Or(str, NONETYPE),
            schema.Or(str, NONETYPE),
            str,
            str,
            str,
            str,
            str,
        ]
    ])

    def __init__(self, apikey):
        self.apikey = apikey
        self.logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

    def submit_hours(self, entries):
        url = f"https://api.10000ft.com/api/v1/approvals?auth={self.apikey}"
        approvables = [{"id": entry["id"], "type": "TimeEntry", "updated_at": entry["updated_at"]} for entry in entries]

        data = {
            "approvables": approvables,
            "status": "pending",
        }
        return requests.post(url, json=data).json()

    def fetch_endpoint(self, next_page):
        entries = []
        while next_page:
            self.logger.debug("Processing page %s", next_page)
            url = f"https://api.10000ft.com{next_page}&auth={self.apikey}"
            tenkfeet_data = requests.get(url).json()
            next_page = tenkfeet_data["paging"]["next"]
            entries.extend(tenkfeet_data["data"])
        self.logger.info("Fetched %s entries from 10kf", len(entries))
        return entries

    def fetch_holidays(self):
        self.logger.info("Fetching holidays")
        url = "/api/v1/holidays?per_page=250"
        return self.fetch_endpoint(url)

    def fetch_api_hour_entries(self, start_date, end_date):
        self.logger.info("Fetching hour entries from the API: %s - %s", start_date, end_date)
        url = f"/api/v1/time_entries?fields=approvals&with_suggestions=false&from={start_date:%Y-%m-%d}&to={end_date:%Y-%m-%d}&per_page=250"
        return self.fetch_endpoint(url)

    def fetch_projects(self):
        self.logger.info("Fetching projects")
        next_page = "/api/v1/projects?per_page=250&page=1&with_archived=true"
        return self.PROJECTS_SCHEMA.validate(self.fetch_endpoint(next_page))

    def fetch_project(self, project_id):
        url = f"https://api.10000ft.com/api/v1/projects/{project_id}?auth={self.apikey}"
        return requests.get(url).json()

    def fetch_hour_entries(self, start_date, end_date, validate_schema=False):
        # This defaults to validate_schema=False, as validation does not add much value, and takes quite a while (~15sec for 5000 entries)
        self.logger.info("Fetching hour entries reporting API: %s - %s", start_date, end_date)
        now = timezone.now()
        url = f"https://api.10000ft.com/api/v1/reports.json?startdate={start_date:%Y-%m-%d}&enddate={end_date:%Y-%m-%d}&today={now:%Y-%m-%d}&auth={self.apikey}"
        tenkfeet_data = requests.get(url).json()["time_entries"]
        self.logger.info("Fetched %s hour entries", len(tenkfeet_data))
        if validate_schema:
            return self.HOUR_ENTRIES_SCHEMA.validate(tenkfeet_data)
        return tenkfeet_data

    def fetch_users(self):
        self.logger.info("Fetching users")
        next_page = "/api/v1/users?per_page=250&page=1&with_archived=true"
        return self.USERS_SCHEMA.validate(self.fetch_endpoint(next_page))
