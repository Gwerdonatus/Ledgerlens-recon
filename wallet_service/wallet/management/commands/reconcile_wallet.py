import json

from django.core.management.base import BaseCommand, CommandError

from ...reconciliation import reconcile


class Command(BaseCommand):
    help = "Check wallet balances and debit/credit pairs using one database snapshot."

    def handle(self, *args, **options):
        issues = reconcile()
        self.stdout.write(json.dumps({"issues": issues}, indent=2))
        if issues:
            raise CommandError(f"Found {len(issues)} wallet discrepancies.")
