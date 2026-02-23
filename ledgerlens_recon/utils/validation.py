from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional


@dataclass(frozen=True)
class ValidationError:
    field: str
    message: str


def ensure(condition: bool, field: str, message: str, errors: List[ValidationError]) -> None:
    if not condition:
        errors.append(ValidationError(field=field, message=message))


def raise_if_errors(errors: Iterable[ValidationError]) -> None:
    errors = list(errors)
    if not errors:
        return
    details = "; ".join(f"{e.field}: {e.message}" for e in errors)
    raise ValueError(details)
