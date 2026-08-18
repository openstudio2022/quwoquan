"""Typed values and semantic binding parser for the runtime-policy facade."""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from core.control_types import AgentProvider, RuntimeEnvironment
from core.cursor_model import CursorModelParameter, CursorModelSelection


@dataclass(frozen=True, slots=True)
class ProviderTimeouts:
    encyclopedia_seconds: int
    mediawiki_seconds: int
    qunar_seconds: int
    openverse_seconds: int
    overpass_seconds: int


@dataclass(frozen=True, slots=True)
class CoverageDiscoveryPolicy:
    saturation_threshold: float
    saturation_rounds: int
    max_pages_per_cell: int
    max_candidates_per_city_source: int
    max_new_per_cell: int
    request_budget: int
    max_total_candidates: int
    required_empty_pages: int
    request_timeout_seconds: int
    rate_limit_per_second: float
    wiki_category_depth: int
    retry_backoff_multiplier: float
    wikidata_sparql_endpoint: str
    wikidata_result_limit: int
    overpass_result_limit: int
    overpass_endpoints: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SemanticAgentBinding:
    provider: AgentProvider
    model: str
    model_parameters: tuple[CursorModelParameter, ...]

    @property
    def selection(self) -> CursorModelSelection:
        return CursorModelSelection(
            model_id=self.model,
            parameters=self.model_parameters,
        )


@dataclass(frozen=True, slots=True)
class SemanticCalibrationPolicy:
    binding: SemanticAgentBinding
    sample_rate: float
    minimum_sample_count: int
    small_batch_policy: str

    def sample_count(self, accepted_count: int) -> int:
        if (
            isinstance(accepted_count, bool)
            or not isinstance(accepted_count, int)
            or accepted_count < 0
        ):
            raise ValueError("accepted_count must be a non-negative integer")
        if accepted_count == 0:
            return 0
        requested = max(
            self.minimum_sample_count,
            math.ceil(accepted_count * self.sample_rate),
        )
        return min(accepted_count, requested)


@dataclass(frozen=True, slots=True)
class ExplicitSemanticSelection:
    selection_id: str
    binding: SemanticAgentBinding
    runtime: RuntimeEnvironment
    requires_new_retry_of: bool


@dataclass(frozen=True, slots=True)
class RuntimeEvidencePolicy:
    """Timeouts owned by the governed runtime-evidence execution profile."""

    process_inspection_timeout_seconds: float
    queue_fault_event_timeout_seconds: float
    semantic_preflight_receipt_ttl_seconds: int


def mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"runtime policy {label} must be an object")
    return value


def non_empty_string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"runtime policy {label} must be a non-empty string")
    return value.strip()


def non_empty_string_tuple(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"runtime policy {label} must be a non-empty list")
    items = tuple(
        non_empty_string(item, label=f"{label}[{index}]")
        for index, item in enumerate(value)
    )
    if len(set(items)) != len(items):
        raise ValueError(f"runtime policy {label} must not contain duplicates")
    return items


def semantic_binding(value: object, *, label: str) -> SemanticAgentBinding:
    raw = mapping(value, label=label)
    selection = CursorModelSelection.from_config(
        raw.get("model"),
        raw.get("modelParameters"),
        label=label,
    )
    return SemanticAgentBinding(
        provider=AgentProvider(
            non_empty_string(raw.get("provider"), label=f"{label}.provider")
        ),
        model=selection.model_id,
        model_parameters=selection.parameters,
    )


def explicit_semantic_selections(
    value: object,
    *,
    label: str,
) -> tuple[ExplicitSemanticSelection, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"runtime policy {label} must be a non-empty list")
    selections: list[ExplicitSemanticSelection] = []
    for index, item in enumerate(value):
        item_label = f"{label}[{index}]"
        raw = mapping(item, label=item_label)
        selections.append(
            ExplicitSemanticSelection(
                selection_id=non_empty_string(
                    raw.get("selectionId"),
                    label=f"{item_label}.selectionId",
                ),
                binding=semantic_binding(raw, label=item_label),
                runtime=RuntimeEnvironment(
                    non_empty_string(
                        raw.get("runtime"),
                        label=f"{item_label}.runtime",
                    )
                ),
                requires_new_retry_of=raw.get("requiresNewRetryOf") is True,
            )
        )
    ids = [selection.selection_id for selection in selections]
    if len(set(ids)) != len(ids):
        raise ValueError(f"runtime policy {label} contains duplicate selectionId")
    return tuple(selections)


__all__ = [
    "CoverageDiscoveryPolicy",
    "ExplicitSemanticSelection",
    "ProviderTimeouts",
    "RuntimeEvidencePolicy",
    "SemanticAgentBinding",
    "SemanticCalibrationPolicy",
    "explicit_semantic_selections",
    "mapping",
    "non_empty_string",
    "non_empty_string_tuple",
    "semantic_binding",
]
