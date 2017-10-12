from invoices.models import AmazonInvoiceRow
from invoices.aws_utils import AWS_URLS

def generate_amazon_invoice_data(linked_account, entries, year, month):
    phases = {}
    total_rows = {"aws": {"incurred_money": 0, "currency": "USD", "description": "Total", "priority": 2}}
    total_entries = 0
    for entry in entries:
        if entry.record_type == "AccountTotal":
            continue
        if entry.product_code not in phases:
            phases[entry.product_code] = {"name": entry.product_code, "entries": [], "billable": True, "url": AWS_URLS.get(entry.product_code)}
        if entry.product_code not in total_rows:
            total_rows[entry.product_code] = {"incurred_money": 0, "currency": "USD", "description": entry.product_code, "priority": 1}
        total_rows[entry.product_code]["incurred_money"] += entry.total_cost
        phases[entry.product_code]["entries"].append({"price": entry.total_cost, "currency": entry.currency, "decimals": 6, "quantity": entry.usage_quantity, "description": entry.item_description, "usage": entry.usage_type})
        total_rows["aws"]["incurred_money"] += entry.total_cost
    for phase in phases.values():
        phase["entries"] = sorted(phase["entries"], key=lambda k: k['usage'])
    total_rows = sorted(total_rows.values(), key=lambda k: "%s-%s" % (k["priority"], k["description"]))
    phases = sorted(phases.values(), key=lambda k: k["name"])
    return {
        "total_rows": total_rows,
        "phases": phases,
        "total_entries": total_entries,
    }

def calculate_stats_for_hours(entries):
    phases = {}
    billable_incorrect_price = []
    non_billable_hours = []
    non_phase_specific = []
    no_category = []
    not_approved_hours = []
    empty_descriptions = []
    total_rows = {"hours": {"description": "Hour markings", "incurred_hours": 0, "incurred_money": 0, "bill_rate_avg": None, "currency": "EUR", "incurred_billable_hours": 0}}
    total_entries = 0

    for entry in entries:
        total_entries += 1
        phase_name = "%s - %s" % (entry.phase_name, entry.bill_rate)
        if phase_name not in phases:
            phases[phase_name] = {"users": {}, "billable": entry.calculated_is_billable, "incurred_hours": 0, "incurred_money": 0}
        phase_details = phases[phase_name]
        if entry.user_email not in phase_details["users"]:
            phase_details["users"][entry.user_email] = {"user_email": entry.user_email, "user_name": entry.user_name, "user_m": entry.user_m, "entries": {}}
        if entry.bill_rate not in phase_details["users"][entry.user_email]["entries"]:
            phase_details["users"][entry.user_email]["entries"][entry.bill_rate] = {"incurred_hours": 0, "incurred_money": 0}
        phase_details["users"][entry.user_email]["entries"][entry.bill_rate]["incurred_hours"] += entry.incurred_hours
        phase_details["users"][entry.user_email]["entries"][entry.bill_rate]["incurred_money"] += entry.incurred_money

        if not entry.calculated_has_proper_price and entry.calculated_is_billable:
            billable_incorrect_price.append(entry)

        if entry.calculated_is_billable:
            total_rows["hours"]["incurred_money"] += entry.incurred_money
            phase_details["incurred_money"] += entry.incurred_money
            total_rows["hours"]["incurred_billable_hours"] += entry.incurred_hours
        else:
            non_billable_hours.append(entry)
        total_rows["hours"]["incurred_hours"] += entry.incurred_hours
        phase_details["incurred_hours"] += entry.incurred_hours
        if not entry.calculated_has_phase:
            non_phase_specific.append(entry)
        if not entry.calculated_is_approved:
            not_approved_hours.append(entry)
        if not entry.calculated_has_notes:
            empty_descriptions.append(entry)
        if not entry.calculated_has_category:
            no_category.append(entry)

    if total_rows["hours"]["incurred_hours"] > 0:
        total_rows["hours"]["bill_rate_avg"] = total_rows["hours"]["incurred_money"] / total_rows["hours"]["incurred_hours"]


    stats = {
        "total_rows": total_rows,
        "phases": phases,
        "billable_incorrect_price": billable_incorrect_price,
        "non_billable_hours": non_billable_hours,
        "non_phase_specific": non_phase_specific,
        "billable_incorrect_price_count": len(billable_incorrect_price),
        "non_billable_hours_count": len(non_billable_hours),
        "non_phase_specific_count": len(non_phase_specific),
        "not_approved_hours": not_approved_hours,
        "not_approved_hours_count": len(not_approved_hours),
        "empty_descriptions": empty_descriptions,
        "empty_descriptions_count": len(empty_descriptions),
        "no_category": no_category,
        "no_category_count": len(no_category),
        "total_entries": total_entries,
    }
    stats["incorrect_entries_count"] = stats["billable_incorrect_price_count"] + stats["non_billable_hours_count"] + stats["non_phase_specific_count"] + stats["not_approved_hours_count"] + stats["empty_descriptions_count"] + stats["no_category_count"]
    return stats

