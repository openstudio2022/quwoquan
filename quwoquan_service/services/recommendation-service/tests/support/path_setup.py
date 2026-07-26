"""Canonical source-path setup for recommendation-service tests."""
from __future__ import annotations

from pathlib import Path


def recommendation_service_root() -> Path:
    return Path(__file__).resolve().parents[2]


def model_runtime_root() -> Path:
    return (
        recommendation_service_root()
        / "internal"
        / "recommendation"
        / "recommendation_model_release"
        / "infrastructure"
        / "model_runtime"
    )
