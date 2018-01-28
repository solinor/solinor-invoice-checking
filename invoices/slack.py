import datetime
import logging

import slacker
from django.conf import settings
from django.db.models import Count, Sum
from django.urls import reverse

from invoices.models import Project, SlackChannel, SlackChat, SlackChatMember, SlackNotificationBundle, TenkfUser

slack = slacker.Slacker(settings.SLACK_BOT_ACCESS_TOKEN)  # pylint:disable=invalid-name
logger = logging.getLogger(__name__)  # pylint:disable=invalid-name


def create_slack_mpim(members_list):
    slack_chat = SlackChat.objects.annotate(users_count=Count("slackchatmember")).filter(users_count=len(members_list))
    for recipient in members_list:
        slack_chat = slack_chat.filter(slackchatmember__member_id=recipient)

    if slack_chat.count() == 0:
        if len(members_list) < 2:
            logger.info("Unable to create a new chat for %s - not enough members", members_list)
            return
        logger.info("Trying to create a new Slack group chat with %s.", members_list)
        slack_chat_details = slack.mpim.open(",".join(members_list))
        chat_id = slack_chat_details.body["group"]["id"]
        slack_chat = SlackChat(chat_id=chat_id)
        slack_chat.save()
        for member in members_list:
            SlackChatMember(slack_chat=slack_chat, member_id=member).save()
        logger.info("Created a new slack.mpim for %s.", members_list)
    else:
        slack_chat = slack_chat[0]
        chat_id = slack_chat.chat_id
    return chat_id


def send_unsubmitted_hours_notifications():
    today = datetime.date.today()
    for user in TenkfUser.objects.filter(hourentry__status="Unsubmitted", hourentry__date__lt=today).annotate(entries_count=Count("hourentry__user_m")).annotate(sum_of_hours=Sum("hourentry__incurred_hours")):
        fallback_message = """<https://finance.solinor.com{}|You> have *unsubmitted hours*: {} hour markings with total of {} hours. Go to <https://app.10000ft.com|10000ft> to submit these hours.""".format(reverse("person_month", args=(str(user.guid), today.year, today.month)), user.entries_count, user.sum_of_hours)
        message = "You need to submit or remove following hours:"
        unsubmitted_hours = user.hourentry_set.filter(status="Unsubmitted").filter(date__lt=today).order_by("date")
        for unsubmitted_hour in unsubmitted_hours:
            project_name_field = "{} - {}".format(unsubmitted_hour.client, unsubmitted_hour.project)
            if unsubmitted_hour.project_m:
                project_name_field = "<https://finance.solinor.com{}|{}>".format(reverse("project", args=(unsubmitted_hour.project_m.guid,)), project_name_field)
            message += "\n- {} - {} - {} - {} - {}h - {}".format(unsubmitted_hour.date, project_name_field, unsubmitted_hour.category, unsubmitted_hour.phase_name, unsubmitted_hour.incurred_hours, unsubmitted_hour.notes)

        attachment = {
            "author_name": "Solinor Finance",
            "author_link": "https://" + settings.DOMAIN,
            "fallback": fallback_message,
            "title": "Unsubmitted hours in 10000ft",
            "title_link": "https://app.10000ft.com",
            "text": message,
            "fields": [
                {"title": "Unsubmitted markings", "value": "{}".format(user.entries_count), "short": True},
                {"title": "Unsubmitted hours", "value": "{:.2f}h".format(user.sum_of_hours), "short": True},
            ],
            "actions": [
                {
                    "type": "button",
                    "text": "Submit your hours",
                    "url": "https://app.10000ft.com",
                    "style": "primary",
                }
            ],
            "footer": "This notification is sent weekly if you have unsubmitted hours."
        }

        if not user.slack_id:
            logger.warning("No slack_id for %s", user.email)
            for admin in settings.SLACK_NOTIFICATIONS_ADMIN:
                slack.chat.post_message(admin, text="Unsubmitted hours by {}, but no slack ID available.".format(user.email), attachments=[attachment], as_user="finance-bot")
            continue

        slack.chat.post_message(user.slack_id, attachments=[attachment], as_user="finance-bot")

        for admin in settings.SLACK_NOTIFICATIONS_ADMIN:
            if admin != user.slack_id:
                slack.chat.post_message(admin, text="This was sent to {} in slack:".format(user.email), attachments=[attachment], as_user="finance-bot")
    SlackNotificationBundle(notification_type="unsubmitted").save()


