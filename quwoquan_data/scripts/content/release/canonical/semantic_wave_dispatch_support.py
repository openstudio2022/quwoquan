"""Physical source binding and selection support for semantic wave dispatch."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from content.execution.source_pool.binding import (
    validate_bound_scale_source_pool,
)
from content.execution.planning.retry_unfinished_scope import (
    load_retry_unfinished_scope,
)
from content.release.canonical.object_transaction_contract import _read_json
from content.release.canonical.pool_source_ready_input import (
    physical_evidence_binding,
)
from content.source.research.scale_source_pool import ScaleSourcePoolError
from core.entity_object import parse_entity_ref

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
            raise _fail(
                DISPATCH_INVALID, f"wave candidate absent from pool: {candidate_id}"
            )
        carrier = str(candidate.get("carrier") or "")
        expected = {
            "carrier": candidate.get("carrier"),
            "candidateId": candidate.get("candidateId"),
            "objectRef": str(candidate.get("objectRef") or "").strip("/"),
            "entityRef": candidate.get("entityRef"),
            **physical_evidence_binding(candidate, carrier=carrier),
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
    load_scope: Any = load_retry_unfinished_scope,
) -> list[dict[str, Any]]:
    """Bind an exact failed post-author ref set back to predecessor pool rows."""

    predecessor_root = output_root / "data/tasks" / predecessor_execution_id
    try:
        scope = load_scope(
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


__all__ = [
    "DISPATCH_COLLISION",
    "DISPATCH_EMPTY",
    "DISPATCH_INVALID",
    "_CARRIERS",
    "_FAMILIES",
    "_SAFE_ID",
    "_SAFE_SCOPE",
    "_SELECTORS",
    "SemanticWaveDispatchError",
    "_digest",
    "_fail",
    "_file_sha256",
    "_output_path",
    "_selection",
    "_slot_count",
    "_source_binding",
    "_target_names",
    "_unfinished_retry_candidates",
    "_wave_input",
]
