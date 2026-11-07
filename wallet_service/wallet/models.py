import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q

# Bound each wallet and transfer to keep all persisted values within signed bigint.
MAX_MINOR = 10**12


class Account(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    opening_balance = models.BigIntegerField(default=0)
    balance = models.BigIntegerField(default=0)
    currency = models.CharField(max_length=3, default="GBP")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(balance__gte=0, balance__lte=MAX_MINOR), name="wallet_balance_bounds"
            ),
            models.CheckConstraint(
                condition=Q(opening_balance__gte=0, opening_balance__lte=MAX_MINOR),
                name="wallet_opening_bounds",
            ),
            models.CheckConstraint(condition=Q(currency="GBP"), name="wallet_gbp_only"),
        ]


class Transfer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    source = models.ForeignKey(Account, related_name="outgoing", on_delete=models.PROTECT)
    destination = models.ForeignKey(Account, related_name="incoming", on_delete=models.PROTECT)
    amount = models.BigIntegerField()
    status = models.CharField(
        max_length=16, choices=[("completed", "Completed"), ("rejected", "Rejected")]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0, amount__lte=MAX_MINOR), name="transfer_amount_bounds"
            ),
            models.CheckConstraint(
                condition=~Q(source=F("destination")), name="transfer_distinct_accounts"
            ),
            models.CheckConstraint(
                condition=Q(status__in=["completed", "rejected"]), name="transfer_final_status"
            ),
        ]


class IdempotencyRecord(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    key = models.CharField(max_length=128)
    request = models.JSONField()
    response = models.JSONField(default=dict)
    response_status = models.PositiveSmallIntegerField(default=201)
    transfer = models.OneToOneField(Transfer, null=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "key"], name="wallet_user_key_unique")
        ]


class LedgerEntry(models.Model):
    transfer = models.ForeignKey(Transfer, related_name="entries", on_delete=models.PROTECT)
    account = models.ForeignKey(Account, related_name="entries", on_delete=models.PROTECT)
    amount = models.BigIntegerField()  # signed minor units

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["transfer", "account"], name="ledger_transfer_account_unique"
            ),
            models.CheckConstraint(condition=~Q(amount=0), name="ledger_nonzero"),
        ]
