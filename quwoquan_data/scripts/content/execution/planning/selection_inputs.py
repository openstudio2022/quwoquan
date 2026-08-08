"""Input parsing helpers for target selection."""
from __future__ import annotations

from pathlib import Path


def split_csv(value: str | None) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def default_discovery_path() -> Path:
    """Return the committed coverage master tree used for discovery."""
    from governance.coverage.master_list import COVERAGE_MASTER_ROOT

    return COVERAGE_MASTER_ROOT

