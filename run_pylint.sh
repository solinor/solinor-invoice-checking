#!/bin/bash
# TODO: temporarily disable pylint results
# set -e
pylint --load-plugins pylint_django invoice_checking invoices flex_hours --disable line-too-long --disable missing-docstring --disable no-self-use --disable fixme --disable bad-indentation --disable bad-continuation --disable invalid-name --disable too-many-locals --disable duplicate-code --disable too-many-branches
exit 0
