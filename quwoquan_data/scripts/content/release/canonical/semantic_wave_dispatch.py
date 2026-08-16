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
from content.execution.identity import build_execution_id, parse_execution_id
from content.execution.planning.retry_unfinished_scope import (
    load_retry_unfinished_scope,
)
from content.execution.planning.semantic_preflight_admission import (
    bind_semantic_preflight_receipt,
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

_EXTRACTED_DEPENDENCIES = (
    bind_semantic_preflight_receipt,
    build_execution_id,
    task_execute_argv,
)

DISPATCH_INVALID = "DATA.SEMANTIC.WAVE_DISPATCH_INVALID"
DISPATCH_EMPTY = "DATA.SEMANTIC.WAVE_INPUT_EMPTY"
DISPATCH_COLLISION = "DATA.SEMANTIC.WAVE_DISPATCH_COLLISION"

_CARRIERS = ("homepage", "article", "image", "video")
_FAMILIES = {carrier: f"content/travel/{carrier}/{carrier}" for carrier in _CARRIERS}
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
    if (
        path.is_symlink()
        or (directory and not path.is_dir())
        or (not directory and not path.is_file())
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
    if (
        not isinstance(source_input, Mapping)
        or source_input.get("status") != "validated"
    ):
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
        "sourceRevision": str(plan["sourceRevision"]),
        "sourceDigest": str(plan["sourceDigest"]),
        "entityCatalogDigest": str(plan["entityCatalogDigest"]),
        "planRef": plan_ref,
        "planDigest": str(plan["planDigest"]),
        "planFileSha256": file_digest,
    }
    if plan.get("targetScale") != inspection.get("milestone") or plan.get(
        "planDigest"
    ) != source_input.get("sourcePoolDigest"):
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
            raise _fail(
                DISPATCH_INVALID, f"wave candidate absent from pool: {candidate_id}"
            )
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
            raise _fail(
                DISPATCH_INVALID, f"wave candidate projection drift: {candidate_id}"
            )
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
        raise _fail(
            DISPATCH_INVALID, "unfinished ref is absent from predecessor pool slot"
        )
    return [by_id[candidate_id] for candidate_id in scope.candidate_ids]


def build_semantic_wave_dispatch(
    *,
    dispatch_id: str,
    pool_inspection_ref: str,
    semantic_preflight_receipt_ref: str,
    run_date: str,
    scope: str,
    region_ref: str,
    sequence_start: int,
    predecessor_dispatch_ref: str | None = None,
    predecessor_execution_ids: Mapping[str, str] | None = None,
    predecessor_unfinished_refs: Mapping[str, Sequence[str]] | None = None,
    required_workers: int,
    partition_count: int,
    capacity_plan_digest: str,
    output_root: Path,
    publish_root: Path,
    require_fresh_preflight: bool = True,
) -> dict[str, Any]:
    from content.release.canonical.semantic_wave_dispatch_builder import (
        build_semantic_wave_dispatch as build,
    )

    return build(
        dispatch_id=dispatch_id,
        pool_inspection_ref=pool_inspection_ref,
        semantic_preflight_receipt_ref=semantic_preflight_receipt_ref,
        run_date=run_date,
        scope=scope,
        region_ref=region_ref,
        sequence_start=sequence_start,
        predecessor_dispatch_ref=predecessor_dispatch_ref,
        predecessor_execution_ids=predecessor_execution_ids,
        predecessor_unfinished_refs=predecessor_unfinished_refs,
        required_workers=required_workers,
        partition_count=partition_count,
        capacity_plan_digest=capacity_plan_digest,
        output_root=output_root,
        publish_root=publish_root,
        require_fresh_preflight=require_fresh_preflight,
    )


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
                or ["--retry-of", str(slot["retryOf"])] != slot["argv"][6:8]
                or slot["argv"][8 : 8 + len(unfinished_argv)] != unfinished_argv
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
        require_fresh_preflight=not destination.is_file(),
        **kwargs,
    )
    body = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode(
            "utf-8"
        )
        + b"\n"
    )
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
