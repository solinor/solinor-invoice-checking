import logging

import slacker
from invoices.models import FeetUser, SlackChannel, Project, SlackNotification, SlackChat
from django.conf import settings
from django.db.models import Count, Sum
from django.core.urlresolvers import reverse

slack = slacker.Slacker(settings.SLACK_BOT_ACCESS_TOKEN)
logger = logging.getLogger(__name__)

def send_unapproved_hours_notifications(year, month):
    for project in Project.objects.all().filter(hourentry__approved=False, hourentry__date__year=year, hourentry__date__month=month).annotate(entries_count=Count("hourentry__project_m")).annotate(sum_of_hours=Sum("hourentry__incurred_hours")).annotate(sum_of_money=Sum("hourentry__incurred_money")).prefetch_related("admin_users"):
        message = """Your project *%s - %s* has unapproved hours: %s hour markings with total of %s hours, which equals to %s euros. Go to <https://app.10000ft.com/viewproject?id=%s|10000ft> to approve these hours. See detailed info in <https://solinor-finance.herokuapp.com%s|Solinor Finance service>.""" % (project.client, project.name, project.entries_count, project.sum_of_hours, project.sum_of_money, project.project_id, reverse("project", args=(project.guid,)))

        admin_users = project.admin_users.all()
        admin_users_count = admin_users.count()
        if admin_users_count == 0:
            logger.warning("Unapproved hours in %s, but no admin users specified.", project.project_id)
            continue

        slack_chat = SlackChat.objects.annotate(admin_users_count=Count("members")).filter(admin_users_count=admin_users_count)
        for recipient in admin_users:
            slack_chat = slack_chat.filter(members=recipient)

        if slack_chat.count() == 0:
            members_list = set([member.slack_id for member in project.admin_users.all() if member.slack_id] + settings.SLACK_NOTIFICATIONS_ADMIN)
            if len(members_list) < 2:
                logger.info("Unable to create a new chat for %s - not enough members: %s.", project.project_id, members_list)
                continue
            logger.info("Trying to create a new Slack group chat with %s.", members_list)
            slack_chat_details = slack.mpim.open(u",".join(members_list))
            chat_id = slack_chat_details.body["group"]["id"]
            slack_chat = SlackChat(chat_id=chat_id)
            slack_chat.save()
            for admin_user in admin_users:
                slack_chat.members.add(admin_user)
            slack_chat.save()
            logger.info("Created a new slack.mpim for %s.", members_list)
        else:
            slack_chat = slack_chat[0]
            chat_id = slack_chat.chat_id
        logger.info(u"%s %s", message, chat_id)
        slack.chat.post_message(chat_id, message)

def refresh_slack_users():
    slack_users = slack.users.list().body["members"]
    for member in slack_users:
        email = member.get("profile", {}).get("email")
        if not email:
            continue
        FeetUser.objects.filter(email__iexact=email).update(slack_id=member.get("id"))


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
