import datetime
import json
import logging

import redis
import slacker
from django.conf import settings
from django.db.models import Count, Sum
from django.urls import reverse

from invoices.models import Event, Project, SlackChannel, SlackChat, SlackChatMember, SlackNotificationBundle, TenkfUser

slack = slacker.Slacker(settings.SLACK_BOT_ACCESS_TOKEN)  # pylint:disable=invalid-name
logger = logging.getLogger(__name__)  # pylint:disable=invalid-name
redis_client = redis.from_url(settings.REDIS)  # pylint:disable=invalid-name


def queue_slack_notification(notification_type):
    if notification_type not in ("unapproved", "unsubmitted"):
        raise ValueError("Invalid notification type")
    redis_client.publish("request-refresh", json.dumps({"type": f"slack-{notification_type}-notification"}))


def create_slack_mpim(members_list):
    slack_chat = SlackChat.objects.annotate(users_count=Count("slackchatmember")).filter(users_count=len(members_list))
    for recipient in members_list:
        slack_chat = slack_chat.filter(slackchatmember__member_id=recipient)

    if slack_chat.count() == 0:
        if len(members_list) < 2:
            logger.info("Unable to create a new chat for %s - not enough members", members_list)
            return None
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


def send_unsubmitted_hours_notifications(first_day, last_day):
    today = datetime.date.today()
    notification_count = 0
    for user in TenkfUser.objects.filter(hourentry__status="Unsubmitted", hourentry__date__lte=last_day, hourentry__date__gte=first_day).annotate(entries_count=Count("hourentry__user_m")).annotate(sum_of_hours=Sum("hourentry__incurred_hours")):
        fallback_message = """<https://{}{}|You> have *unsubmitted hours*: {} hour markings with total of {} hours. Go to <https://app.10000ft.com|10000ft> to submit these hours.""".format(settings.DOMAIN, reverse("person_month", args=(str(user.guid), today.year, today.month)), user.entries_count, user.sum_of_hours)
        message = "You need to submit or remove following hours:"
        unsubmitted_hours = user.hourentry_set.filter(status="Unsubmitted").filter(date__lte=last_day, date__gte=first_day).exclude(invoice__project_m__archived=True).select_related("invoice", "invoice__project_m").order_by("date")  # TODO: select_related
        for unsubmitted_hour in unsubmitted_hours:
            url = "https://{}{}".format(settings.DOMAIN, reverse("project", args=(unsubmitted_hour.invoice.project_m.guid,)))
            project_name_field = f"<{url}|{unsubmitted_hour.invoice.project_m.client_m.name} - {unsubmitted_hour.invoice.project_m.name}>"
            message += "\n- {} - {} - {} - {} - {}h - {}".format(unsubmitted_hour.date, project_name_field, unsubmitted_hour.category, unsubmitted_hour.phase_name, unsubmitted_hour.incurred_hours, unsubmitted_hour.notes)

        attachment = {
            "author_name": "Solinor Finance",
            "author_link": "https://" + settings.DOMAIN,
            "fallback": fallback_message,
            "title": "Unsubmitted hours in 10000ft",
            "title_link": "https://app.10000ft.com",
            "text": message,
            "fields": [
                {"title": "Unsubmitted markings", "value": f"{user.entries_count}", "short": True},
                {"title": "Unsubmitted hours", "value": f"{user.sum_of_hours:.2f}h", "short": True},
            ],
            "actions": [
                {
                    "type": "button",
                    "text": "Submit your hours",
                    "url": "https://{}{}".format(settings.DOMAIN, reverse("your_unsubmitted_hours")),
                    "style": "primary",
                },
                {
                    "type": "button",
                    "text": "Edit in 10000ft",
                    "url": "https://app.10000ft.com",
                },
            ],
            "footer": "This notification is sent weekly if you have unsubmitted hours."
        }

        if not user.slack_id:
            logger.warning("No slack_id for %s", user.email)
            for admin in settings.SLACK_NOTIFICATIONS_ADMIN:
                slack.chat.post_message(admin, text=f"Unsubmitted hours by {user.email}, but no slack ID available.", attachments=[attachment], as_user="finance-bot")
            continue

        slack.chat.post_message(user.slack_id, attachments=[attachment], as_user="finance-bot")
        notification_count += 1

        for admin in settings.SLACK_NOTIFICATIONS_ADMIN:
            if admin != user.slack_id:
                slack.chat.post_message(admin, text=f"This was sent to {user.email} in slack:", attachments=[attachment], as_user="finance-bot")
    SlackNotificationBundle(notification_type="unsubmitted").save()
    Event(event_type="send_unsubmitted_hours_notifications", succeeded=True, message=f"Sent {notification_count} notifications").save()


