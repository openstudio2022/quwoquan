"""On-demand Provider discovery derived from requested capability owners."""

from __future__ import annotations

import importlib
from typing import Any

from .model import AcceptanceDataProvider, TestDataContext


def load_provider(
    owner_service: str,
    context: TestDataContext,
) -> AcceptanceDataProvider:
    overrides = getattr(context.runtime, "provider_overrides", {})
    if owner_service in overrides:
        return overrides[owner_service]
    if not owner_service or not owner_service.replace("_", "").isalnum():
        raise ValueError("Provider owner module identity is invalid")
    module = importlib.import_module(
        f"quwoquan_ops.cli.lib.test_data.providers.{owner_service}"
    )
    builder: Any = getattr(module, "build_provider", None)
    if not callable(builder):
        raise RuntimeError(f"Provider module has no build_provider: {owner_service}")
    return builder()
