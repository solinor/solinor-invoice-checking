from invoices.models import Event, SlackChannel, TenkfUser
from invoices.slack import slack


def sync_slack_users(force=False):  # pylint:disable=unused-argument
    slack_users = slack.users.list().body["members"]
    for member in slack_users:
        email = member.get("profile", {}).get("email")
        if not email:
            continue
        TenkfUser.objects.filter(email__iexact=email).update(slack_id=member.get("id"))
    Event(event_type="sync_slack_users", succeeded=True, message=f"Got {len(slack_users)} users from Slack").save()


def sync_slack_channels(force=False):  # pylint:disable=unused-argument
    slack_channels = slack.channels.list().body["channels"]
    for channel in slack_channels:
        channel_id = channel.get("id")
        channel_name = channel.get("name")
        SlackChannel.objects.update_or_create(channel_id=channel_id, defaults={
            "name": channel_name,
            "archived": channel.get("is_archived", False),
        })
    Event(event_type="sync_slack_channels", succeeded=True, message="Got {} channels from Slack".format(len(slack_channels))).save()
