from django.core.management.base import BaseCommand, CommandError

from invoices.syncing.slack import sync_slack_channels, sync_slack_users
from invoices.syncing.tenkfeet import sync_10000ft_projects, sync_10000ft_users


class Command(BaseCommand):
    help = 'Sync data from upstream. Usage: <system> <type>.'

    SYNC_COMMANDS = {
        "10000ft": {
            "users": sync_10000ft_users,
            "projects": sync_10000ft_projects,
        },
        "slack": {
            "users": sync_slack_users,
            "channels": sync_slack_channels
        }
    }

    def add_arguments(self, parser):
        parser.add_argument('event_details', nargs='+', type=str)
        parser.add_argument(
            "--force",
            action="store_true",
            dest="force",
            help="Force update, instead of skipping if update was recently executed",
        )

    def handle(self, *args, **options):
        if len(options["event_details"]) != 2:
            raise CommandError("Missing mandatory argument(s). Usage: <system> <type> [--force]")

        system_name = options["event_details"][0]
        event_type = options["event_details"][1]

        sync_method = self.SYNC_COMMANDS.get(system_name, {}).get(event_type)
        if not sync_method:
            raise CommandError("Invalid system or event type.")

        force = options.get("force", False) or False

        sync_method(force=force)
        self.stdout.write(self.style.SUCCESS(f"Successfully synced {event_type} from {system_name}"))
