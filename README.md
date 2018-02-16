# Invoice checking

Simple web service for checking and approving invoices generated from hour entries.

Master branch of [this repository](https://github.com/solinor/solinor-invoice-checking) is automatically deployed to Solinor's internal service.


## User permissions

- Do not use is_superuser for anyone. This will add options that will break the system, such as manually creating projects or invoices. Always use separate permissions.
- Always use groups to set permissions. See admin -> Authentication and Authorization -> Groups.


## Data syncing

This system does not use upstream APIs for each request. Instead, data is periodically synced.

Following data is synced:

- Public holidays (from 10000ft) - `python manage.py sync_public_holidays`
- Slack users - `python manage.py sync_data slack users`
- Slack channels - `python manage.py sync_data slack channels`
- AWS invoices - `python manage.py import_aws_billing_s3 <year> <month>` or `python manage.py import_aws_billing_s3_automatic` for current and previous months
- 10000ft projects - `python manage.py sync_data 10000ft projects`
- 10000ft users - `python manage.py sync_data 10000ft users`
- Hour entries - a separate worker process: `python manage.py process_update_queue`. Some inconsistent results are to be expected if more than one update process is running.
- If calculated invoice data is not up to date, see `python manage.py refresh_invoice_stats`. This only happens on database/code changes, during normal operations all relevant invoices are always refreshed.

**Forcing resync:** To improve performance, hour entry checksums are stored in a separate table, `invoices.HourEntryChecksum`. If you need to force updating the data, delete contents of this table. For resyncing, use `python manage.py queue_update --automatic-split --force --start-date YYYY-MM-DD --end-date YYYY-MM-DD`.

## Data cleanup

Following data accumulates and should be cleaned up periodically:

- `invoices.Event` - `python manage.py cleanup --type event`
- `invoices.DataUpdate` - `python manage.py cleanup --type dataupdate`
- Django sessions - `python manage.py clearsessions`


## Data versioning

This project uses django-reversion for versioning some of the models - see `@reversion.register()` decorators.

Be careful when adding reversions - some models, such as `invoices.HourEntry` see a lot of churn. When updating hour entries, all old entries are deleted, and same entries are recreated (to sync possible changes).


## G Suite integration

G Suite is used for signing in. Steps to setup:

- Go to https://console.cloud.google.com/
- Create a new project
- Go to "APIs & Services", enable "Google+ API". No need to configure Google+.
- Go to "APIs & Services -> Credentials". Create OAuth Client ID. Select Web Application. Don't set "Authorised JavaScript origins". Set "Authorised redirect URIs" to your application's install address.
- Copy access key, secret key. Set to `GOOGLEAUTH_CLIENT_ID` and `GOOGLEAUTH_CLIENT_SECRET` variables.
- Set `GOOGLEAUTH_CALLBACK_DOMAIN` to one of the addresses you entered to "Authorized redirect URIs".
- Set `GOOGLEAUTH_APPS_DOMAIN` to your G Suite domain to restrict others from signing in.


## Slack integration

Setting up Slack integrations. You need to create two different app types on Slack side. Both are created through https://api.slack.com/apps .

Traditional slack app (required for sending direct messages without user interaction):

- Create a new traditional slack app
- Go to "OAuth & Permissions"
- Enable following permissions: "chat:write:bot" and "chat:write:user".
- Copy "Bot User OAuth Access Token" to `SLACK_BOT_ACCESS_TOKEN`. Token starts with `xoxb-`.
- Go to "Bot users", and create "finance-bot" user, enable "Always Show My Bot as Online".

Workspace slack app (required for interactive commands and link unfurling):

- As of 2018-02-16, use https://api.slack.com/apps?new_app_token=1 (alternatively, go to https://api.slack.com/apps , click create and select "Interested in the next generation of apps?")
- Go to "OAuth & Permissions"
- Enable following Scopes: `commands`, `channels:read`, `chat:write`, `groups:read`, `im:read`, `im:write`, `links:read`, `links:write`, `mpim:write`, `team:read`, `usergroups:read`, `users.profile:read`, `users:read`, `users:read.email`.
- Go to "Slash commands". Create a new command `/flex-hours`. Request URL is `https://your-installation-domain/slack_query_flex_saldo`.
- Go to "Install App", and install to your workspace. You need to reinstall the app every time you change scopes etc.
- Go to "OAuth & Permissions" and copy "OAuth Access Token" to `SLACK_WORKSPACE_ACCESS_TOKEN`. Starts with `xoxa-`. This changes every time you change scopes and/or reinstall the app.
- Go to "Basic information". Copy "Verification Token" and set it to `SLACK_VERIFICATION_TOKEN`. Reload/deploy/whatever is necessary your app, as setting up events requires this to work.
- Go to "Event Subscriptions". Enable Events. Set Request URL to `https://your-installation-domain/incoming_slack_event` - this won't go through if you didn't finish the last step. Add `link_shared` event. Add your app domain(s) to App Unfurl Domains list.


## 10000ft

Ask 10000ft API token from local 10000ft admin user. Set to TENKFEET_AUTH variable. A long base64-encoded string.


## Heroku configuration

Hobby dyno is easily enough - no need to go with professional dynos.

Resources:

- Papertrail: log search
- Sentry: error logging and alerting
- Heroku scheduler: periodic syncing and notifications
- Pingdom: monitoring
- Heroku redis (hobby): caching, queuing
- Heroku Postgres (hobby): storage
- Deploy hooks: slack notification and Sentry deployment status

Buildpacks:

- heroku/python
- https://github.com/ojarva/django-compressor-heroku-buildpack.git - django compressor

Automatic deploys:

- After CI passes, deploy master branch to dyno

Config variables:

- See `settings.py` for up-to-date list of variables that need/should be set.


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
2. Update 10000ft projects and users: `./manage.py sync_10000ft_projects && ./manage.py sync_10000ft_users`
3. Start background worker: `./manage.py process_update_queue`, in order to actually fetch data from 10000ft with the "Request data update" button.
4. Start the server with `./manage.py runserver` and navigate to http://localhost:8000

If you are starting with empty database, after first hours refresh from 10000ft, run `./manage.py sync_10000ft_projects` to link hours to projects.

If you want to avoid using Google authentication, remove `googleauth.backends.GoogleAuthBackend` from `AUTHENTICATION_BACKENDS` list from `invoice_checking/settings.py`.
