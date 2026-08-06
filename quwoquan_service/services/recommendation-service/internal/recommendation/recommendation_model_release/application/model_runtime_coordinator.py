from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


class RecommendationModelRuntimeCoordinator:
    """Applies canonical release events to the in-process scoring runtime."""

    _STATUS_BY_EVENT = {
        "RecommendationModelReleaseStaged": "staged",
        "RecommendationModelReleaseActivated": "active",
        "RecommendationModelReleaseRetired": "retired",
    }

    def __init__(self, reload_runtime: Callable[[], None]) -> None:
        if not callable(reload_runtime):
            raise ValueError("model runtime reload callback is required")
        self._reload_runtime = reload_runtime

    def apply_release_event(
        self,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> None:
        expected_status = self._STATUS_BY_EVENT.get(event_type.strip())
        if expected_status is None:
            raise ValueError("unsupported recommendation model release event")
        if not str(payload.get("id") or "").strip():
            raise ValueError("recommendation model release id is required")
        if str(payload.get("status") or "").strip() != expected_status:
            raise ValueError("recommendation model release status does not match event")
        if event_type in {
            "RecommendationModelReleaseActivated",
            "RecommendationModelReleaseRetired",
        }:
            self._reload_runtime()


__all__ = ["RecommendationModelRuntimeCoordinator"]
