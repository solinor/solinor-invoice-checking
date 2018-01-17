import datetime
from collections import defaultdict

import slacker
from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import reverse

from flex_hours.models import FlexTimeCorrection, WorkContract
from flex_hours.utils import FlexHourException, calculate_flex_saldo
from invoices.models import HourEntry, TenkfUser


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
            if correction.user.email not in per_user_contracts:
                errors.append("Flex saldo correction (%s) for user %s but no contracts defined." % (correction, correction.user.email))
                continue
            if correction.adjust_by is not None:
                for contract in per_user_contracts[correction.user.email]:
                    if contract.start_date >= correction.date >= contract.end_date:
                        break
                else:
                    errors.append("Flex saldo adjustment (%s) for user %s but no valid contract defined." % (correction, correction.user.email))

        hour_entries = HourEntry.objects.exclude(user_m=None).filter(date__gte=datetime.datetime(2017, 10, 1)).order_by("user_m", "date").distinct("user_m", "date").select_related("user_m")
        users_with_no_contracts = set()
        for entry in hour_entries:
            if entry.user_m.email in users_with_no_contracts:
                continue
            if entry.user_m.email not in per_user_contracts:
                errors.append("No contract for %s (%s)" % (entry.user_m.email, entry.date))
                users_with_no_contracts.add(entry.user_m.email)
                continue

        message = "Following errors with flex hour contracts were found:\n"
        for error in errors:
            print(error)
            message += "- " + error + "\n"

        if errors:
            slack = slacker.Slacker(settings.SLACK_BOT_ACCESS_TOKEN)
            message += "<%s%s|Edit in %s>" % (settings.DOMAIN, reverse("admin:index"), settings.DOMAIN)
            for user in settings.SLACK_NOTIFICATIONS_ADMIN:
                slack.chat.post_message(channel=user, text=message)
                print("Sent report to %s" % user)
