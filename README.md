# Invoice checking

Simple web service for checking and approving invoices generated from hour entries.

## Contributions

To contribute to this project, fork on GitHub, commit your appropriately documented changes to a separate branch and create a new pull request.

This service is tightly integrated with 10000ft hour reporting service. Pull requests for making this more generic will be rejected.

### Pylint

Install pylint and pylint-django

Run pylint with `pylint --load-plugins pylint_django invoice_checking invoices --disable line-too-long --disable missing-docstring`. Do not add any new warnings or errors.

## Setting up the environment

Mandatory environment variables:

```
GOOGLEAUTH_APPS_DOMAIN="google-g-suite-domain"
GOOGLEAUTH_CALLBACK_DOMAIN="domain-for-this-application"
GOOGLEAUTH_CLIENT_ID="client-id-from-google-developer-console"
GOOGLEAUTH_CLIENT_SECRET="client-secret-from-google-developer-console"
GOOGLEAUTH_USE_HTTPS="True"
SECRET_KEY="long-random-generated-string"
TENKFEET_AUTH="10000ft-api-token"
REDIS_URL="url-to-redis-instance"
# optional, defaults to sqlite:
DATABASE_URL="database-url"
SECURE_SSL_REDIRECT="False"  # For local development - disable automatic redirect to https
```

For development, to avoid using Google authentication, modify `AUTHENTICATION_BACKENDS` from `invoice_checking/settings.py`.
