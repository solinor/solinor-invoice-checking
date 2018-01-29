#!/bin/bash
set -e
isort --diff --check --recursive slack_hooks flex_hours invoice_checking invoices *.py
