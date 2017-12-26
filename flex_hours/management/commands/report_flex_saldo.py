from django.core.management.base import BaseCommand
from flex_hours.utils import calculate_flex_saldo
from invoices.models import FeetUser


class Command(BaseCommand):
    help = 'Report flex saldo for everyone'

    def handle(self, *args, **options):
        users = []
        for user in FeetUser.objects.all():
            flex_info = calculate_flex_saldo(user)
            if not isinstance(flex_info, dict):
                continue
            users.append((flex_info["person"].email, flex_info["flex_hours"]))
        users = sorted(users, key=lambda k: k[1])
        for email, flex_hours in users:
            print("%s - %sh" % (email, flex_hours))
