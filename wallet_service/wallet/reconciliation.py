from django.db import connection, transaction

from .models import Account, LedgerEntry, Transfer


def reconcile():
    """Read a single committed snapshot so active transfers cannot cause false alarms."""
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        issues = []
        entries = list(LedgerEntry.objects.all())
        by_transfer, by_account = {}, {}
        for entry in entries:
            by_transfer.setdefault(entry.transfer_id, []).append((entry.account_id, entry.amount))
            by_account[entry.account_id] = by_account.get(entry.account_id, 0) + entry.amount
        for transfer in Transfer.objects.all():
            expected = (
                []
                if transfer.status == "rejected"
                else [
                    (transfer.source_id, -transfer.amount),
                    (transfer.destination_id, transfer.amount),
                ]
            )
            actual = by_transfer.get(transfer.pk, [])
            if sorted(actual) != sorted(expected):
                issues.append({"type": "transfer_entries", "transfer_id": str(transfer.pk)})
            if transfer.requested_by_id != transfer.source.owner_id:
                issues.append({"type": "transfer_owner", "transfer_id": str(transfer.pk)})
        for account in Account.objects.all():
            expected = account.opening_balance + by_account.get(account.pk, 0)
            if account.balance != expected:
                affected = sorted(
                    {str(e.transfer_id) for e in entries if e.account_id == account.pk}
                )
                issues.append(
                    {
                        "type": "account_balance",
                        "account_id": str(account.pk),
                        "expected": expected,
                        "actual": account.balance,
                        "related_transfer_ids": affected,
                    }
                )
        return issues
