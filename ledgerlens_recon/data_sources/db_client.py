from __future__ import annotations

import csv
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import create_engine, text

from ..reconciliation.models import Transaction
from ..utils.time import parse_iso8601


@dataclass(frozen=True)
class DbQueryOptions:
    limit: int = 5000


class DbClient:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    def fetch_transactions(self, *, limit: int = 5000) -> List[Transaction]:
        """Fetch internal transactions via SQLAlchemy.

        Assumes a table named `payments` with columns:
        - transaction_id (text)
        - amount (numeric)
        - currency (text)
        - created_at (timestamp)
        """
        sql = text(
            """
            SELECT transaction_id, amount, currency, created_at
            FROM payments
            ORDER BY created_at DESC
            LIMIT :limit
            """
        )
        out: List[Transaction] = []
        with self.engine.begin() as conn:
            rows = conn.execute(sql, {"limit": limit}).fetchall()
            for r in rows:
                out.append(
                    Transaction(
                        transaction_id=str(r[0]),
                        amount=float(r[1]),
                        currency=str(r[2]).upper(),
                        created_at=r[3],
                        source="internal",
                    )
                )
        return out


def load_internal_from_csv(path: str) -> List[Transaction]:
    """Load internal transactions from CSV for local demo.

    Expected columns:
    transaction_id,amount,currency,created_at
    """
    out: List[Transaction] = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            out.append(
                Transaction(
                    transaction_id=str(row["transaction_id"]).strip(),
                    amount=float(row["amount"]),
                    currency=str(row["currency"]).upper().strip(),
                    created_at=parse_iso8601(str(row["created_at"])),
                    source="internal",
                )
            )
    return out
