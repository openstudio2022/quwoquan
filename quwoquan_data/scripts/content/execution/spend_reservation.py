"""Cursor SDK 调用前的原子 USD 预留与结算。"""
from __future__ import annotations

import fcntl
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Mapping

from core.io import read_json, write_json
from core.paths import DATA_LOCAL_ROOT
from core.runtime_policy import RuntimePolicy, active_runtime_policy
from core.schema import assert_valid


SPEND_ROOT = DATA_LOCAL_ROOT / "cache" / "cursor_spend"
SPEND_LEDGER_PATH = SPEND_ROOT / "cursor_sdk_spend.json"
SPEND_LOCK_PATH = SPEND_ROOT / ".cursor_sdk_spend.lock"


class SpendBudgetExceeded(RuntimeError):
    """Raised before dispatch when an object, batch or daily cap would be exceeded."""


@dataclass(frozen=True, slots=True)
class SpendReservation:
    reservation_id: str
    execution_id: str
    reserved_usd: float
    date: str


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


@contextmanager
def _ledger_lock() -> Iterator[None]:
    SPEND_ROOT.mkdir(parents=True, exist_ok=True)
    with SPEND_LOCK_PATH.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _ledger() -> dict[str, object]:
    if not SPEND_LEDGER_PATH.is_file():
        return {
            "schema": "quwoquan.cursor_spend_reservations",
            "days": {},
        }
    payload = read_json(SPEND_LEDGER_PATH)
    if payload.get("schema") != "quwoquan.cursor_spend_reservations":
        raise ValueError("Cursor spend reservation ledger schema is invalid")
    if not isinstance(payload.get("days"), Mapping):
        raise ValueError("Cursor spend reservation ledger days must be an object")
    assert_valid(
        payload,
        "execution",
        "cursor_spend_reservations",
        label=SPEND_LEDGER_PATH.as_posix(),
    )
    return dict(payload)


def _write_ledger(payload: Mapping[str, object]) -> None:
    document = dict(payload)
    assert_valid(
        document,
        "execution",
        "cursor_spend_reservations",
        label=SPEND_LEDGER_PATH.as_posix(),
    )
    write_json(SPEND_LEDGER_PATH, document)


def _totals(execution: Mapping[str, object]) -> tuple[float, float]:
    reservations = execution.get("reservations")
    if not isinstance(reservations, Mapping):
        return 0.0, 0.0
    reserved = 0.0
    spent = 0.0
    for value in reservations.values():
        if not isinstance(value, Mapping):
            continue
        reserved += float(value.get("reservedUsd") or 0.0)
        spent += float(value.get("settledUsd") or 0.0)
    return reserved, spent


def reserve_cursor_spend(
    *,
    execution_id: str,
    reservation_id: str,
    policy: RuntimePolicy | None = None,
) -> SpendReservation:
    resolved = policy or active_runtime_policy()
    amount = float(resolved.default_object_cost_budget_usd)
    if amount <= 0:
        raise SpendBudgetExceeded("Cursor object spend cap is not approved")
    day_key = _today()
    with _ledger_lock():
        ledger = _ledger()
        days = dict(ledger["days"])  # type: ignore[arg-type]
        day = dict(days.get(day_key) or {})
        executions = dict(day.get("executions") or {})
        execution = dict(executions.get(execution_id) or {})
        reservations = dict(execution.get("reservations") or {})
        existing = reservations.get(reservation_id)
        if isinstance(existing, Mapping):
            return SpendReservation(
                reservation_id=reservation_id,
                execution_id=execution_id,
                reserved_usd=float(existing.get("reservedUsd") or 0.0),
                date=day_key,
            )
        batch_reserved, batch_spent = _totals(execution)
        daily_reserved = 0.0
        daily_spent = 0.0
        for value in executions.values():
            if isinstance(value, Mapping):
                reserved, spent = _totals(value)
                daily_reserved += reserved
                daily_spent += spent
        if batch_reserved + batch_spent + amount > resolved.max_batch_cost_usd:
            raise SpendBudgetExceeded("Cursor batch spend cap would be exceeded")
        if daily_reserved + daily_spent + amount > resolved.max_daily_cost_usd:
            raise SpendBudgetExceeded("Cursor daily spend cap would be exceeded")
        reservations[reservation_id] = {
            "reservedUsd": amount,
            "settledUsd": 0.0,
            "status": "reserved",
            "costIssue": None,
        }
        execution.update(
            {
                "batchCapUsd": resolved.max_batch_cost_usd,
                "reservations": reservations,
            }
        )
        executions[execution_id] = execution
        day.update(
            {
                "dailyCapUsd": resolved.max_daily_cost_usd,
                "executions": executions,
            }
        )
        days[day_key] = day
        ledger["days"] = days
        _write_ledger(ledger)
    return SpendReservation(
        reservation_id=reservation_id,
        execution_id=execution_id,
        reserved_usd=amount,
        date=day_key,
    )


def settle_cursor_spend(
    reservation: SpendReservation,
    *,
    actual_cost_usd: float | None,
    cost_issue: str = "",
) -> None:
    with _ledger_lock():
        ledger = _ledger()
        days = dict(ledger["days"])  # type: ignore[arg-type]
        day = dict(days.get(reservation.date) or {})
        executions = dict(day.get("executions") or {})
        execution = dict(executions.get(reservation.execution_id) or {})
        reservations = dict(execution.get("reservations") or {})
        row = dict(reservations.get(reservation.reservation_id) or {})
        if not row:
            raise ValueError("Cursor spend reservation is missing")
        if row.get("status") != "reserved":
            return
        if actual_cost_usd is None:
            row.update(
                {
                    "status": "cost_unknown",
                    "costIssue": cost_issue or "GATE_BLOCK_COST_UNKNOWN",
                }
            )
        else:
            actual = float(actual_cost_usd)
            if actual < 0:
                raise ValueError("Cursor settled cost must not be negative")
            row.update(
                {
                    "reservedUsd": 0.0,
                    "settledUsd": actual,
                    "status": (
                        "settled"
                        if actual <= reservation.reserved_usd
                        else "settled_over_budget"
                    ),
                    "costIssue": (
                        None
                        if actual <= reservation.reserved_usd
                        else "GATE_BLOCK_BUDGET_EXCEEDED"
                    ),
                }
            )
        reservations[reservation.reservation_id] = row
        execution["reservations"] = reservations
        executions[reservation.execution_id] = execution
        day["executions"] = executions
        days[reservation.date] = day
        ledger["days"] = days
        _write_ledger(ledger)


__all__ = [
    "SpendBudgetExceeded",
    "SpendReservation",
    "reserve_cursor_spend",
    "settle_cursor_spend",
]
