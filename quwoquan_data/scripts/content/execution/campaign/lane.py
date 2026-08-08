"""Shared identities and callback contracts for four-lane campaigns."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

CAMPAIGN_CARRIERS = ("homepage", "article", "image", "video")
LaneRunner = Callable[[list[str], Path, dict[str, str], Path, float], int]
PhaseResultCallback = Callable[[str, tuple[int, str | None]], None]
