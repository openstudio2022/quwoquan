"""Resolve one explicit, runtime-policy-owned semantic preflight selection."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from core.control_types import AgentProvider, RuntimeEnvironment
from core.cursor_model import CursorModelSelection
from core.runtime_policy import (
    RuntimePolicy,
    active_runtime_policy,
    runtime_profile_digest,
)

DEFAULT_SEMANTIC_SELECTION_ID = "default"
CALIBRATION_SEMANTIC_SELECTION_ID = "sol_calibration"


def semantic_selection_document_digest(document: dict[str, object]) -> str:
    body = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


@dataclass(frozen=True, slots=True)
class SemanticPreflightSelection:
    """Exact provider/model/runtime tuple selected before any probe is invoked."""

    selection_id: str
    provider: AgentProvider
    model_selection: CursorModelSelection
    runtime: RuntimeEnvironment
    runtime_profile_id: str
    runtime_profile_digest: str
    requires_new_retry_of: bool

    @property
    def selection_digest(self) -> str:
        return semantic_selection_document_digest(self.document())

    def document(self) -> dict[str, object]:
        return {
            "semanticSelectionId": self.selection_id,
            "provider": self.provider.value,
            "model": self.model_selection.model_id,
            "modelParameters": self.model_selection.parameters_document(),
            "semanticRuntime": self.runtime.value,
            "runtimeProfileId": self.runtime_profile_id,
            "runtimeProfileDigest": self.runtime_profile_digest,
            "requiresNewRetryOf": self.requires_new_retry_of,
        }


def bind_semantic_preflight_selection(
    report: dict[str, object],
    selection: SemanticPreflightSelection,
) -> dict[str, object]:
    """Attach resolved identity and reject any provider/model/profile drift."""

    expected = selection.document()
    for key in (
        "semanticSelectionId",
        "provider",
        "model",
        "modelParameters",
        "semanticRuntime",
        "runtimeProfileId",
        "runtimeProfileDigest",
        "requiresNewRetryOf",
    ):
        if key in report and report[key] != expected[key]:
            raise ValueError(f"semantic preflight {key} drifted from runtime policy")
    if "selectionDigest" in report and report["selectionDigest"] != selection.selection_digest:
        raise ValueError("semantic preflight selectionDigest drifted from runtime policy")
    if "fallbackPolicy" in report and report["fallbackPolicy"] != "forbidden":
        raise ValueError("semantic preflight fallbackPolicy must be forbidden")
    report.update(expected)
    report["selectionDigest"] = selection.selection_digest
    report["fallbackPolicy"] = "forbidden"
    return report


def resolve_semantic_preflight_selection(
    selection_id: object,
    *,
    policy: RuntimePolicy | None = None,
) -> SemanticPreflightSelection:
    """Resolve ``default`` or a governed explicit selection; never fall back."""

    effective_policy = policy or active_runtime_policy()
    normalized = str(selection_id or DEFAULT_SEMANTIC_SELECTION_ID).strip()
    if normalized == DEFAULT_SEMANTIC_SELECTION_ID:
        provider = effective_policy.semantic_author.provider
        model_selection = effective_policy.semantic_author.selection
        runtime = effective_policy.semantic_agent_runtime
        requires_new_retry_of = False
    elif normalized == CALIBRATION_SEMANTIC_SELECTION_ID:
        provider = effective_policy.semantic_calibration.binding.provider
        model_selection = effective_policy.semantic_calibration.binding.selection
        runtime = effective_policy.semantic_agent_runtime
        requires_new_retry_of = False
    else:
        explicit = effective_policy.explicit_semantic_selection(normalized)
        provider = explicit.binding.provider
        model_selection = explicit.binding.selection
        runtime = explicit.runtime
        requires_new_retry_of = explicit.requires_new_retry_of
    if effective_policy.semantic_fallback_policy != "forbidden":
        raise ValueError("semantic preflight requires fallbackPolicy=forbidden")
    return SemanticPreflightSelection(
        selection_id=normalized,
        provider=provider,
        model_selection=model_selection,
        runtime=runtime,
        runtime_profile_id=effective_policy.profile_id,
        runtime_profile_digest=runtime_profile_digest(effective_policy.profile_id),
        requires_new_retry_of=requires_new_retry_of,
    )


__all__ = [
    "CALIBRATION_SEMANTIC_SELECTION_ID",
    "DEFAULT_SEMANTIC_SELECTION_ID",
    "SemanticPreflightSelection",
    "bind_semantic_preflight_selection",
    "resolve_semantic_preflight_selection",
    "semantic_selection_document_digest",
]