def send_unapproved_hours_notifications(first_day, last_day):
    notification_count = 0
    for project in Project.objects.filter(invoice__hourentry__approved=False, invoice__hourentry__date__lte=last_day, invoice__hourentry__date__gte=first_day).annotate(entries_count=Count("invoice__hourentry")).annotate(sum_of_hours=Sum("invoice__hourentry__incurred_hours")).annotate(sum_of_money=Sum("invoice__hourentry__incurred_money")).prefetch_related("admin_users").select_related("client_m"):
        message = f"""You are marked as a responsible person for {project.client_m.name} - {project.name}. You need to approve hours for the project weekly."""
        fallback_message = f"""You are marked as a responsible person for {project.client_m.name} - {project.name}. You need to approve hours for the project weekly. Go to https://app.10000ft.com to do so."""

        attachment = {
            "author_name": "Solinor Finance",
            "author_link": f"https://{settings.DOMAIN}",
            "fallback": fallback_message,
            "title": f"Unapproved project hours: {project.client_m.name} - {project.name}",
            "title_link": "https://app.10000ft.com",
            "text": message,
            "fields": [
                {"title": "Value", "value": f"{project.sum_of_money:.2f}€", "short": True},
                {"title": "Number of entries", "value": f"{project.entries_count}", "short": True},
                {"title": "Amount of hours", "value": f"{project.sum_of_hours:.2f}h", "short": True},
            ],
            "actions": [
                {
                    "type": "button",
                    "text": "See project in 10000ft",
                    "url": f"https://app.10000ft.com/viewproject?id={project.project_id}"
                },
                {
                    "type": "button",
                    "text": "Details in Solinor Finance",
                    "url": "https://{}{}".format(settings.DOMAIN, reverse("project", args=(project.guid,)))
                },
            ],
            "footer": "This notification is sent weekly if your project have unapproved hours.",
        }

        members_list = set([member.slack_id for member in project.admin_users.all() if member.slack_id])
        if len(members_list) > 1:
            chat_id = create_slack_mpim(members_list)
            if not chat_id:
                logger.warning("No chat_id for %s - %s", project, members_list)
                continue
            logger.info("%s %s", message, chat_id)
            notification_count += 1
            slack.chat.post_message(chat_id, attachments=[attachment], as_user="finance-bot")
        elif members_list:
            # members_list is never empty
            notification_count += 1
            slack.chat.post_message(list(members_list)[0], attachments=[attachment], as_user="finance-bot")
        else:
            logger.warning("Unapproved hours in %s, but no admin users specified.", project.name)
            for admin in settings.SLACK_NOTIFICATIONS_ADMIN:
                slack.chat.post_message(admin, text=f"Unapproved hours in {project.name} (id: {project.project_id}), but no admin users specified.", attachments=[attachment], as_user="finance-bot")
            continue

        for admin in settings.SLACK_NOTIFICATIONS_ADMIN:
            if admin not in members_list:
                slack.chat.post_message(admin, text="This was sent to {} in slack:".format(", ".join(project.admin_users.all().values_list("display_name", flat=True))), attachments=[attachment], as_user="finance-bot")

    SlackNotificationBundle(notification_type="unapproved").save()
    Event(event_type="send_unapproved_hours_notifications", succeeded=True, message=f"Sent {notification_count} notifications").save()


def send_new_project_to_slack(project):
    message = f"<!channel> Hi! New project was added: <https://app.10000ft.com/viewproject?id={project.project_id}|{project.client_m.name} - {project.name}> (created at {project.created_at})"
    for channel in SlackChannel.objects.filter(new_project_notification=True):
        slack.chat.post_message(channel.channel_id, message)
