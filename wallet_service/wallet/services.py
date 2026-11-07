from django.db import transaction
from rest_framework.exceptions import APIException, NotFound

from .models import MAX_MINOR, Account, IdempotencyRecord, LedgerEntry, Transfer


class Conflict(APIException):
    status_code = 409
    default_detail = "This Idempotency-Key was already used for a different request."


def transfer_data(transfer):
    return {
        "id": str(transfer.id),
        "source": str(transfer.source_id),
        "destination": str(transfer.destination_id),
        "amount": transfer.amount,
        "currency": "GBP",
        "status": transfer.status,
        "created_at": transfer.created_at.isoformat(),
    }


@transaction.atomic
def make_transfer(*, user, key, source, destination, amount):
    payload = {"source": str(source), "destination": str(destination), "amount": amount}
    # The unique index waits for an in-flight request to commit or roll back.
    # Reserve before account locks; do not hold account locks while waiting for a key.
    record, created = IdempotencyRecord.objects.get_or_create(
        user=user, key=key, defaults={"request": payload}
    )
    if not created:
        if record.request != payload:
            raise Conflict()
        return record.response, record.response_status

    accounts = list(
        Account.objects.select_for_update().filter(pk__in=[source, destination]).order_by("pk")
    )
    by_id = {account.pk: account for account in accounts}
    if len(accounts) != 2 or by_id[source].owner_id != user.pk:
        raise NotFound("Account unavailable.")
    debit, credit = by_id[source], by_id[destination]
    error = None
    if debit.balance < amount:
        error = "insufficient_funds"
    elif credit.balance + amount > MAX_MINOR:
        error = "destination_balance_limit"
    transfer = Transfer.objects.create(
        requested_by=user,
        source=debit,
        destination=credit,
        amount=amount,
        status="rejected" if error else "completed",
    )
    if not error:
        debit.balance -= amount
        debit.save(update_fields=["balance"])
        # Any exception from here through response persistence rolls back the debit too.
        credit.balance += amount
        credit.save(update_fields=["balance"])
        LedgerEntry.objects.bulk_create(
            [
                LedgerEntry(transfer=transfer, account=debit, amount=-amount),
                LedgerEntry(transfer=transfer, account=credit, amount=amount),
            ]
        )
    result = transfer_data(transfer)
    if error:
        result["error"] = error
    record.transfer = transfer
    record.response = result
    record.response_status = 409 if error else 201
    record.save(update_fields=["transfer", "response", "response_status"])
    return result, record.response_status
