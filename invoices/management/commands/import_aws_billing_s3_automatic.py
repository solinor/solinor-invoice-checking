import datetime
import tempfile

import boto3
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from invoices.aws_utils import import_aws_invoice


class Command(BaseCommand):
    help = "Import AWS billing CSV from S3"

    def handle(self, *args, **options):
        s3_client = boto3.client("s3", aws_access_key_id=settings.AWS_ACCESS_KEY, aws_secret_access_key=settings.AWS_SECRET_KEY)
        today = timezone.now()
        fetch_months = [today]
        if today.day < 5:
            fetch_months = [(today - datetime.timedelta(days=10))]
        for date in fetch_months:
            with tempfile.NamedTemporaryFile(mode="w+b") as data:
                s3_client.download_fileobj("solinor-hostmaster-billing", f"321914701408-aws-billing-csv-{date:%Y-%m}.csv", data)
                data.seek(0)
                infile = open(data.name, mode="rt")
                import_aws_invoice(infile, date.year, date.month)
