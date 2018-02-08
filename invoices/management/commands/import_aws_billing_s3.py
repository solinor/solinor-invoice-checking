import tempfile

import boto3
from django.conf import settings
from django.core.management.base import BaseCommand

from invoices.aws_utils import import_aws_invoice


class Command(BaseCommand):
    help = "Import AWS billing CSV from S3"

    def add_arguments(self, parser):
        parser.add_argument("year", nargs=1, type=int)
        parser.add_argument("month", nargs=1, type=int)

    def handle(self, *args, **options):
        year = options["year"][0]
        month = "{:02d}".format(options["month"][0])
        s3_client = boto3.client("s3", aws_access_key_id=settings.AWS_ACCESS_KEY, aws_secret_access_key=settings.AWS_SECRET_KEY)
        with tempfile.NamedTemporaryFile(mode="w+b") as data:
            s3_client.download_fileobj("solinor-hostmaster-billing", f"321914701408-aws-billing-csv-{year}-{month}.csv", data)
            data.seek(0)
            infile = open(data.name, mode="rt")
            import_aws_invoice(infile, int(year), int(month))
