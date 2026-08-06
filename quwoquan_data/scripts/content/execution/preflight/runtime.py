"""Prepare and verify the exact provider-specific disposable runtime."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.python_environment import (
    agent_requirements_path,
    agent_runtime_modules,
    prepare_data_runtime_cache,
    python_has_modules,
)

from content.execution.preflight.selection import SemanticPreflightSelection


def prepare_selected_runtime(
    selection: SemanticPreflightSelection,
    *,
    prepare: Callable[..., dict[str, Any]] = prepare_data_runtime_cache,
) -> dict:
    report = prepare(
        requirements=agent_requirements_path(selection.provider)
    )
    python = Path(str(report.get("python") or "")).expanduser()
    modules = agent_runtime_modules(selection.provider)
    provider_ready, provider_missing = (
        python_has_modules(python, modules)
        if python.is_file()
        else (False, ["prepared Python is missing"])
    )
    report["semanticSelectionId"] = selection.selection_id
    report["provider"] = selection.provider.value
    report["requirements"] = str(agent_requirements_path(selection.provider))
    report["agentModules"] = list(modules)
    report["providerModulesReady"] = provider_ready
    report["missing"] = list(
        dict.fromkeys(
            [*(str(item) for item in report.get("missing") or []), *provider_missing]
        )
    )
    report["ready"] = bool(report.get("ready")) and provider_ready
    return report


__all__ = ["prepare_selected_runtime"]
