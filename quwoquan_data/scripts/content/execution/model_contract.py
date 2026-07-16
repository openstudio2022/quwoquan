"""Typed author/reviewer model contract for one content execution.

The recipe, rather than a model-id prefix heuristic, declares both model IDs
and their provider families.  This keeps independent-review eligibility a
fail-closed execution input that can be checked before any source work starts.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping


class ModelFamily(StrEnum):
    CLAUDE = "claude"
    COMPOSER = "composer"
    GEMINI = "gemini"
    GPT = "gpt"
    GROK = "grok"


@dataclass(frozen=True, slots=True)
class ExecutionModel:
    model_id: str
    family: ModelFamily

    @classmethod
    def from_execution(cls, execution: Mapping[str, Any], *, role: str) -> "ExecutionModel":
        if role == "author":
            model_key, family_key = "model", "modelFamily"
        elif role == "reviewer":
            model_key, family_key = "reviewModel", "reviewModelFamily"
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
        return cls(model_id=model_id, family=family)


@dataclass(frozen=True, slots=True)
class ExecutionModelPair:
    author: ExecutionModel
    reviewer: ExecutionModel

    def __post_init__(self) -> None:
        if self.author.family == self.reviewer.family:
            raise ValueError(
                "independent reviewer model family must differ from author model family"
            )


def execution_model_pair(recipe: Mapping[str, Any]) -> ExecutionModelPair:
    execution = recipe.get("execution")
    if not isinstance(execution, Mapping):
        raise ValueError("recipe.execution must be an object")
    return ExecutionModelPair(
        author=ExecutionModel.from_execution(execution, role="author"),
        reviewer=ExecutionModel.from_execution(execution, role="reviewer"),
    )
