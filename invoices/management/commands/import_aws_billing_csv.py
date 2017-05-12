import datetime
import json
import pytz

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings

from invoices.models import AmazonLinkedAccount, AmazonInvoiceRow
from invoices.aws_utils import import_aws_invoice


class Command(BaseCommand):
    help = 'Import AWS billing CSV'

    def add_arguments(self, parser):
        parser.add_argument('filename', nargs=1, type=str)

    def handle(self, *args, **options):
        f = open(options["filename"][0])
        import_aws_invoice(f)
