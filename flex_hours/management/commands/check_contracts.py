import datetime
from collections import defaultdict

import slacker
from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import reverse

from flex_hours.models import FlexTimeCorrection, WorkContract
from flex_hours.utils import FlexHourException, calculate_flex_saldo
from invoices.models import Event, HourEntry, TenkfUser


class Command(BaseCommand):
    help = "Check contract information"

    def handle(self, *args, **options):
        errors = []
        work_contracts = WorkContract.objects.select_related("user")
        per_user_contracts = defaultdict(list)
        for contract in work_contracts:
            per_user_contracts[contract.user.email].append(contract)
        flex_time_corrections = FlexTimeCorrection.objects.order_by("date")  # Important to order by date for "start_date_by_user" collection
        start_date_by_user = {}
        for correction in flex_time_corrections:
            if correction.set_to is not None:  # can be 0
                start_date_by_user[correction.user.email] = correction.date
        for correction in flex_time_corrections:
            if correction.user.email not in per_user_contracts:
                errors.append("Flex saldo correction ({}) for user {} but no contracts defined.".format(correction, correction.user.email))
                continue
            if correction.adjust_by is not None:
                for contract in per_user_contracts[correction.user.email]:
                    if contract.start_date >= correction.date >= contract.end_date:
                        break
                else:
                    if correction.date < start_date_by_user[correction.user.email]:
                        errors.append("Flex saldo adjustment ({}) for user {} but no valid contract defined.".format(correction, correction.user.email))

        hour_entries = HourEntry.objects.exclude(user_m=None).filter(date__gte=datetime.datetime(2017, 10, 1)).values("user_m__email", "date").order_by("user_m__email", "date").distinct()
        users_with_no_contracts = set()
        for entry in hour_entries:
            if entry["user_m__email"] in users_with_no_contracts:
                continue
            if entry["user_m__email"] not in per_user_contracts:
                errors.append("No contract for {} ({})".format(entry["user_m__email"], entry["date"]))
                users_with_no_contracts.add(entry["user_m__email"])
                continue
            for contract in work_contracts:
                if contract.start_date <= entry["date"] <= contract.end_date:
                    break
            else:
                errors.append("No contract for {} ({})".format(entry["user_m__email"], entry["date"]))
                users_with_no_contracts.add(entry["user_m__email"])

        message = "Following errors with flex hour contracts were found:\n"
        for error in errors:
            print(error)
            message += "- " + error + "\n"

        if errors:
            slack = slacker.Slacker(settings.SLACK_BOT_ACCESS_TOKEN)
            message += "<{}{}|Edit in {}>".format(settings.DOMAIN, reverse("admin:index"), settings.DOMAIN)
            for user in settings.SLACK_NOTIFICATIONS_ADMIN:
                slack.chat.post_message(channel=user, text=message, as_user="finance-bot")
                print("Sent report to {}".format(user))

        Event(event_type="check_contracts", succeeded=True, message="Found {} issues".format(len(errors))).save()
