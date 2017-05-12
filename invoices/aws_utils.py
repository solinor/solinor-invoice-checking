import csv
import datetime
from invoices.models import AmazonLinkedAccount, AmazonInvoiceRow
import pytz

def parse_aws_invoice(f):
    reader = csv.reader(f)
    header = next(reader)
    for line in reader:
        yield dict(zip(header, line))

def parse_date_record(d):
    if d == "":
        return None
    unaware = datetime.datetime.strptime(d, "%Y/%m/%d %H:%M:%S")
    return pytz.utc.localize(unaware)

def import_aws_invoice(f):
    linked_accounts = {}
    for record in parse_aws_invoice(f):
        linked_account_id = record["LinkedAccountId"]
        if linked_account_id in linked_accounts:
            linked_account = linked_accounts[linked_account_id]
        else:
            linked_account, _ = AmazonLinkedAccount.objects.update_or_create(linked_account_id=record["LinkedAccountId"], defaults={
                "name": record["LinkedAccountName"],
            })
            linked_accounts[linked_account_id] = linked_account
        if len(record["UsageQuantity"]):
            usage_quantity = float(record["UsageQuantity"])
        else:
            usage_quantity = None
        AmazonInvoiceRow.objects.update_or_create(record_id=record["RecordID"], defaults={
            "record_type": record["RecordType"],
            "billing_period_start": parse_date_record(record["BillingPeriodStartDate"]),
            "billing_period_end": parse_date_record(record["BillingPeriodEndDate"]),
            "invoice_date": parse_date_record(record["InvoiceDate"]),
            "linked_account": linked_account,
            "product_code": record["ProductCode"],
            "usage_type": record["UsageType"],
            "item_description": record["ItemDescription"],
            "usage_start": parse_date_record(record["UsageStartDate"]),
            "usage_end": parse_date_record(record["UsageEndDate"]),
            "usage_quantity": usage_quantity,
            "total_cost": float(record["TotalCost"]),
            "currency": record["CurrencyCode"],
        })
