import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, connection

from ...models import Account
from ...reconciliation import reconcile
from ...services import make_transfer


class Command(BaseCommand):
    help = (
        "Create fresh fictional wallets, race two £80 transfers, then retry the winner ten times."
    )

    def handle(self, *args, **options):
        label = uuid.uuid4().hex[:12]
        alice = get_user_model().objects.create_user(username=f"demo-alice-{label}")
        bob = get_user_model().objects.create_user(username=f"demo-bob-{label}")
        source = Account.objects.create(owner=alice, opening_balance=10000, balance=10000)
        destination = Account.objects.create(owner=bob)
        barrier = Barrier(2)

        def send(key):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return key, make_transfer(
                    user=alice, key=key, source=source.pk, destination=destination.pk, amount=8000
                )
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(send, ["first", "second"]))
        if sorted(result[1][1] for result in results) != [201, 409]:
            raise CommandError("Expected exactly one successful withdrawal.")
        winner, original = next(result for result in results if result[1][1] == 201)
        for _ in range(10):
            retry = make_transfer(
                user=alice, key=winner, source=source.pk, destination=destination.pk, amount=8000
            )
            if retry != original:
                raise CommandError("Retry returned a different response.")
        source.refresh_from_db()
        destination.refresh_from_db()
        if (source.balance, destination.balance) != (2000, 8000):
            raise CommandError("Unexpected final balances.")
        issues = reconcile()
        self.stdout.write(
            json.dumps(
                {
                    "fictional": True,
                    "requests": [
                        {"key": key, "http_status": result[1], "result": result[0]}
                        for key, result in results
                    ],
                    "successful_retries": 10,
                    "source_balance": source.balance,
                    "destination_balance": destination.balance,
                    "reconciliation_issues": issues,
                },
                indent=2,
            )
        )
        if issues:
            raise CommandError("Reconciliation found discrepancies.")
