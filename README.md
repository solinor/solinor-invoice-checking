# Invoice checking

Simple web service for checking and approving invoices generated from hour entries.

## Contributions

To contribute to this project, fork on GitHub, commit your appropriately documented changes to a separate branch and create a new pull request.

This service is tightly integrated with 10000ft hour reporting service. Pull requests for making this more generic will be rejected.

### Code checks

Install `pycodestyle`, `pylint` and `isort`. Exact versions can be checked from `.travis.yml`

Run

```
./run_pylint.sh
./run_isort.sh
./run_pycodestyle.sh
```

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
# optional, defaults to sqlite. Do note that sqlite does not support all SQL operations used, so not all pages will work properly. PostgreSQL recommended.
DATABASE_URL="database-url"
SECURE_SSL_REDIRECT="False"  # For local development - disable automatic redirect to https
SLACK_BOT_ACCESS_TOKEN="slack-bot-token"
AWS_SECRET_KEY="aws-secret-key"
AWS_ACCESS_KEY="aws-access-key"
```

## Local development

For local development:

1. Collect static files: `./manage.py collectstatic && ./manage.py compress --force`
2. Update 10000ft projects and users: `./manage.py update_projects && ./manage.py update_users`
3. Start background worker: `./manage.py process_update_queue`, in order to actually fetch data from 10000ft with the "Request data update" button.
4. Start the server with `./manage.py runserver` and navigate to http://localhost:8000

If you are starting with empty database, after first hours refresh from 10000ft, run `./manage.py update_projects` to link hours to projects.

If you want to avoid using Google authentication, remove `googleauth.backends.GoogleAuthBackend` from `AUTHENTICATION_BACKENDS` list from `invoice_checking/settings.py`.
