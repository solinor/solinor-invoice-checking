import logging

import requests
import schema
from schema import And, Or, Schema, Use

from invoices.utils import parse_date, parse_datetime, parse_float


def opt(t):
    return Or(type(None), t)


class TenkFeetApi(object):
    API_HOST = "https://api.10000ft.com"

    USERS_SCHEMA = Schema([{
        "account_owner": bool,
        "archived": bool,
        "archived_at": opt(Use(parse_datetime)),
        "billability_target": float,
        "billable": bool,
        "billrate": float,
        "created_at": opt(Use(parse_datetime)),
        "deleted": bool,
        "deleted_at": opt(Use(parse_datetime)),
        "discipline": opt(str),
        "display_name": str,
        "email": opt(And(str, Use(str.lower))),
        "employee_number": opt(str),
        "first_name": str,
        "guid": str,  # Can be validated
        "has_login": bool,
        "hire_date": opt(Use(parse_date)),
        "id": int,
        "invitation_pending": bool,
        "last_name": str,
        "location": opt(str),
        "login_type": opt(str),
        "mobile_phone": opt(str),
        "office_phone": opt(str),
        "role": opt(str),
        "termination_date": opt(Use(parse_date)),
        "thumbnail": opt(str),  # URL - can be validated
        "type": str,
        "updated_at": opt(Use(parse_datetime)),
        "user_settings": int,
        "user_type_id": int
    }])

    PROJECT_SCHEMA = Schema({
        "archived": bool,
        "archived_at": opt(Use(parse_datetime)),
        "client": opt(str),
        "created_at": opt(Use(parse_datetime)),
        "deleted_at": opt(schema.Use(parse_datetime)),
        "description": opt(str),
        "ends_at": opt(schema.Use(parse_date)),
        "guid": str,  # should be validated
        "has_pending_updates": bool,
        "id": int,
        "name": str,
        "parent_id": opt(int),
        "phase_name": opt(str),
        "project_code": str,
        "project_state": str,
        "secureurl": opt(str),  # should be validated
        "secureurl_expiration": opt(str),  # should be parsed
        "settings": int,
        "starts_at": opt(Use(parse_date)),
        "tags": {
            "data": [{"id": int, "value": str}],
            "paging": {
                "next": opt(str),
                "page": int,
                "per_page": int,
                "previous": opt(str),
                "self": str,
            },
        },
        "thumbnail": opt(str),
        "timeentry_lockout": int,
        "type": str,
        "updated_at": opt(Use(parse_datetime)),
        "use_parent_bill_rates": bool
    })

    PROJECTS_SCHEMA = Schema([PROJECT_SCHEMA])

    PHASES_SCHEMA = Schema([{
        "archived": bool,
        "archived_at": opt(Use(parse_datetime)),
        "client": opt(str),
        "created_at": opt(Use(parse_datetime)),
        "deleted_at": opt(Use(parse_datetime)),
        "description": opt(str),
        "ends_at": opt(Use(parse_date)),
        "guid": str,  # should be validated
        "has_pending_updates": bool,
        "id": int,
        "name": str,
        "parent_id": opt(int),
        "phase_name": opt(str),
        "project_code": opt(str),
        "project_state": opt(str),
        "secureurl": opt(str),  # should be validated
        "secureurl_expiration": opt(str),  # should be parsed
        "settings": int,
        "starts_at": opt(Use(parse_date)),
        "tags": {
            "data": [{"id": int, "value": str}],
            "paging": {
                "next": opt(str),
                "page": int,
                "per_page": int,
                "previous": opt(str),
                "self": str,
            },
        },
        "thumbnail": opt(str),
        "timeentry_lockout": int,
        "type": str,
        "updated_at": opt(Use(parse_datetime)),
        "use_parent_bill_rates": bool
    }])

    TIME_ENTRIES_SCHEMA = Schema([{
        "id": int,
        "assignable_id": int,
        "assignable_type": str,
        "user_id": int,
        "bill_rate": Use(parse_float),
        "bill_rate_id": opt(int),
        "date": Use(parse_date),
        "hours": Use(parse_float),
        "scheduled_hours": Use(parse_float),
        "notes": opt(str),
        "task": opt(str),
        "is_suggestion": bool,
        "created_at": Use(parse_datetime),
        "updated_at": Use(parse_datetime),
        "approvals": {
            "data": [{
                "id": int,
                "status": str,
                "approvable_id": int,
                "approvable_type": str,
                "submitted_by": int,
                "submitted_at": Use(parse_datetime),
                "approved_by": opt(int),
                "approved_at": opt(Use(parse_datetime)),
                "created_at": Use(parse_datetime),
                "updated_at": Use(parse_datetime)
            }],
            "paging": {
                "next": opt(str),
                "page": int,
                "per_page": int,
                "previous": opt(str),
                "self": str,
            }
        }
    }])

    def __init__(self, apikey):
        self.apikey = apikey
        self.logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

    def submit_hours(self, entries):
        approvables = [{"id": entry["id"], "type": "TimeEntry", "updated_at": entry["updated_at"]} for entry in entries]

        return requests.post(
            url=f"{self.API_HOST}/api/v1/approvals",
            json={
                "approvables": approvables,
                "status": "pending",
            },
            params={"auth": self.apikey}
        ).json()

    def fetch_endpoint(self, next_page):
        entries = []
        while next_page:
            self.logger.debug("Processing page %s", next_page)
            tenkfeet_data = requests.get(self.API_HOST + next_page, params={"auth": self.apikey}).json()
            next_page = tenkfeet_data["paging"]["next"]
            entries.extend(tenkfeet_data["data"])

        self.logger.info("Fetched %s entries from 10kf", len(entries))
        return entries

    def fetch_holidays(self):
        self.logger.info("Fetching holidays")
        return self.fetch_endpoint("/api/v1/holidays?per_page=1000")

    def fetch_api_hour_entries(self, start_date, end_date):
        self.logger.info("Fetching hour entries from the API: %s - %s", start_date, end_date)
        return self.TIME_ENTRIES_SCHEMA.validate(self.fetch_endpoint(
            f"/api/v1/time_entries?fields=approvals&from={start_date:%Y-%m-%d}&to={end_date:%Y-%m-%d}&per_page=10000"
        ))

    def fetch_projects(self):
        self.logger.info("Fetching projects")
        return self.PROJECTS_SCHEMA.validate(self.fetch_endpoint(
            "/api/v1/projects?per_page=1000&with_archived=true"
        ))

    def fetch_phases(self):
        self.logger.info("Fetching phases")
        return self.PHASES_SCHEMA.validate(self.fetch_endpoint(
            "/api/v1/projects?per_page=1000&with_archived=true&with_phases=true"
        ))

    def fetch_project(self, project_id):
        return self.PROJECT_SCHEMA.validate(
            requests.get(
                url=f"{self.API_HOST}/api/v1/projects/{project_id}",
                params={"auth": self.apikey}
            ).json()
        )

    def fetch_users(self):
        self.logger.info("Fetching users")
        return self.USERS_SCHEMA.validate(self.fetch_endpoint(
            "/api/v1/users?per_page=1000&with_archived=true"
        ))

    def fetch_leave_types(self):
        self.logger.info("Fetching leave types")
        return self.fetch_endpoint("/api/v1/leave_types")
