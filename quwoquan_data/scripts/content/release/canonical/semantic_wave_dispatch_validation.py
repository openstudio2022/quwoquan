"""Schema and retry-lineage validation for semantic wave dispatch."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from content.execution.campaign.lane import normalize_workloads
from content.execution.identity import parse_execution_id
from content.execution.request import RuntimeExecutionRequest
from content.release.canonical.semantic_wave_dispatch_support import (
    _CARRIERS,
    _SELECTORS,
    DISPATCH_INVALID,
    _digest,
    _fail,
)
from core.schema import assert_valid


def _selector(carrier: str) -> Any:
    from core.control_types import TargetSelector

    return TargetSelector(_SELECTORS[carrier])


def _option_occurrences(
    argv: list[str], option: str
) -> tuple[tuple[int, str], ...] | None:
    values: list[tuple[int, str]] = []
    for index, token in enumerate(argv):
        if token != option:
            continue
        if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
            return None
        values.append((index, argv[index + 1]))
    return tuple(values)


def _option_values(argv: list[str], option: str) -> tuple[str, ...] | None:
    occurrences = _option_occurrences(argv, option)
    if occurrences is None:
        return None
    return tuple(value for _index, value in occurrences)


def _has_exact_retry_lineage(
    argv: list[str], *, retry_of: str, unfinished_refs: tuple[str, ...]
) -> bool:
    retry = _option_occurrences(argv, "--retry-of")
    unfinished = _option_occurrences(argv, "--retry-unfinished-ref")
    if retry is None or unfinished is None:
        return False
    expected_values = (retry_of, *unfinished_refs)
    actual = (*retry, *unfinished)
    if tuple(value for _index, value in actual) != expected_values:
        return False
    positions = tuple(index for index, _value in actual)
    return positions == tuple(
        range(positions[0], positions[0] + 2 * len(positions), 2)
    )


def _has_plan_only_stage(argv: list[str]) -> bool:
    return _option_values(argv, "--stage") == ("plan-only",)


def validate_semantic_wave_dispatch(document: Mapping[str, Any]) -> dict[str, Any]:
    try:
        value = dict(document)
        assert_valid(
            value,
            "execution",
            "semantic_wave_dispatch_manifest",
            label="semantic wave dispatch",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise _fail(DISPATCH_INVALID, exc) from exc
    stable = {key: item for key, item in value.items() if key != "manifestDigest"}
    if value.get("manifestDigest") != _digest(stable):
        raise _fail(DISPATCH_INVALID, "manifestDigest drift")
    candidates: list[str] = []
    objects: list[str] = []
    carriers: list[str] = []
    retry_slots: list[dict[str, Any]] = []
    for index, slot in enumerate(value["slots"], start=1):
        slot_stable = {key: item for key, item in slot.items() if key != "slotDigest"}
        if slot["slotIndex"] != index or slot["slotDigest"] != _digest(slot_stable):
            raise _fail(DISPATCH_INVALID, f"slot identity drift: {index}")
        try:
            RuntimeExecutionRequest.from_document(slot["taskRequest"])
        except SystemExit as exc:
            raise _fail(DISPATCH_INVALID, exc) from exc
        candidates.extend(str(item) for item in slot["candidateIds"])
        objects.extend(str(item) for item in slot["candidateObjectRefs"])
        carriers.append(str(slot["carrier"]))
        if not _has_plan_only_stage(slot["argv"]):
            raise _fail(DISPATCH_INVALID, f"dispatch stage drift: {slot['slotId']}")
        if slot.get("retryOf") is not None:
            retry_slots.append(dict(slot))
    if len(candidates) != len(set(candidates)) or len(objects) != len(set(objects)):
        raise _fail(DISPATCH_INVALID, "candidate repeated across semantic slots")
    expected_active = [carrier for carrier in _CARRIERS if carrier in carriers]
    if value["activeCarriers"] != expected_active:
        raise _fail(DISPATCH_INVALID, "activeCarriers drift from slots")
    workloads = normalize_workloads(
        value["workloadTargets"], active_carriers=expected_active
    )
    dispatched = {
        carrier: sum(
            int(slot["taskRequest"]["quota"])
            for slot in value["slots"]
            if slot["carrier"] == carrier
        )
        for carrier in expected_active
    }
    if dispatched != workloads:
        raise _fail(
            DISPATCH_INVALID,
            f"dispatch quotas drift from workloadTargets: {dispatched}",
        )
    has_predecessor = "predecessorDispatch" in value
    has_mappings = "predecessorMappings" in value
    if has_predecessor != has_mappings:
        raise _fail(DISPATCH_INVALID, "predecessor dispatch and mappings must coexist")
    if has_predecessor:
        mappings = value["predecessorMappings"]
        if len(retry_slots) != len(value["slots"]) or len(mappings) != len(retry_slots):
            raise _fail(
                DISPATCH_INVALID, "retry lineage must cover every dispatch slot"
            )
        by_slot = {str(row["slotId"]): row for row in mappings}
        if len(by_slot) != len(mappings):
            raise _fail(DISPATCH_INVALID, "duplicate predecessor mapping slotId")
        for slot in retry_slots:
            mapping = by_slot.get(str(slot["slotId"]))
            selection = slot["taskRequest"]["sourcePoolSelection"]
            unfinished_refs = tuple(slot.get("retryUnfinishedRefs") or ())
            if mapping is None or (
                mapping["executionId"] != slot["executionId"]
                or mapping["retryOf"] != slot["retryOf"]
                or mapping["selectionDigest"] != selection["selectionDigest"]
                or tuple(mapping.get("unfinishedRefs") or ()) != unfinished_refs
                or not _has_exact_retry_lineage(
                    slot["argv"],
                    retry_of=str(slot["retryOf"]),
                    unfinished_refs=unfinished_refs,
                )
            ):
                raise _fail(DISPATCH_INVALID, f"retry lineage drift: {slot['slotId']}")
            current = parse_execution_id(str(slot["executionId"]))
            predecessor = parse_execution_id(str(slot["retryOf"]))
            comparable = ("vertical", "content_type", "intent", "scope", "phase")
            if (
                any(
                    getattr(current, field) != getattr(predecessor, field)
                    for field in comparable
                )
                or predecessor.sequence >= current.sequence
            ):
                raise _fail(DISPATCH_INVALID, f"retry scope drift: {slot['slotId']}")
    elif retry_slots:
        raise _fail(
            DISPATCH_INVALID, "slot retryOf requires predecessor dispatch lineage"
        )
    return value


__all__ = ["_selector", "validate_semantic_wave_dispatch"]
