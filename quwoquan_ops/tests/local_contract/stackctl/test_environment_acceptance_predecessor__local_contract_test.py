"""Retired standalone EnvironmentAcceptanceFact predecessor API."""

from __future__ import annotations

from pathlib import Path


def test_standalone_predecessor_modules_are_deleted() -> None:
    root = Path(__file__).resolve().parents[4]
    assert not (
        root / "quwoquan_ops/cli/commands/environment_acceptance_predecessor.py"
    ).exists()
    assert not (
        root / "quwoquan_ops/cli/lib/environment_acceptance_fact_predecessor.py"
    ).exists()
