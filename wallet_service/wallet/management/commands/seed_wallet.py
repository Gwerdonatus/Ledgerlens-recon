import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from rest_framework.authtoken.models import Token

from ...models import Account


class Command(BaseCommand):
    help = "Seed fictional Alice (£100) and Bob (£0); reruns never reset balances."

    @transaction.atomic
    def handle(self, *args, **options):
        result = {}
        for name, amount, account_id in [
            ("wallet-alice", 10000, "00000000-0000-0000-0000-000000000001"),
            ("wallet-bob", 0, "00000000-0000-0000-0000-000000000002"),
        ]:
            user, created = get_user_model().objects.get_or_create(username=name)
            if created:
                user.set_unusable_password()
                user.save()
            account, _ = Account.objects.get_or_create(
                pk=account_id,
                defaults={"owner": user, "opening_balance": amount, "balance": amount},
            )
            token, _ = Token.objects.get_or_create(user=user)
            result[name] = {
                "account": str(account.pk),
                "token": token.key,
                "balance": account.balance,
            }
        self.stdout.write(json.dumps(result, indent=2))
