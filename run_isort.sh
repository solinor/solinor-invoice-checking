#!/bin/bash
set -e
isort --diff --check --recursive flex_hours invoice_checking invoices *.py
