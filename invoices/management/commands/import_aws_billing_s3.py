import datetime
import json
import tempfile
import pytz

import boto3

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings

from invoices.models import AmazonLinkedAccount, AmazonInvoiceRow
from invoices.aws_utils import import_aws_invoice


class Command(BaseCommand):
    help = 'Import AWS billing CSV from S3'

    def add_arguments(self, parser):
        parser.add_argument('year', nargs=1, type=str)
        parser.add_argument('month', nargs=1, type=str)

    def handle(self, *args, **options):
        year = options["year"][0]
        month = options["month"][0]
        s3 = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY,
            aws_secret_access_key=settings.AWS_SECRET_KEY,
        )
        with tempfile.TemporaryFile() as data:
            s3.download_fileobj("solinor-hostmaster-billing", "321914701408-aws-billing-csv-%s-%s.csv" % (year, month), data)
            data.seek(0)
            import_aws_invoice(data, int(year), int(month))
