"""Create-once standalone execution requests for one physical semantic wave."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from content.execution.campaign.source_pool_binding import (
    validate_bound_scale_source_pool,
)
from content.execution.campaign.lane import normalize_workloads
from content.execution.campaign.request_envelope import workload_intent
from content.execution.identity import build_execution_id, parse_execution_id
from content.execution.planning.semantic_preflight_admission import (
    bind_semantic_preflight_receipt,
)
from content.execution.planning.capacity_calibration import (
    bind_capacity_calibration_source,
    current_host_class,
)
from content.execution.planning.retry_unfinished_scope import (
    load_retry_unfinished_scope,
)
from content.execution.request import RuntimeExecutionRequest
from content.release.canonical.object_transaction_contract import _read_json
from content.release.canonical.semantic_wave_dispatch_command import (
    task_execute_argv,
)
from content.source.research.scale_source_pool import ScaleSourcePoolError
from core.entity_object import parse_entity_ref
from core.io import read_json
from core.schema import assert_valid

DISPATCH_INVALID = "DATA.SEMANTIC.WAVE_DISPATCH_INVALID"
DISPATCH_EMPTY = "DATA.SEMANTIC.WAVE_INPUT_EMPTY"
DISPATCH_COLLISION = "DATA.SEMANTIC.WAVE_DISPATCH_COLLISION"

_CARRIERS = ("homepage", "article", "image", "video")
_FAMILIES = {
    carrier: f"content/travel/{carrier}/{carrier}" for carrier in _CARRIERS
}
_SELECTORS = {
    "homepage": "source-ready-priority",
    "article": "all",
    "image": "all",
    "video": "source-ready-priority",
}
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,95}$")
_SAFE_SCOPE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class SemanticWaveDispatchError(ValueError):
    """Typed malformed-input or immutable-dispatch blocker."""

    def __init__(self, code: str, issue: object) -> None:
        self.code = code
        self.issue = str(issue).strip()
        if not self.issue:
            raise ValueError("semantic wave dispatch error requires an issue")
        super().__init__(f"{code}: {self.issue}")


def _fail(code: str, issue: object) -> SemanticWaveDispatchError:
    return SemanticWaveDispatchError(code, issue)


def _digest(value: object) -> str:
    body = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _output_path(
    output_root: Path,
    raw_ref: object,
    *,
    label: str,
    directory: bool = False,
) -> tuple[Path, str]:
    root = output_root.expanduser().resolve()
    raw = str(raw_ref or "").strip()
    ref = Path(raw)
    if not raw or ref.is_absolute() or ".." in ref.parts:
        raise _fail(DISPATCH_INVALID, f"{label} must be one relative output ref")
    path = (root / ref).resolve()
    try:
        normalized = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise _fail(DISPATCH_INVALID, f"{label} escapes output root") from exc
    if path.is_symlink() or (directory and not path.is_dir()) or (
        not directory and not path.is_file()
    ):
        kind = "directory" if directory else "file"
        raise _fail(DISPATCH_INVALID, f"{label} is not an exact physical {kind}")
    return path, normalized


def _wave_input(inspection: Mapping[str, Any]) -> dict[str, Any]:
    scheduling = inspection.get("semanticScheduling")
    if not isinstance(scheduling, Mapping):
        raise _fail(DISPATCH_INVALID, "pool inspection lacks semanticScheduling")
    wave = scheduling.get("waveInput")
    if not isinstance(wave, Mapping):
        raise _fail(DISPATCH_INVALID, "pool inspection lacks waveInput")
    stable = {key: value for key, value in wave.items() if key != "waveInputDigest"}
    if wave.get("waveInputDigest") != _digest(stable):
        raise _fail(DISPATCH_INVALID, "waveInputDigest drift")
    candidates = wave.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise _fail(DISPATCH_EMPTY, "waveInput has no physical candidate")
    return dict(wave)


def _source_binding(
    *,
    inspection: Mapping[str, Any],
    wave: Mapping[str, Any],
    output_root: Path,
) -> tuple[dict[str, Any], str, dict[str, dict[str, Any]], Mapping[str, Any]]:
    scheduling = inspection["semanticScheduling"]
    assert isinstance(scheduling, Mapping)
    source_input = scheduling.get("sourceReadyInput")
    if not isinstance(source_input, Mapping) or source_input.get("status") != "validated":
        raise _fail(DISPATCH_INVALID, "sourceReadyInput must be physically validated")
    ref_pairs = (
        ("sourcePoolRef", wave.get("sourcePoolRef")),
        ("sourcePoolDigest", wave.get("sourcePoolDigest")),
        (
            "sourcePoolEvidenceRootRef",
            wave.get("sourcePoolEvidenceRootRef"),
        ),
    )
    drift = [
        field
        for field, wave_value in ref_pairs
        if source_input.get(field) != wave_value
    ]
    if drift:
        raise _fail(
            DISPATCH_INVALID,
            "wave/sourceReadyInput drift: " + ", ".join(drift),
        )
    plan_path, plan_ref = _output_path(
        output_root,
        source_input.get("sourcePoolRef"),
        label="sourcePoolRef",
    )
    _, evidence_ref = _output_path(
        output_root,
        source_input.get("sourcePoolEvidenceRootRef"),
        label="sourcePoolEvidenceRootRef",
        directory=True,
    )
    file_digest = _file_sha256(plan_path)
    if file_digest != source_input.get("sourcePoolFileSha256"):
        raise _fail(DISPATCH_INVALID, "source pool file digest drift")
    plan = _read_json(plan_path)
    binding = {
        "poolId": str(plan["poolId"]),
        "targetScale": str(plan["targetScale"]),
        "workloadMode": str(plan["workloadMode"]),
        "activeCarriers": list(plan["activeCarriers"]),
        "workloadTargets": dict(plan["workloadTargets"]),
        "sourceRevision": str(plan["sourceRevision"]),
        "sourceDigest": str(plan["sourceDigest"]),
        "entityCatalogDigest": str(plan["entityCatalogDigest"]),
        "planRef": plan_ref,
        "planDigest": str(plan["planDigest"]),
        "planFileSha256": file_digest,
    }
    if (
        plan.get("targetScale") != inspection.get("milestone")
        or plan.get("activeCarriers") != wave.get("activeCarriers")
        or plan.get("workloadTargets") != wave.get("workloadTargets")
        or plan.get("planDigest") != source_input.get("sourcePoolDigest")
    ):
        raise _fail(DISPATCH_INVALID, "source pool milestone or digest drift")
    try:
        validate_bound_scale_source_pool(
            binding,
            evidence_root_ref=evidence_ref,
            output_root=output_root,
        )
    except (OSError, TypeError, ValueError, ScaleSourcePoolError) as exc:
        raise _fail(DISPATCH_INVALID, exc) from exc
    by_id = {
        str(row["candidateId"]): dict(row)
        for row in plan.get("candidates") or []
        if isinstance(row, Mapping)
    }
    selected: dict[str, dict[str, Any]] = {}
    for raw in wave["candidates"]:
        if not isinstance(raw, Mapping):
            raise _fail(DISPATCH_INVALID, "wave candidate must be an object")
        candidate_id = str(raw.get("candidateId") or "")
        candidate = by_id.get(candidate_id)
        if candidate is None:
            raise _fail(DISPATCH_INVALID, f"wave candidate absent from pool: {candidate_id}")
        expected = {
            "carrier": candidate.get("carrier"),
            "candidateId": candidate.get("candidateId"),
            "objectRef": str(candidate.get("objectRef") or "").strip("/"),
            "entityRef": candidate.get("entityRef"),
            "sourceUnitRef": candidate.get("sourceUnitRef"),
            "sourceReadyEvidenceRootRef": str(
                candidate.get("sourceReadyEvidenceRootRef") or "."
            ),
        }
        if dict(raw) != expected:
            raise _fail(DISPATCH_INVALID, f"wave candidate projection drift: {candidate_id}")
        if candidate_id in selected:
            raise _fail(DISPATCH_INVALID, f"duplicate wave candidate: {candidate_id}")
        selected[candidate_id] = candidate
    return binding, evidence_ref, selected, scheduling


def _slot_count(
    *, carrier: str, candidate_count: int, scheduling: Mapping[str, Any]
) -> int:
    carrier_rows = scheduling.get("carriers")
    if not isinstance(carrier_rows, list):
        raise _fail(DISPATCH_INVALID, "semanticScheduling.carriers is invalid")
    matches = [
        row
        for row in carrier_rows
        if isinstance(row, Mapping) and row.get("carrier") == carrier
    ]
    if len(matches) != 1:
        raise _fail(DISPATCH_INVALID, f"scheduler carrier row is not exact: {carrier}")
    row = matches[0]
    assigned = row.get("assignedSlots")
    declared = row.get("dispatchCandidateCount")
    if (
        isinstance(assigned, bool)
        or not isinstance(assigned, int)
        or assigned < 1
        or isinstance(declared, bool)
        or not isinstance(declared, int)
        or declared != candidate_count
    ):
        raise _fail(DISPATCH_INVALID, f"scheduler slot/candidate drift: {carrier}")
    # Never manufacture an empty slot when a stale scheduler over-allocated.
    return min(assigned, candidate_count)


def _selection(carrier: str, candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    stable: dict[str, Any] = {
        "carrier": carrier,
        "candidateIds": [str(row["candidateId"]) for row in candidates],
        "candidateCount": len(candidates),
    }
    return {**stable, "selectionDigest": _digest(stable)}


def _target_names(candidates: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    names: list[str] = []
    for row in candidates:
        parsed = parse_entity_ref(str(row.get("entityRef") or ""))
        if parsed is None:
            raise _fail(
                DISPATCH_INVALID,
                f"candidate entityRef is invalid: {row.get('candidateId')}",
            )
        names.append(parsed[2])
    if len(names) != len(set(names)):
        raise _fail(DISPATCH_INVALID, "one slot cannot repeat an entity target")
    return tuple(names)


def _unfinished_retry_candidates(
    *,
    output_root: Path,
    predecessor_execution_id: str,
    predecessor_candidates: Sequence[Mapping[str, Any]],
    unfinished_refs: Sequence[str],
) -> list[dict[str, Any]]:
    """Bind an exact failed post-author ref set back to predecessor pool rows."""

    predecessor_root = output_root / "data/tasks" / predecessor_execution_id
    try:
        scope = load_retry_unfinished_scope(
            predecessor_root,
            predecessor_execution_id=predecessor_execution_id,
            required_object_refs=unfinished_refs,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise _fail(DISPATCH_INVALID, exc) from exc
    by_id = {str(row["candidateId"]): dict(row) for row in predecessor_candidates}
    if any(candidate_id not in by_id for candidate_id in scope.candidate_ids):
        raise _fail(DISPATCH_INVALID, "unfinished ref is absent from predecessor pool slot")
    return [by_id[candidate_id] for candidate_id in scope.candidate_ids]


def build_semantic_wave_dispatch(
    *,
    dispatch_id: str,
    pool_inspection_ref: str,
    semantic_preflight_receipt_ref: str | None,
    capacity_calibration_receipt_ref: str,
    run_date: str,
    scope: str,
    region_ref: str,
    sequence_start: int,
    predecessor_dispatch_ref: str | None = None,
    predecessor_execution_ids: Mapping[str, str] | None = None,
    predecessor_unfinished_refs: Mapping[str, Sequence[str]] | None = None,
    workload_targets: Mapping[str, int] | None = None,
    output_root: Path,
    publish_root: Path,
) -> dict[str, Any]:
    """Validate one inspection and project only its candidate-backed slots."""

    if not _SAFE_ID.fullmatch(dispatch_id):
        raise _fail(DISPATCH_INVALID, "dispatchId is invalid")
    if not _SAFE_SCOPE.fullmatch(scope):
        raise _fail(DISPATCH_INVALID, "scope is invalid")
    if isinstance(sequence_start, bool) or sequence_start < 1:
        raise _fail(DISPATCH_INVALID, "sequenceStart must be positive")
    predecessor_ref = str(predecessor_dispatch_ref or "").strip() or None
    predecessor_ids = {
        str(slot_id).strip(): str(execution_id).strip()
        for slot_id, execution_id in (predecessor_execution_ids or {}).items()
    }
    predecessor_ref_scopes = {
        str(slot_id).strip(): tuple(str(ref).strip() for ref in refs)
        for slot_id, refs in (predecessor_unfinished_refs or {}).items()
    }
    if bool(predecessor_ref) != bool(predecessor_ids):
        raise _fail(
            DISPATCH_INVALID,
            "predecessorDispatchRef and retry predecessor mappings are required together",
        )
    if predecessor_ref_scopes and set(predecessor_ref_scopes) != set(predecessor_ids):
        raise _fail(
            DISPATCH_INVALID,
            "retry unfinished ref scopes must exactly cover predecessor mappings",
        )
    predecessor_manifest: dict[str, Any] | None = None
    predecessor_binding: dict[str, Any] | None = None
    predecessor_slots: dict[str, dict[str, Any]] = {}
    if predecessor_ref is not None:
        predecessor_path, predecessor_ref = _output_path(
            output_root,
            predecessor_ref,
            label="predecessorDispatchRef",
        )
        try:
            predecessor_manifest = validate_semantic_wave_dispatch(
                _read_json(predecessor_path)
            )
        except (OSError, TypeError, ValueError) as exc:
            raise _fail(DISPATCH_INVALID, exc) from exc
        predecessor_binding = {
            "manifestRef": predecessor_ref,
            "manifestFileSha256": _file_sha256(predecessor_path),
            "manifestDigest": str(predecessor_manifest["manifestDigest"]),
        }
        predecessor_slots = {
            str(slot["slotId"]): dict(slot)
            for slot in predecessor_manifest["slots"]
        }
    reference_root = (
        Path(__file__).resolve().parents[4]
        / "reference/travel/entities"
        / region_ref
    ).resolve()
    entities_root = (Path(__file__).resolve().parents[4] / "reference/travel/entities").resolve()
    if (
        reference_root == entities_root
        or entities_root not in reference_root.parents
        or not reference_root.is_dir()
    ):
        raise _fail(DISPATCH_INVALID, "regionRef must resolve to one entity subtree")
    inspection_path, inspection_ref = _output_path(
        output_root,
        pool_inspection_ref,
        label="poolInspectionRef",
    )
    inspection = _read_json(inspection_path)
    try:
        assert_valid(
            inspection,
            "release",
            "pool_inspection",
            label="semantic wave pool inspection",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise _fail(DISPATCH_INVALID, exc) from exc
    if workload_targets is not None and normalize_workloads(
        workload_targets
    ) != normalize_workloads(inspection["workloadTargets"]):
        raise _fail(DISPATCH_INVALID, "dispatch workloadTargets drift from inspection")
    wave = _wave_input(inspection)
    binding, evidence_ref, selected, scheduling = _source_binding(
        inspection=inspection,
        wave=wave,
        output_root=output_root,
    )
    if predecessor_manifest is not None and (
        predecessor_manifest.get("sourcePoolBinding") != binding
        or predecessor_manifest.get("sourcePoolEvidenceRootRef") != evidence_ref
        or predecessor_manifest.get("waveInputDigest") != wave.get("waveInputDigest")
    ):
        raise _fail(
            DISPATCH_INVALID,
            "retry wave must preserve predecessor source-pool and waveInput binding",
        )
    preflight: dict[str, str] | None = None
    if str(semantic_preflight_receipt_ref or "").strip():
        receipt_path, _ = _output_path(
            output_root,
            semantic_preflight_receipt_ref,
            label="semanticPreflightReceiptRef",
        )
        try:
            preflight = bind_semantic_preflight_receipt(
                receipt_path,
                semantic_selection_id="cursor_grok",
                output_root=output_root,
            )
        except (OSError, TypeError, ValueError) as exc:
            raise _fail(DISPATCH_INVALID, exc) from exc
    try:
        capacity_path, capacity_ref = _output_path(
            output_root,
            capacity_calibration_receipt_ref,
            label="capacityCalibrationReceiptRef",
        )
        capacity_calibration = bind_capacity_calibration_source(
            receipt_path=capacity_path,
            receipt_ref=capacity_ref,
            host_class=current_host_class(),
            provider_tier="cursor_grok",
        )
    except (OSError, TypeError, ValueError) as exc:
        raise _fail(DISPATCH_INVALID, exc) from exc
    ordered_by_carrier = {
        carrier: [
            selected[str(row["candidateId"])]
            for row in wave["candidates"]
            if row["carrier"] == carrier
        ]
        for carrier in _CARRIERS
    }
    slots: list[dict[str, Any]] = []
    sequence = sequence_start
    seen_candidates: set[str] = set()
    seen_objects: set[str] = set()
    predecessor_mappings: list[dict[str, Any]] = []
    workloads = normalize_workloads(wave["workloadTargets"])
    intent = workload_intent(
        scale=str(inspection["milestone"]),
        workload_mode=str(inspection["workloadMode"]),
        workloads=workloads,
    )
    for carrier in _CARRIERS:
        candidates = ordered_by_carrier[carrier]
        if not candidates:
            continue
        count = _slot_count(
            carrier=carrier,
            candidate_count=len(candidates),
            scheduling=scheduling,
        )
        chunks = [candidates[index::count] for index in range(count)]
        for carrier_slot, chunk in enumerate(chunks, start=1):
            if not chunk or len(chunk) > 12:
                raise _fail(DISPATCH_INVALID, "slot candidate cardinality is invalid")
            slot_id = f"{carrier}-{carrier_slot:02d}"
            # A retry dispatch is a failed-shard successor, not a replay of
            # every sibling slot in the predecessor wave.  Only explicitly
            # mapped slots are materialized; each selected slot still freezes
            # the exact predecessor candidate/object/selection lineage below.
            if predecessor_manifest is not None and slot_id not in predecessor_ids:
                continue
            candidate_ids = [str(row["candidateId"]) for row in chunk]
            object_refs = [str(row["objectRef"]).strip("/") for row in chunk]
            retry_unfinished_refs: tuple[str, ...] = ()
            selection = _selection(carrier, chunk)
            target_names = _target_names(chunk)
            execution_id = build_execution_id(
                run_date=run_date,
                vertical="travel",
                content_type=carrier,
                intent=intent,
                scope=scope,
                phase="scale",
                sequence=sequence,
            )
            retry_of: str | None = None
            if predecessor_manifest is not None:
                retry_of = predecessor_ids.get(slot_id)
                predecessor_slot = predecessor_slots.get(slot_id)
                if retry_of is None or predecessor_slot is None:
                    raise _fail(
                        DISPATCH_INVALID,
                        f"retry predecessor mapping is incomplete for slot: {slot_id}",
                    )
                if retry_of != predecessor_slot.get("executionId"):
                    raise _fail(
                        DISPATCH_INVALID,
                        f"retry predecessor does not match predecessor dispatch slot: {slot_id}",
                    )
                current_identity = parse_execution_id(execution_id)
                predecessor_identity = parse_execution_id(retry_of)
                comparable = ("vertical", "content_type", "intent", "scope", "phase")
                if any(
                    getattr(current_identity, field)
                    != getattr(predecessor_identity, field)
                    for field in comparable
                ) or predecessor_identity.sequence >= current_identity.sequence:
                    raise _fail(
                        DISPATCH_INVALID,
                        f"retry predecessor must be an earlier sequence in the same scope: {slot_id}",
                    )
                predecessor_request = predecessor_slot.get("taskRequest")
                if not isinstance(predecessor_request, Mapping) or (
                    predecessor_slot.get("carrier") != carrier
                    or predecessor_slot.get("candidateIds") != candidate_ids
                    or predecessor_slot.get("candidateObjectRefs") != object_refs
                    or predecessor_request.get("scaleSourcePool") != binding
                    or predecessor_request.get("sourcePoolEvidenceRootRef") != evidence_ref
                    or predecessor_request.get("sourcePoolSelection") != selection
                    or predecessor_request.get("targetNames") != list(target_names)
                ):
                    raise _fail(
                        DISPATCH_INVALID,
                        f"retry slot drifted from predecessor physical selection: {slot_id}",
                    )
                retry_unfinished_refs = predecessor_ref_scopes.get(slot_id, ())
                if retry_unfinished_refs:
                    chunk = _unfinished_retry_candidates(
                        output_root=output_root,
                        predecessor_execution_id=retry_of,
                        predecessor_candidates=chunk,
                        unfinished_refs=retry_unfinished_refs,
                    )
                    candidate_ids = [str(row["candidateId"]) for row in chunk]
                    object_refs = [str(row["objectRef"]).strip("/") for row in chunk]
                    selection = _selection(carrier, chunk)
                    target_names = _target_names(chunk)
                predecessor_mappings.append(
                    {
                        "slotId": slot_id,
                        "executionId": execution_id,
                        "retryOf": retry_of,
                        "predecessorSlotDigest": str(
                            predecessor_slot["slotDigest"]
                        ),
                        "selectionDigest": str(selection["selectionDigest"]),
                        **(
                            {"unfinishedRefs": list(retry_unfinished_refs)}
                            if retry_unfinished_refs
                            else {}
                        ),
                    }
                )
            if seen_candidates.intersection(candidate_ids) or seen_objects.intersection(
                object_refs
            ):
                raise _fail(DISPATCH_INVALID, "candidate repeated across semantic slots")
            if any((publish_root / ref / "manifest.json").is_file() for ref in object_refs):
                raise _fail(DISPATCH_INVALID, "wave contains an already published object")
            seen_candidates.update(candidate_ids)
            seen_objects.update(object_refs)
            # 一个 slot 只声明工作单元（chunk）与容量校准来源；分区数与
            # capacityPlanDigest 由冻结 execution spec 时按 DEC-002 派生，
            # dispatch 不得先行给出第二份容量事实。
            request = RuntimeExecutionRequest(
                family_ref=_FAMILIES[carrier],
                region_ref=region_ref,
                selector=_selector(carrier),
                count=len(chunk),
                quota=len(chunk),
                capacity_calibration=capacity_calibration,
                worker_host_set_binding=None,
                topic=f"{intent}-{carrier}-wave",
                source_providers=(),
                target_names=target_names,
                scale_source_pool=binding,
                source_pool_evidence_root_ref=evidence_ref,
                source_pool_selection=selection,
            )
            stable_slot: dict[str, Any] = {
                "slotIndex": len(slots) + 1,
                "slotId": slot_id,
                "carrier": carrier,
                "executionId": execution_id,
                "candidateIds": candidate_ids,
                "candidateObjectRefs": object_refs,
                "taskRequest": request.to_document(),
                "argv": task_execute_argv(
                    execution_id=execution_id,
                    carrier=carrier,
                    request=request,
                    semantic_receipt_ref=(
                        str(preflight["receiptRef"])
                        if preflight is not None
                        else None
                    ),
                    retry_of=retry_of,
                    retry_unfinished_refs=retry_unfinished_refs,
                ),
                "queueBackend": "local_file",
                "poolDeliveryBackend": "reliabletask",
            }
            if retry_of is not None:
                stable_slot["retryOf"] = retry_of
            if retry_unfinished_refs:
                stable_slot["retryUnfinishedRefs"] = list(retry_unfinished_refs)
            slots.append({**stable_slot, "slotDigest": _digest(stable_slot)})
            sequence += 1
    if not slots:
        raise _fail(DISPATCH_EMPTY, "wave produced no candidate-backed slot")
    if predecessor_manifest is not None:
        expected_slot_ids = {str(slot["slotId"]) for slot in slots}
        if set(predecessor_ids) != expected_slot_ids:
            raise _fail(
                DISPATCH_INVALID,
                "retry predecessor mappings must exactly cover dispatch slots",
            )
    active = [
        carrier
        for carrier in _CARRIERS
        if any(slot["carrier"] == carrier for slot in slots)
    ]
    dispatched_workloads = {
        carrier: sum(
            int(slot["taskRequest"]["quota"])
            for slot in slots
            if slot["carrier"] == carrier
        )
        for carrier in active
    }
    stable: dict[str, Any] = {
        "schema": "quwoquan_data.semantic_wave_dispatch_manifest",
        "dispatchId": dispatch_id,
        "milestone": str(inspection["milestone"]),
        "workloadMode": str(inspection["workloadMode"]),
        "workloadTargets": dispatched_workloads,
        "poolInspectionRef": inspection_ref,
        "poolInspectionFileSha256": _file_sha256(inspection_path),
        "waveInputDigest": str(wave["waveInputDigest"]),
        "sourcePoolBinding": binding,
        "sourcePoolEvidenceRootRef": evidence_ref,
        "semanticSelectionId": "cursor_grok",
        "capacityCalibration": capacity_calibration,
        "queueBackend": "local_file",
        "poolDeliveryBackend": "reliabletask",
        "activeCarriers": active,
        "slots": slots,
    }
    if preflight is not None:
        stable["semanticPreflightReceipt"] = preflight
    if predecessor_binding is not None:
        stable["predecessorDispatch"] = predecessor_binding
        stable["predecessorMappings"] = predecessor_mappings
    manifest = {**stable, "manifestDigest": _digest(stable)}
    validate_semantic_wave_dispatch(manifest)
    return manifest


def _selector(carrier: str) -> Any:
    from core.control_types import TargetSelector

    return TargetSelector(_SELECTORS[carrier])


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
            raise _fail(DISPATCH_INVALID, "retry lineage must cover every dispatch slot")
        by_slot = {str(row["slotId"]): row for row in mappings}
        if len(by_slot) != len(mappings):
            raise _fail(DISPATCH_INVALID, "duplicate predecessor mapping slotId")
        for slot in retry_slots:
            mapping = by_slot.get(str(slot["slotId"]))
            selection = slot["taskRequest"]["sourcePoolSelection"]
            unfinished_refs = tuple(slot.get("retryUnfinishedRefs") or ())
            unfinished_argv = [
                value
                for ref in unfinished_refs
                for value in ("--retry-unfinished-ref", str(ref))
            ]
            if mapping is None or (
                mapping["executionId"] != slot["executionId"]
                or mapping["retryOf"] != slot["retryOf"]
                or mapping["selectionDigest"] != selection["selectionDigest"]
                or tuple(mapping.get("unfinishedRefs") or ()) != unfinished_refs
                or ["--retry-of", str(slot["retryOf"])]
                != slot["argv"][6:8]
                or slot["argv"][8 : 8 + len(unfinished_argv)] != unfinished_argv
            ):
                raise _fail(DISPATCH_INVALID, f"retry lineage drift: {slot['slotId']}")
            current = parse_execution_id(str(slot["executionId"]))
            predecessor = parse_execution_id(str(slot["retryOf"]))
            comparable = ("vertical", "content_type", "intent", "scope", "phase")
            if any(
                getattr(current, field) != getattr(predecessor, field)
                for field in comparable
            ) or predecessor.sequence >= current.sequence:
                raise _fail(DISPATCH_INVALID, f"retry scope drift: {slot['slotId']}")
    elif retry_slots:
        raise _fail(DISPATCH_INVALID, "slot retryOf requires predecessor dispatch lineage")
    return value


def write_create_once_semantic_wave_dispatch(
    *,
    output_root: Path,
    publish_root: Path,
    **kwargs: Any,
) -> tuple[dict[str, Any], Path]:
    """Atomically persist or replay one exact dispatch manifest."""

    dispatch_id = str(kwargs.get("dispatch_id") or "")
    destination = (
        output_root.expanduser().resolve()
        / "data/local/semantic-wave-dispatches"
        / dispatch_id
        / "manifest.json"
    )
    manifest = build_semantic_wave_dispatch(
        output_root=output_root,
        publish_root=publish_root,
        **kwargs,
    )
    body = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8") + b"\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            existing = read_json(destination)
            if not isinstance(existing, Mapping):
                raise _fail(DISPATCH_COLLISION, "existing dispatch is not an object")
            try:
                frozen = validate_semantic_wave_dispatch(existing)
            except SemanticWaveDispatchError as exc:
                raise _fail(DISPATCH_COLLISION, exc) from exc
            if frozen != manifest:
                raise _fail(
                    DISPATCH_COLLISION,
                    f"create-once dispatch collision: {dispatch_id}",
                )
            return frozen, destination
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)
    return manifest, destination


__all__ = [
    "DISPATCH_COLLISION",
    "DISPATCH_EMPTY",
    "DISPATCH_INVALID",
    "SemanticWaveDispatchError",
    "build_semantic_wave_dispatch",
    "validate_semantic_wave_dispatch",
    "write_create_once_semantic_wave_dispatch",
]
