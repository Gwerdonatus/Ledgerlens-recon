import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TransactionTestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import MAX_MINOR, Account, IdempotencyRecord, LedgerEntry, Transfer
from .reconciliation import reconcile
from .services import make_transfer


class WalletTests(TransactionTestCase):
    def setUp(self):
        self.alice = get_user_model().objects.create_user(username="alice")
        self.bob = get_user_model().objects.create_user(username="bob")
        self.stranger = get_user_model().objects.create_user(username="stranger")
        self.source = Account.objects.create(owner=self.alice, opening_balance=10000, balance=10000)
        self.dest = Account.objects.create(owner=self.bob)
        self.token = Token.objects.create(user=self.alice).key
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")
        self.payload = {
            "source": str(self.source.pk),
            "destination": str(self.dest.pk),
            "amount": 8000,
        }

    def post(self, key="one", payload=None, client=None):
        return (client or self.client).post(
            "/transfers", payload or self.payload, format="json", HTTP_IDEMPOTENCY_KEY=key
        )

    def balances(self):
        self.source.refresh_from_db()
        self.dest.refresh_from_db()
        return self.source.balance, self.dest.balance

    def concurrent_posts(self, keys):
        barrier = Barrier(len(keys))

        def run(key):
            close_old_connections()
            try:
                client = APIClient()
                client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")
                barrier.wait(timeout=10)
                response = self.post(key, client=client)
                return response.status_code, response.json()
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=len(keys)) as pool:
            return list(pool.map(run, keys))

    def test_success_and_ten_retries_return_original_response(self):
        first = self.post()
        self.assertEqual(first.status_code, 201)
        for _ in range(10):
            retry = self.post()
            self.assertEqual((retry.status_code, retry.json()), (201, first.json()))
        self.assertEqual(self.balances(), (2000, 8000))
        self.assertEqual(Transfer.objects.count(), 1)
        self.assertEqual(LedgerEntry.objects.count(), 2)
        self.assertEqual(reconcile(), [])

    def test_simultaneous_same_key_moves_money_once(self):
        results = self.concurrent_posts(["same"] * 5)
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(results[0][0], 201)
        self.assertEqual(self.balances(), (2000, 8000))
        self.assertEqual(Transfer.objects.count(), 1)

    def test_concurrent_overspending_then_ten_retries(self):
        results = self.concurrent_posts(["first", "second"])
        self.assertEqual(sorted(code for code, _ in results), [201, 409])
        self.assertEqual(self.balances(), (2000, 8000))
        winner = "first" if results[0][0] == 201 else "second"
        for _ in range(10):
            self.assertEqual(self.post(winner).status_code, 201)
        self.assertEqual(self.balances(), (2000, 8000))
        self.assertEqual(LedgerEntry.objects.count(), 2)
        self.assertEqual(reconcile(), [])

    def test_failure_after_debit_rolls_everything_back_then_retry_succeeds(self):
        original = Account.save

        def fail_credit(account, *args, **kwargs):
            if account.pk == self.dest.pk:
                raise RuntimeError("Injected failure after debit")
            return original(account, *args, **kwargs)

        with patch.object(Account, "save", fail_credit), self.assertRaises(RuntimeError):
            self.post()
        self.assertEqual(self.balances(), (10000, 0))
        self.assertEqual(Transfer.objects.count(), 0)
        self.assertEqual(LedgerEntry.objects.count(), 0)
        self.assertEqual(IdempotencyRecord.objects.count(), 0)
        self.assertEqual(self.post().status_code, 201)

    def test_failure_persisting_response_also_rolls_back(self):
        original = IdempotencyRecord.save

        def fail_result(record, *args, **kwargs):
            if not record._state.adding:
                raise RuntimeError("storage failure after ledger entries")
            return original(record, *args, **kwargs)

        with patch.object(IdempotencyRecord, "save", fail_result):
            with self.assertRaises(RuntimeError):
                make_transfer(
                    user=self.alice,
                    key="broken",
                    source=self.source.pk,
                    destination=self.dest.pk,
                    amount=8000,
                )
        self.assertEqual(self.balances(), (10000, 0))
        self.assertEqual(Transfer.objects.count(), 0)

    def test_conflicting_key_rejected(self):
        self.post()
        for change in [{"amount": 10}, {"destination": str(uuid.uuid4())}]:
            self.assertEqual(self.post(payload={**self.payload, **change}).status_code, 409)
        self.assertEqual(self.balances(), (2000, 8000))

    def test_rejected_request_remains_rejected_after_funding(self):
        payload = {**self.payload, "amount": 20000}
        first = self.post(payload=payload)
        self.assertEqual(first.status_code, 409)
        Account.objects.filter(pk=self.source.pk).update(balance=30000, opening_balance=30000)
        self.assertEqual(self.post(payload=payload).json(), first.json())
        self.assertEqual(self.balances(), (30000, 0))

    def test_key_is_scoped_to_authenticated_user(self):
        self.post()
        client = APIClient()
        client.force_authenticate(self.bob)
        reverse = {"source": str(self.dest.pk), "destination": str(self.source.pk), "amount": 1000}
        self.assertEqual(self.post(payload=reverse, client=client).status_code, 201)
        self.assertEqual(self.balances(), (3000, 7000))

    def test_ownership_and_unauthenticated_access(self):
        result = self.post().json()
        client = APIClient()
        self.assertEqual(self.post(client=client).status_code, 401)
        client.force_authenticate(self.stranger)
        self.assertEqual(self.post(client=client).status_code, 404)
        self.assertEqual(client.get(f'/transfers/{result["id"]}').status_code, 404)
        self.assertEqual(client.get(f"/accounts/{self.source.pk}/transfers").status_code, 404)
        self.assertEqual(client.get("/accounts").json()["results"], [])
        client.force_authenticate(self.bob)
        self.assertEqual(client.get(f'/transfers/{result["id"]}').status_code, 200)
        self.assertEqual(client.get(f"/accounts/{self.dest.pk}/transfers").json()["count"], 1)

    def test_invalid_inputs(self):
        for amount in [0, -1, 1.5, 1.0, True, "100", MAX_MINOR + 1, None]:
            self.assertEqual(self.post(payload={**self.payload, "amount": amount}).status_code, 400)
        self.assertEqual(
            self.post(payload={**self.payload, "destination": str(self.source.pk)}).status_code, 400
        )
        self.assertEqual(self.post(payload={**self.payload, "destination": "bad"}).status_code, 400)
        self.assertEqual(
            self.post(payload={**self.payload, "destination": str(uuid.uuid4())}).status_code, 404
        )
        for key in ["", "x" * 129, "space key"]:
            self.assertEqual(self.post(key).status_code, 400)
        self.assertEqual(IdempotencyRecord.objects.count(), 0)

    def test_destination_limit(self):
        Account.objects.filter(pk=self.dest.pk).update(balance=MAX_MINOR, opening_balance=MAX_MINOR)
        self.assertEqual(self.post().json()["error"], "destination_balance_limit")
        self.assertEqual(self.balances(), (10000, MAX_MINOR))

    def test_database_rejects_negative_balance(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Account.objects.filter(pk=self.source.pk).update(balance=-1)

    def test_reconciliation_identifies_bad_pair_and_affected_transfer(self):
        response = self.post().json()
        # Simulate faulty historical importer (no API exists for altering entries).
        LedgerEntry.objects.filter(amount__gt=0).update(amount=7999)
        issues = reconcile()
        self.assertTrue(any(i.get("transfer_id") == response["id"] for i in issues))
        balance_issue = next(i for i in issues if i["type"] == "account_balance")
        self.assertIn(response["id"], balance_issue["related_transfer_ids"])

    def test_opposing_transfers_do_not_deadlock(self):
        Account.objects.filter(pk=self.dest.pk).update(balance=10000, opening_balance=10000)
        barrier = Barrier(2)

        def run(user_id, source, destination):
            close_old_connections()
            try:
                user = get_user_model().objects.get(pk=user_id)
                barrier.wait(timeout=10)
                return make_transfer(
                    user=user, key="opposed", source=source, destination=destination, amount=1000
                )[1]
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(run, self.alice.pk, self.source.pk, self.dest.pk),
                pool.submit(run, self.bob.pk, self.dest.pk, self.source.pk),
            ]
            self.assertEqual([f.result(timeout=25) for f in futures], [201, 201])
        self.assertEqual(self.balances(), (10000, 10000))
        self.assertEqual(reconcile(), [])

    def test_unknown_fields_are_rejected(self):
        self.assertEqual(self.post(payload={**self.payload, "currency": "USD"}).status_code, 400)
        self.assertEqual(self.post(payload={**self.payload, "ammount": 100}).status_code, 400)
        self.assertEqual(self.balances(), (10000, 0))

    def test_seed_rerun_preserves_spent_balance(self):
        import io
        import json

        from django.core.management import call_command

        output = io.StringIO()
        call_command("seed_wallet", stdout=output)
        alice = json.loads(output.getvalue())["wallet-alice"]
        account = Account.objects.get(pk=alice["account"])
        Account.objects.filter(pk=account.pk).update(balance=1234)
        call_command("seed_wallet", stdout=io.StringIO())
        account.refresh_from_db()
        self.assertEqual(account.balance, 1234)
        self.assertEqual(Token.objects.get(user=account.owner).key, alice["token"])

    def test_reconciliation_command_exits_nonzero_on_discrepancy(self):
        import io
        import json

        from django.core.management import CommandError, call_command

        output = io.StringIO()
        call_command("reconcile_wallet", stdout=output)
        self.assertEqual(json.loads(output.getvalue()), {"issues": []})
        self.post()
        LedgerEntry.objects.filter(amount__gt=0).update(amount=7999)
        with self.assertRaises(CommandError):
            call_command("reconcile_wallet", stdout=io.StringIO())

    def test_demo_command_leaves_inspectable_correct_records(self):
        import io
        import json

        from django.core.management import call_command

        output = io.StringIO()
        call_command("demo_wallet", stdout=output)
        result = json.loads(output.getvalue())
        self.assertEqual(result["successful_retries"], 10)
        self.assertEqual((result["source_balance"], result["destination_balance"]), (2000, 8000))
        self.assertEqual(result["reconciliation_issues"], [])
