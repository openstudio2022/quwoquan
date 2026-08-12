"""Frozen semantic execution selection projected from one governed profile."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.runtime_policy import (
    apply_runtime_policy,
    load_runtime_policy,
    runtime_profile_digest,
)

from content.execution.agent.agent_conflicts import assert_managed_workspace_available
from content.execution.model_contract import (
    DEFAULT_SEMANTIC_SELECTION_ID,
    SemanticExecutionBinding,
    normalize_semantic_selection_id,
    semantic_execution_binding,
)


def resolve_frozen_semantic_selection(
    recipe: Mapping[str, Any],
    *,
    existing_manifest: Mapping[str, Any] | None,
    requested_selection_id: object,
    retry_of: str | None,
) -> SemanticExecutionBinding:
    requested = (
        normalize_semantic_selection_id(requested_selection_id)
        if requested_selection_id not in (None, "")
        else None
    )
    if existing_manifest is not None:
        frozen = normalize_semantic_selection_id(
            existing_manifest.get("semanticSelectionId")
        )
        if requested is not None and requested != frozen:
            raise ValueError(
                "resume may not change semanticSelectionId; create retryOf"
            )
        selection_id = frozen
    else:
        selection_id = requested or DEFAULT_SEMANTIC_SELECTION_ID
    binding = semantic_execution_binding(recipe, selection_id)
    if existing_manifest is None and binding.requires_new_retry_of:
        from content.execution.planning.semantic_failover_admission import (
            require_cursor_auto_retry_admission,
        )

        require_cursor_auto_retry_admission(retry_of)
    return binding


def activate_frozen_semantic_selection(
    recipe: Mapping[str, Any],
    binding: SemanticExecutionBinding,
    *,
    workspace: Path,
    execution_id: str,
) -> None:
    """Project a frozen selection to process inputs; environment is never truth."""
    profile = str(recipe.get("runtimeProfile") or "").strip()
    if not profile:
        raise ValueError("recipe.runtimeProfile is required")
    policy = load_runtime_policy(profile)
    apply_runtime_policy(policy)
    os.environ.update(
        {
            "QWQ_SEMANTIC_AGENT_PROVIDER": binding.pair.author.provider.value,
            "QWQ_SEMANTIC_AGENT_MODEL": binding.pair.author.model_id,
            "QWQ_SEMANTIC_REVIEWER_PROVIDER": binding.pair.reviewer.provider.value,
            "QWQ_SEMANTIC_REVIEWER_MODEL": binding.pair.reviewer.model_id,
        }
    )
    assert_managed_workspace_available(
        workspace,
        provider=binding.pair.author.provider.value,
        execution_id=execution_id,
    )


def semantic_manifest_identity(
    recipe: Mapping[str, Any],
    *,
    semantic_selection_id: object,
    retry_of: str | None,
) -> dict[str, object]:
    profile = str(recipe.get("runtimeProfile") or "").strip()
    if not profile:
        raise ValueError("recipe runtimeProfile is missing")
    binding = resolve_frozen_semantic_selection(
        recipe,
        existing_manifest=None,
        requested_selection_id=semantic_selection_id,
        retry_of=retry_of,
    )
    author = binding.pair.author
    reviewer = binding.pair.reviewer
    if author.provider is not reviewer.provider:
        raise ValueError("execution manifest supports one provider for both roles")
    return {
        "modelBinding": {
            "provider": author.provider.value,
            "authorModel": author.model_id,
            "authorModelFamily": author.family.value,
            "authorModelParameters": author.selection.parameters_document(),
            "reviewerModel": reviewer.model_id,
            "reviewerModelFamily": reviewer.family.value,
            "reviewerModelParameters": reviewer.selection.parameters_document(),
        },
        "runtimeProfileId": profile,
        "runtimeProfileDigest": runtime_profile_digest(profile),
        "semanticSelectionId": binding.selection_id,
        "semanticRuntime": binding.runtime.value,
    }


__all__ = [
    "activate_frozen_semantic_selection",
    "resolve_frozen_semantic_selection",
    "semantic_manifest_identity",
]
