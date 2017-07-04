
from django.core.management.base import BaseCommand
from invoices.models import AmazonLinkedAccount, FeetUser


class Command(BaseCommand):
    help = 'Link AWS accounts and 10kf users'

    def handle(self, *args, **options):
        for user in FeetUser.objects.all():
            accounts = AmazonLinkedAccount.objects.filter(name=u'%s %s' % (user.first_name, user.last_name))
            if len(accounts) == 1:
                user.amazon_account.add(accounts[0])
