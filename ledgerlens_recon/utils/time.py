from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def parse_iso8601(ts: str) -> datetime:
    # Supports 'Z' and offset-aware ISO strings
    s = ts.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def seconds_between(a: datetime, b: datetime) -> float:
    return abs((a - b).total_seconds())


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
