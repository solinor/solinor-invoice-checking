import logging

import slacker
from django.conf import settings
from invoices.models import FeetUser, SlackChannel

slack = slacker.Slacker(settings.SLACK_BOT_ACCESS_TOKEN)
logger = logging.getLogger(__name__)

def refresh_slack_users():
    slack_users = slack.users.list().body["members"]
    for member in slack_users:
        email = member.get("profile", {}).get("email")
        if not email:
            continue
        FeetUser.objects.filter(email=email).update(slack_id=member.get("id"))


def refresh_slack_channels():
    slack_channels = slack.channels.list().body["channels"]
    for channel in slack_channels:
        channel_id = channel.get("id")
        channel_name = channel.get("name")
        if channel.get("is_archived"):
            continue
        SlackChannel.objects.update_or_create(channel_id=channel_id, defaults={
            "name": channel_name,
        })

def send_slack_notification(project):
    message = """<!channel> Hi! New project was added: <https://app.10000ft.com/viewproject?id=%s|%s - %s> (created at %s)""" % (project.project_id, project.client, project.name, project.created_at)
    for channel in SlackChannel.objects.filter(new_project_notification=True):
        slack.chat.post_message(channel.channel_id, message)
