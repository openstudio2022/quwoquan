"""Retired EnvironmentAcceptanceFact release-order projection API."""

from __future__ import annotations

from pathlib import Path


def test_release_order_projection_is_deleted_in_favor_of_scheduler_state() -> None:
    root = Path(__file__).resolve().parents[4]
    assert not (
        root / "quwoquan_ops/cli/lib/environment_release_order_view.py"
    ).exists()
