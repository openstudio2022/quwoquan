"""Typed author/reviewer model contract for one content execution.

The recipe, rather than a model-id prefix heuristic, declares both model IDs
and provider families. Review independence is proven by the object-level
semantic-agent run identity and an exact provider/model binding.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from core.control_types import AgentProvider
from core.cursor_model import CursorModelParameter, CursorModelSelection
from core.control_types import RuntimeEnvironment
from core.runtime_policy import (
    active_runtime_policy,
    load_runtime_policy,
)


DEFAULT_SEMANTIC_SELECTION_ID = "default"
CURSOR_GROK_SEMANTIC_SELECTION_ID = "cursor_grok"
CURSOR_AUTO_SEMANTIC_SELECTION_ID = "cursor_auto"
SEMANTIC_SELECTION_IDS = (
    DEFAULT_SEMANTIC_SELECTION_ID,
    CURSOR_GROK_SEMANTIC_SELECTION_ID,
    CURSOR_AUTO_SEMANTIC_SELECTION_ID,
)


class ModelFamily(StrEnum):
    AUTO = "auto"
    CLAUDE = "claude"
    COMPOSER = "composer"
    GEMINI = "gemini"
    GPT = "gpt"
    GROK = "grok"


@dataclass(frozen=True, slots=True)
class ExecutionModel:
    provider: AgentProvider
    model_id: str
    family: ModelFamily
    parameters: tuple[CursorModelParameter, ...] = ()

    @property
    def selection(self) -> CursorModelSelection:
        return CursorModelSelection(
            model_id=self.model_id,
            parameters=self.parameters,
        )

    @classmethod
    def from_execution(
        cls,
        execution: Mapping[str, Any],
        *,
        role: str,
        provider: AgentProvider,
    ) -> "ExecutionModel":
        if role == "author":
            model_key, family_key, parameters_key = (
                "model",
                "modelFamily",
                "modelParameters",
            )
        elif role == "reviewer":
            model_key, family_key, parameters_key = (
                "reviewModel",
                "reviewModelFamily",
                "reviewModelParameters",
            )
        else:
            raise ValueError(f"unsupported execution model role: {role}")
        model_id = str(execution.get(model_key) or "").strip()
        family_text = str(execution.get(family_key) or "").strip()
        if not model_id:
            raise ValueError(f"execution.{model_key} is required")
        if not family_text:
            raise ValueError(f"execution.{family_key} is required")
        try:
            family = ModelFamily(family_text)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in ModelFamily)
            raise ValueError(
                f"execution.{family_key} must be one of: {allowed}"
            ) from exc
        selection = CursorModelSelection.from_config(
            model_id,
            execution.get(parameters_key),
            label=f"recipe.execution.{role}",
        )
        return cls(
            provider=provider,
            model_id=selection.model_id,
            family=family,
            parameters=selection.parameters,
        )


@dataclass(frozen=True, slots=True)
class ExecutionModelPair:
    author: ExecutionModel
    reviewer: ExecutionModel


@dataclass(frozen=True, slots=True)
class SemanticExecutionBinding:
    selection_id: str
    pair: ExecutionModelPair
    runtime: RuntimeEnvironment
    requires_new_retry_of: bool


def normalize_semantic_selection_id(value: object) -> str:
    selection_id = str(value or DEFAULT_SEMANTIC_SELECTION_ID).strip()
    if selection_id not in SEMANTIC_SELECTION_IDS:
        allowed = ", ".join(SEMANTIC_SELECTION_IDS)
        raise ValueError(f"semanticSelectionId must be one of: {allowed}")
    return selection_id


def semantic_execution_binding(
    recipe: Mapping[str, Any],
    semantic_selection_id: object = DEFAULT_SEMANTIC_SELECTION_ID,
) -> SemanticExecutionBinding:
    execution = recipe.get("execution")
    if not isinstance(execution, Mapping):
        raise ValueError("recipe.execution must be an object")
    runtime_profile = str(recipe.get("runtimeProfile") or "").strip()
    if not runtime_profile:
        raise ValueError("recipe.runtimeProfile must bind the semantic role policy")
    policy = load_runtime_policy(runtime_profile)
    selection_id = normalize_semantic_selection_id(semantic_selection_id)
    if selection_id == DEFAULT_SEMANTIC_SELECTION_ID:
        pair = ExecutionModelPair(
            author=ExecutionModel.from_execution(
                execution,
                role="author",
                provider=policy.semantic_author.provider,
            ),
            reviewer=ExecutionModel.from_execution(
                execution,
                role="reviewer",
                provider=policy.semantic_reviewer.provider,
            ),
        )
        if pair.author.selection != policy.semantic_author.selection:
            raise ValueError(
                "recipe author model must match runtime policy semanticAgent.author"
            )
        if pair.reviewer.selection != policy.semantic_reviewer.selection:
            raise ValueError(
                "recipe reviewer model must match runtime policy semanticAgent.reviewer"
            )
        runtime = policy.semantic_agent_runtime
        requires_new_retry_of = False
    else:
        explicit = policy.explicit_semantic_selection(selection_id)
        family_by_selection = {
            CURSOR_GROK_SEMANTIC_SELECTION_ID: ModelFamily.GROK,
            CURSOR_AUTO_SEMANTIC_SELECTION_ID: ModelFamily.AUTO,
        }
        if explicit.selection_id not in family_by_selection:
            raise ValueError(
                f"unsupported explicit semantic selection: {explicit.selection_id}"
            )
        model = ExecutionModel(
            provider=explicit.binding.provider,
            model_id=explicit.binding.model,
            family=family_by_selection[explicit.selection_id],
            parameters=explicit.binding.model_parameters,
        )
        pair = ExecutionModelPair(author=model, reviewer=model)
        runtime = explicit.runtime
        requires_new_retry_of = explicit.requires_new_retry_of
    if policy.semantic_fallback_policy != "forbidden":
        raise ValueError("runtime policy semantic fallback must be forbidden")
    return SemanticExecutionBinding(
        selection_id=selection_id,
        pair=pair,
        runtime=runtime,
        requires_new_retry_of=requires_new_retry_of,
    )


def cursor_grok_binding_mismatch(
    binding: SemanticExecutionBinding,
    *,
    role: str = "author",
) -> str | None:
    """Return a mismatch reason unless this is the frozen cursor_grok binding.

    The model version lives in the runtime profile, so moving between grok
    versions is a profile edit rather than a code edit. Precision is unchanged:
    the selection id, provider and model family are still exact, and manifest
    identity drift against the profile digest is still enforced upstream by
    ``semantic_execution_binding_for_execution``.
    """
    if binding.selection_id != CURSOR_GROK_SEMANTIC_SELECTION_ID:
        return (
            f"{role} requires the {CURSOR_GROK_SEMANTIC_SELECTION_ID} selection, "
            f"got {binding.selection_id}"
        )
    model = binding.pair.reviewer if role == "reviewer" else binding.pair.author
    if model.provider is not AgentProvider.CURSOR_SDK:
        return (
            f"{role} provider must be {AgentProvider.CURSOR_SDK.value}, "
            f"got {model.provider.value}"
        )
    if model.family is not ModelFamily.GROK or not model.model_id.startswith("grok"):
        return f"{role} model must be a grok model, got {model.model_id}"
    return None


def governed_cursor_grok_model(runtime_profile: str | None = None) -> str:
    """Return the grok model id frozen by one runtime profile."""
    policy = (
        load_runtime_policy(runtime_profile)
        if runtime_profile
        else active_runtime_policy()
    )
    binding = policy.explicit_semantic_selection(
        CURSOR_GROK_SEMANTIC_SELECTION_ID
    ).binding
    if binding.provider is not AgentProvider.CURSOR_SDK:
        raise ValueError(
            f"{CURSOR_GROK_SEMANTIC_SELECTION_ID} must bind "
            f"{AgentProvider.CURSOR_SDK.value}"
        )
    if not binding.model.startswith("grok"):
        raise ValueError(
            f"{CURSOR_GROK_SEMANTIC_SELECTION_ID} must bind a grok model, "
            f"got {binding.model}"
        )
    return binding.model


def execution_model_pair(
    recipe: Mapping[str, Any],
    semantic_selection_id: object = DEFAULT_SEMANTIC_SELECTION_ID,
) -> ExecutionModelPair:
    return semantic_execution_binding(recipe, semantic_selection_id).pair


def execution_model_pair_for_execution(execution_id: str) -> ExecutionModelPair:
    """Retired: current execution model identity lives in stage actor evidence."""
    from content.execution.workspace import load_execution_manifest

    manifest = load_execution_manifest(execution_id)
    if manifest.get("hostRuntime") != "external_host_agent":
        raise ValueError(
            "execution manifest hostRuntime must be external_host_agent"
        )
    raise ValueError(
        "current execution model pair is not manifest state; read stage semantic actor evidence"
    )


def semantic_execution_binding_for_execution(
    execution_id: str,
) -> SemanticExecutionBinding:
    """Retired for current manifests; stage actor evidence is authoritative."""
    from content.execution.workspace import load_execution_manifest

    manifest = load_execution_manifest(execution_id)
    if manifest.get("hostRuntime") != "external_host_agent":
        raise ValueError(
            "execution manifest hostRuntime must be external_host_agent"
        )
    raise ValueError(
        "current semantic binding is not manifest state; read stage semantic actor evidence"
    )


__all__ = [
    "ExecutionModel",
    "ExecutionModelPair",
    "SemanticExecutionBinding",
    "DEFAULT_SEMANTIC_SELECTION_ID",
    "CURSOR_GROK_SEMANTIC_SELECTION_ID",
    "CURSOR_AUTO_SEMANTIC_SELECTION_ID",
    "SEMANTIC_SELECTION_IDS",
    "ModelFamily",
    "cursor_grok_binding_mismatch",
    "governed_cursor_grok_model",
    "execution_model_pair",
    "execution_model_pair_for_execution",
    "normalize_semantic_selection_id",
    "semantic_execution_binding",
    "semantic_execution_binding_for_execution",
]
