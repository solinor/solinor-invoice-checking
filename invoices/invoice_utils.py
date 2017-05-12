

def generate_amazon_invoice_data(linked_account, entries, year, month):
    phases = {linked_account.name: {"entries": {}, "billable": True}}
    total_rows = {"aws": {"incurred_money": 0, "currency": "USD"}}
    total_entries = 0
    for entry in entries:
        if entry.record_type == "AccountTotal":
            continue
        phases[linked_account.name]["entries"]["%s - %s" % (entry.product_code, entry.usage_type)] = {"price": entry.total_cost, "currency": entry.currency}
        total_rows["aws"]["incurred_money"] += entry.total_cost
    return {
        "total_rows": total_rows,
        "phases": phases,
        "total_entries": total_entries,
    }
