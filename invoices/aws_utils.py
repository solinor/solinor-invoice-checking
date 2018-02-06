import csv
import datetime

import pytz

from invoices.models import AmazonInvoiceRow, AmazonLinkedAccount, Event, Invoice

AWS_URLS = {
    "OCBPremiumSupport": "https://aws.amazon.com/premiumsupport/",
    "AmazonEC2": "https://aws.amazon.com/ec2/",
    "awskms": "https://aws.amazon.com/kms/",
    "AWSQueueService": "https://aws.amazon.com/sqs/",
    "AmazonS3": "https://aws.amazon.com/s3/",
    "AmazonPolly": "https://aws.amazon.com/polly/",
    "AWSLambda": "https://aws.amazon.com/lambda/",
    "CodeBuild": "https://aws.amazon.com/codebuild/",
    "AmazonRDS": "https://aws.amazon.com/rds/",
    "AWSCodePipeline": "https://aws.amazon.com/codepipeline/",
    "AmazonRoute53": "https://aws.amazon.com/route53/",
    "AmazonECR": "https://aws.amazon.com/ecr/",
    "AmazonRegistrar": "http://docs.aws.amazon.com/Route53/latest/DeveloperGuide/registrar.html",
    "APNFee": "https://aws.amazon.com/partners/",
    "AmazonLex": "https://aws.amazon.com/lex/",
    "AmazonDynamoDB": "https://aws.amazon.com/dynamodb/",
    "AmazonElastiCache": "https://aws.amazon.com/elasticache/",
    "AmazonApiGateway": "https://aws.amazon.com/api-gateway/",
    "AmazonCloudFront": "https://aws.amazon.com/cloudfront/",
    "AmazonSNS": "https://aws.amazon.com/sns/",
    "AWSCloudTrail": "https://aws.amazon.com/cloudtrail/",
    "AmazonSES": "https://aws.amazon.com/ses/",
    "AWSXRay": "https://aws.amazon.com/xray/",
    "AmazonCloudWatch": "https://aws.amazon.com/cloudwatch/",
    "AmazonVPC": "https://aws.amazon.com/vpc/",
    "AmazonEFS": "https://aws.amazon.com/efs/",
    "AWSCodeCommit": "https://aws.amazon.com/codecommit/",
}


def parse_aws_invoice(file_obj):
    reader = csv.reader(file_obj)
    header = next(reader)
    for line in reader:
        yield dict(zip(header, line))


def parse_date_record(timestamp):
    if timestamp == "":
        return None
    unaware = datetime.datetime.strptime(timestamp, "%Y/%m/%d %H:%M:%S")
    return pytz.utc.localize(unaware)


def import_aws_invoice(file_obj, year, month):
    invoice_month = datetime.date(year, month, 1)
    linked_accounts = {}
    c = 0
    for record in parse_aws_invoice(file_obj):
        c += 1
        linked_account_id = record["LinkedAccountId"]
        if record["UsageQuantity"]:
            usage_quantity = float(record["UsageQuantity"])
        else:
            usage_quantity = None
        if record["TotalCost"]:
            total_cost = float(record["TotalCost"])
        else:
            total_cost = None
        record_data = {
            "record_type": record["RecordType"],
            "billing_period_start": parse_date_record(record["BillingPeriodStartDate"]),
            "billing_period_end": parse_date_record(record["BillingPeriodEndDate"]),
            "invoice_date": parse_date_record(record["InvoiceDate"]),
            "product_code": record["ProductCode"],
            "usage_type": record["UsageType"],
            "item_description": record["ItemDescription"],
            "usage_start": parse_date_record(record["UsageStartDate"]),
            "usage_end": parse_date_record(record["UsageEndDate"]),
            "usage_quantity": usage_quantity,
            "total_cost": total_cost,
            "currency": record["CurrencyCode"],
            "invoice_month": invoice_month,
        }
        if linked_account_id in linked_accounts:
            linked_account = linked_accounts[linked_account_id]
        else:
            linked_account, _ = AmazonLinkedAccount.objects.update_or_create(linked_account_id=record["LinkedAccountId"], defaults={
                "name": record["LinkedAccountName"],
            })
            linked_accounts[linked_account_id] = linked_account
            for project in linked_account.project_set.all():
                year = invoice_month.year
                month = invoice_month.month
                Invoice.objects.get_or_create(year=year, month=month, client=project.client, project=project.name, project_m=project)
        record_data["linked_account"] = linked_account
        record_id = record["RecordID"] + invoice_month.strftime("%Y-%m-%d")
        AmazonInvoiceRow.objects.update_or_create(record_id=record_id, defaults=record_data)
    Event(event_type="sync_aws_invoice", succeeded=True, message=f"Synced {invoice_month}. {c} entries.").save()
