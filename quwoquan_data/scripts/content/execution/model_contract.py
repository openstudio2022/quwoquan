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
from core.runtime_policy import load_runtime_policy, runtime_profile_digest


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


def execution_model_pair(
    recipe: Mapping[str, Any],
    semantic_selection_id: object = DEFAULT_SEMANTIC_SELECTION_ID,
) -> ExecutionModelPair:
    return semantic_execution_binding(recipe, semantic_selection_id).pair


def execution_model_pair_for_execution(execution_id: str) -> ExecutionModelPair:
    """Resolve the immutable model contract referenced by one execution manifest."""
    return semantic_execution_binding_for_execution(execution_id).pair


def _model_binding_document(binding: SemanticExecutionBinding) -> dict[str, object]:
    author = binding.pair.author
    reviewer = binding.pair.reviewer
    if author.provider is not reviewer.provider:
        raise ValueError("execution manifest supports one provider for both roles")
    return {
        "provider": author.provider.value,
        "authorModel": author.model_id,
        "authorModelFamily": author.family.value,
        "authorModelParameters": author.selection.parameters_document(),
        "reviewerModel": reviewer.model_id,
        "reviewerModelFamily": reviewer.family.value,
        "reviewerModelParameters": reviewer.selection.parameters_document(),
    }


def semantic_execution_binding_for_execution(
    execution_id: str,
) -> SemanticExecutionBinding:
    """Resolve provider/model/runtime only from one frozen execution manifest."""
    from content.execution.planning.recipe.model import load_recipe
    from content.execution.workspace import (
        execution_manifest_recipe_ref,
        load_execution_manifest,
    )

    recipe_ref = execution_manifest_recipe_ref(execution_id)
    recipe = load_recipe(recipe_ref)
    runtime_profile = str(recipe.get("runtimeProfile") or "").strip()
    manifest = load_execution_manifest(execution_id)
    if (
        manifest.get("runtimeProfileId") != runtime_profile
        or manifest.get("runtimeProfileDigest")
        != runtime_profile_digest(runtime_profile)
    ):
        raise ValueError(
            "execution manifest runtime profile identity drift; create retryOf"
        )
    binding = semantic_execution_binding(
        recipe,
        manifest.get("semanticSelectionId"),
    )
    if manifest.get("semanticRuntime") != binding.runtime.value:
        raise ValueError(
            "execution manifest semantic runtime identity drift; create retryOf"
        )
    if manifest.get("modelBinding") != _model_binding_document(binding):
        raise ValueError(
            "execution manifest semantic model binding drift; create retryOf"
        )
    return binding


__all__ = [
    "ExecutionModel",
    "ExecutionModelPair",
    "SemanticExecutionBinding",
    "DEFAULT_SEMANTIC_SELECTION_ID",
    "CURSOR_GROK_SEMANTIC_SELECTION_ID",
    "CURSOR_AUTO_SEMANTIC_SELECTION_ID",
    "SEMANTIC_SELECTION_IDS",
    "ModelFamily",
    "execution_model_pair",
    "execution_model_pair_for_execution",
    "normalize_semantic_selection_id",
    "semantic_execution_binding",
    "semantic_execution_binding_for_execution",
]