def send_unapproved_hours_notifications(year, month):
    for project in Project.objects.filter(hourentry__approved=False, hourentry__date__year=year, hourentry__date__month=month).annotate(entries_count=Count("hourentry__project_m")).annotate(sum_of_hours=Sum("hourentry__incurred_hours")).annotate(sum_of_money=Sum("hourentry__incurred_money")).prefetch_related("admin_users"):
        message = """You are marked as a responsible person for {} - {}. You need to approve hours for the project weekly.""".format(project.client, project.name)
        fallback_message = """You are marked as a responsible person for {} - {}. You need to approve hours for the project weekly. Go to https://app.10000ft.com to do so.""".format(project.client, project.name)

        attachment = {
            "author_name": "Solinor Finance",
            "author_link": "https://" + settings.DOMAIN,
            "fallback": fallback_message,
            "title": "Unapproved project hours: {} - {}".format(project.client, project.name),
            "title_link": "https://app.10000ft.com",
            "text": message,
            "fields": [
                {"title": "Value", "value": "{}€".format(project.sum_of_money), "short": True},
                {"title": "Number of entries", "value": "{}".format(project.entries_count), "short": True},
                {"title": "Amount of hours", "value": "{:.2f}h".format(project.sum_of_hours), "short": True},
            ],
            "actions": [
                {
                    "type": "button",
                    "text": "See project in 10000ft",
                    "url": "https://app.10000ft.com/viewproject?id={}".format(project.project_id)
                },
                {
                    "type": "button",
                    "text": "Details in Solinor Finance",
                    "url": "https://{}{}".format(settings.DOMAIN, reverse("project", args=(project.guid,)))
                },
            ],
            "footer": "This notification is sent weekly if your project have unapproved hours.",
        }

        admin_users = project.admin_users.all()
        admin_users_count = admin_users.count()
        if admin_users_count == 0:
            logger.warning("Unapproved hours in %s, but no admin users specified.", project.project_id)
            for admin in settings.SLACK_NOTIFICATIONS_ADMIN:
                slack.chat.post_message(admin, text="Unapproved hours in {}, but no admin users specified.".format(project.project_id), attachments=[attachment], as_user="finance-bot")
            continue

        members_list = set([member.slack_id for member in project.admin_users.all() if member.slack_id])
        if len(members_list) > 1:
            chat_id = create_slack_mpim(members_list)
            if not chat_id:
                logger.warning("No chat_id for %s - %s", project, members_list)
                continue
            logger.info("%s %s", message, chat_id)
            slack.chat.post_message(chat_id, attachments=[attachment], as_user="finance-bot")
        else:
            for member in members_list:
                slack.chat.post_message(member, attachments=[attachment], as_user="finance-bot")

        for admin in settings.SLACK_NOTIFICATIONS_ADMIN:
            if admin not in members_list:
                slack.chat.post_message(admin, text="This was sent to {} in slack:".format(", ".join(project.admin_users.all()))attachments=[attachment], as_user="finance-bot")

    SlackNotificationBundle(notification_type="unapproved").save()


def refresh_slack_users():
    slack_users = slack.users.list().body["members"]
    for member in slack_users:
        email = member.get("profile", {}).get("email")
        if not email:
            continue
        TenkfUser.objects.filter(email__iexact=email).update(slack_id=member.get("id"))


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
    message = """<!channel> Hi! New project was added: <https://app.10000ft.com/viewproject?id={}|{} - {}> (created at {})""".format(project.project_id, project.client, project.name, project.created_at)
    for channel in SlackChannel.objects.filter(new_project_notification=True):
        slack.chat.post_message(channel.channel_id, message)
