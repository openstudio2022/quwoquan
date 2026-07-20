"""Cursor SDK job 必须先预留预算，结算后才释放余额。"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.execution import spend_reservation as spend  # noqa: E402


def _policy(*, object_cap: float = 5, batch_cap: float = 10, daily_cap: float = 15):
    return SimpleNamespace(
        default_object_cost_budget_usd=object_cap,
        max_batch_cost_usd=batch_cap,
        max_daily_cost_usd=daily_cap,
    )


def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "spend"
    monkeypatch.setattr(spend, "SPEND_ROOT", root)
    monkeypatch.setattr(spend, "SPEND_LEDGER_PATH", root / "ledger.json")
    monkeypatch.setattr(spend, "SPEND_LOCK_PATH", root / ".lock")
    monkeypatch.setattr(spend, "_today", lambda: "2026-07-19")


def test_reservation_is_idempotent_and_batch_cap_stops_new_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolated(monkeypatch, tmp_path)
    policy = _policy()
    first = spend.reserve_cursor_spend(
        execution_id="execution-a",
        reservation_id="run-1",
        policy=policy,  # type: ignore[arg-type]
    )
    duplicate = spend.reserve_cursor_spend(
        execution_id="execution-a",
        reservation_id="run-1",
        policy=policy,  # type: ignore[arg-type]
    )
    assert duplicate == first
    spend.reserve_cursor_spend(
        execution_id="execution-a",
        reservation_id="run-2",
        policy=policy,  # type: ignore[arg-type]
    )
    with pytest.raises(spend.SpendBudgetExceeded, match="batch"):
        spend.reserve_cursor_spend(
            execution_id="execution-a",
            reservation_id="run-3",
            policy=policy,  # type: ignore[arg-type]
        )


def test_settlement_releases_unused_reserve_but_unknown_cost_keeps_it_blocked(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolated(monkeypatch, tmp_path)
    policy = _policy(object_cap=4, batch_cap=5)
    reservation = spend.reserve_cursor_spend(
        execution_id="execution-a",
        reservation_id="run-1",
        policy=policy,  # type: ignore[arg-type]
    )
    spend.settle_cursor_spend(reservation, actual_cost_usd=1.0)
    replacement = spend.reserve_cursor_spend(
        execution_id="execution-a",
        reservation_id="run-2",
        policy=policy,  # type: ignore[arg-type]
    )
    spend.settle_cursor_spend(
        replacement,
        actual_cost_usd=None,
        cost_issue="GATE_BLOCK_COST_UNKNOWN",
    )
    with pytest.raises(spend.SpendBudgetExceeded, match="batch"):
        spend.reserve_cursor_spend(
            execution_id="execution-a",
            reservation_id="run-3",
            policy=policy,  # type: ignore[arg-type]
        )