def calculate_stats_for_fixed_rows(fixed_invoice_rows):
    total_rows = {}
    phases = {}
    if fixed_invoice_rows:
        total_rows["fixed"] = {"description": "Fixed rows", "incurred_money": 0}
        phases["Fixed"] = {"entries": {}, "billable": True}
        for item in fixed_invoice_rows:
            phases["Fixed"]["entries"][item.description] = {"price": item.price, "currency": "EUR"}
            total_rows["fixed"]["incurred_money"] += item.price
    return {
        "phases": phases,
        "total_rows": total_rows,
    }

def get_aws_entries(aws_accounts, month_start_date, month_end_date):
    aws_entries = {}
    for aws_account in aws_accounts:
        rows = AmazonInvoiceRow.objects.filter(linked_account=aws_account).filter(billing_period_start__date=month_start_date).filter(billing_period_end__date=month_end_date).filter(record_type="AccountTotal")
        aws_entries[aws_account] = rows
    return aws_entries

def calculate_stats_for_aws_entries(aws_entries):
    phases = {}
    total_rows = {}
    if aws_entries:
        for aws_account, aws_entries_list in aws_entries.items():
            account_key = u"Amazon Web Services"
            if account_key not in phases:
                phases[account_key] = {"entries": {}, "billable": True}
            for aws_entry in aws_entries_list:
                total_key = "aws_%s" % aws_entry.currency
                if total_key not in total_rows:
                    total_rows[total_key] = {"description": "Amazon billing (%s)" % aws_entry.currency, "incurred_money": 0, "currency": aws_entry.currency}

                total_rows[total_key]["incurred_money"] += aws_entry.total_cost
                phases[account_key]["entries"][aws_account.name] = {"aws_id": aws_account.pk, "price": aws_entry.total_cost, "currency": aws_entry.currency}
                break
            else:
                phases[account_key]["entries"][aws_account.name] = {"aws_id": aws_account.pk, "price": 0, "currency": "USD"}
    return {
        "phases": phases,
        "total_rows": total_rows,
    }

def combine_invoice_parts(*combine_stats):
    stats = {}
    for stat in combine_stats:
        for k, v in stat.items():
            if k not in stats:
                stats[k] = v
            else:
                stats[k].update(v)
    return stats

def calculate_entry_stats(hour_entries, fixed_invoice_rows=None, aws_entries=None):
    hour_stats = calculate_stats_for_hours(hour_entries)
    fixed_invoice_stats = calculate_stats_for_fixed_rows(fixed_invoice_rows)
    aws_stats = calculate_stats_for_aws_entries(aws_entries)
    return combine_invoice_parts(hour_stats, fixed_invoice_stats, aws_stats)

def calculate_weekly_entry_stats(hour_entries, aws_entries=None):
    hour_stats = calculate_stats_for_hours(hour_entries)
    aws_stats = calculate_stats_for_aws_entries(aws_entries)
    return combine_invoice_parts(hour_stats, aws_stats)