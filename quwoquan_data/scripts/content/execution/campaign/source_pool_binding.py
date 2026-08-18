"""Immutable source-pool binding shared by scale campaign lanes."""
from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.content_library import library_root_for_output
from core.io import read_json
from core.schema import assert_valid
from content.execution.campaign.lane import normalize_active_carriers
from content.execution.campaign.source_pool_binding_io import (
    digest as _digest,
    file_sha256 as _file_sha256,
    link_evidence_surface_from_library,
    relative_to_output as _relative,
    safe_evidence_directory as _safe_evidence_directory,
    safe_evidence_file as _safe_evidence_file,
    shortfall as _shortfall,
)

from content.source.research.homepage_article_source_ready_batch import (
    CAPSULE_SCHEMA as SOURCE_READY_CAPSULE_SCHEMA,
)
from content.source.research.homepage_article_source_ready_batch import (
    HomepageArticleSourceReadyBatchError,
    validate_source_ready_candidate_capsule,
)
from content.source.research.scale_source_pool import (
    SOURCE_POOL_SHORTFALL,
    ScaleSourcePoolError,
    validate_scale_source_pool,
    validate_scale_source_pool_evidence,
)

def _member_root_ref(candidate: Mapping[str, Any]) -> str:
    raw = candidate.get("sourceReadyEvidenceRootRef")
    if raw is None:
        return "."
    ref = str(raw).strip()
    relative = Path(ref)
    if not ref or relative.is_absolute() or (ref != "." and ".." in relative.parts):
        raise ValueError(f"unsafe source-ready evidence root ref: {ref!r}")
    return ref


def _member_file_ref(candidate: Mapping[str, Any], ref: object) -> str:
    raw = str(ref or "").strip()
    relative = Path(raw)
    if not raw or relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe source-ready member evidence ref: {raw!r}")
    root_ref = _member_root_ref(candidate)
    if root_ref == ".":
        return relative.as_posix()
    return (Path(root_ref) / relative).as_posix()


def _selected_candidates(
    plan: Mapping[str, Any], selections: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    by_id = {
        str(row["candidateId"]): dict(row)
        for row in plan.get("candidates") or []
        if isinstance(row, Mapping)
    }
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    active = normalize_active_carriers(selections)
    for carrier in active:
        selection = validate_lane_source_pool_selection(
            selections[carrier],
            carrier=carrier,
            count=int(selections[carrier].get("candidateCount") or 0),
        )
        for candidate_id in selection["candidateIds"]:
            row = by_id.get(str(candidate_id))
            if row is None or row.get("carrier") != carrier:
                raise ValueError(
                    f"{carrier} selected candidate is absent from frozen plan: "
                    f"{candidate_id}"
                )
            if candidate_id in seen:
                raise ValueError(f"selected candidate is duplicated: {candidate_id}")
            seen.add(str(candidate_id))
            selected.append(row)
    return sorted(
        selected, key=lambda row: (str(row["carrier"]), str(row["candidateId"]))
    )


def _snapshot_document(
    plan: Mapping[str, Any],
    selections: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    stable: dict[str, Any] = {
        "schema": "quwoquan_data.scale_source_pool_snapshot",
        "planDigest": plan["planDigest"],
        "laneSourcePoolSelections": {
            carrier: dict(selections[carrier])
            for carrier in normalize_active_carriers(selections)
        },
        "selectedCandidates": _selected_candidates(plan, selections),
    }
    document = {**stable, "snapshotDigest": _digest(stable)}
    assert_valid(document, "execution", "scale_source_pool_snapshot")
    return document


def _add_ref(refs: dict[str, str], ref: object, sha: object) -> None:
    relative = str(ref or "")
    expected = str(sha or "")
    previous = refs.setdefault(relative, expected)
    if previous != expected:
        raise ValueError(f"source-pool evidence digest collision: {relative}")


def _add_member_ref(
    refs: dict[str, str],
    candidate: Mapping[str, Any],
    ref: object,
    sha: object,
) -> None:
    _add_ref(refs, _member_file_ref(candidate, ref), sha)


def _nested_source_ready_refs(
    candidate: Mapping[str, Any], *, evidence_root: Path, refs: dict[str, str]
) -> None:
    if candidate.get("carrier") not in {"homepage", "article"}:
        return
    candidate_root = _safe_evidence_directory(
        evidence_root,
        _member_root_ref(candidate),
    )
    capsule_path = _safe_evidence_file(
        candidate_root, str(candidate.get("sourceUnitRef") or "")
    )
    try:
        capsule = read_json(capsule_path)
    except (OSError, TypeError, ValueError):
        return
    if not isinstance(capsule, Mapping) or capsule.get("schema") != SOURCE_READY_CAPSULE_SCHEMA:
        return
    validate_source_ready_candidate_capsule(capsule, evidence_root=candidate_root)
    materialization = capsule["materialization"]
    _add_member_ref(
        refs,
        candidate,
        materialization["body"]["ref"],
        materialization["body"]["fileSha256"],
    )
    for row in materialization["media"]:
        _add_member_ref(refs, candidate, row["ref"], row["fileSha256"])
    provenance = capsule["provenance"]
    _add_member_ref(
        refs,
        candidate,
        provenance["coverageProjectionRef"],
        provenance["coverageProjectionFileSha256"],
    )
    _add_member_ref(
        refs,
        candidate,
        provenance["seedSelectionRef"],
        provenance["seedSelectionFileSha256"],
    )
    _add_member_ref(
        refs,
        candidate,
        provenance["discoveryEvidenceRef"],
        provenance["discoveryEvidenceFileSha256"],
    )
    for field in (
        "acquisitionEvidenceRefs", "rightsEvidenceRefs", "qualityEvidenceRefs"
    ):
        for row in provenance[field]:
            _add_member_ref(refs, candidate, row["ref"], row["fileSha256"])


def _selected_evidence_refs(
    candidates: list[dict[str, Any]], *, evidence_root: Path
) -> dict[str, str]:
    refs: dict[str, str] = {}
    for candidate in candidates:
        prefixes = ["sourceUnit", "acquisition", "rights", "quality"]
        if candidate["carrier"] == "video":
            prefixes.append("playability")
        for prefix in prefixes:
            _add_member_ref(
                refs,
                candidate,
                candidate[f"{prefix}Ref"],
                candidate[f"{prefix}FileSha256"],
            )
        _nested_source_ready_refs(candidate, evidence_root=evidence_root, refs=refs)
    return refs


def _validate_selected_evidence(
    candidates: list[dict[str, Any]], *, evidence_root: Path
) -> set[str]:
    refs = _selected_evidence_refs(candidates, evidence_root=evidence_root)
    for ref, expected in refs.items():
        if _file_sha256(_safe_evidence_file(evidence_root, ref)) != expected:
            raise ValueError(f"selected source-pool evidence drift: {ref}")
    actual = {
        path.relative_to(evidence_root).as_posix()
        for path in evidence_root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    if actual != set(refs):
        raise ValueError("source-pool capsule contains non-selected evidence")
    return actual


def bind_scale_source_pool(
    plan_path: Path,
    *,
    evidence_root: Path,
    output_root: Path,
    target_scale: str,
    carrier: str,
    count: int,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    active_carriers: tuple[str, ...] | None = None,
    workload_targets: Mapping[str, int] | None = None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Validate physical evidence and freeze one deterministic lane selection."""

    resolved_plan = plan_path.expanduser().resolve()
    resolved_evidence = evidence_root.expanduser().resolve()
    try:
        plan = read_json(resolved_plan)
        if not isinstance(plan, Mapping):
            raise TypeError("scale source pool plan must be an object")
        validate_scale_source_pool_evidence(plan, evidence_root=resolved_evidence)
    except (OSError, TypeError, ValueError, ScaleSourcePoolError) as exc:
        raise _shortfall(exc) from exc
    expected_identity = (source_revision, source_digest, entity_catalog_digest)
    actual_identity = tuple(
        str(plan.get(field) or "")
        for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest")
    )
    observed_scale = str(plan.get("targetScale") or "")
    if (
        observed_scale not in {target_scale, "WORKLOAD"}
        or actual_identity != expected_identity
    ):
        raise ValueError(f"{SOURCE_POOL_SHORTFALL}: source-pool identity drift")
    if active_carriers is not None and list(active_carriers) != plan.get(
        "activeCarriers"
    ):
        raise ValueError(f"{SOURCE_POOL_SHORTFALL}: source-pool activeCarriers drift")
    if workload_targets is not None and dict(workload_targets) != plan.get(
        "workloadTargets"
    ):
        raise ValueError(f"{SOURCE_POOL_SHORTFALL}: source-pool workloadTargets drift")
    ordered = sorted(
        (
            dict(row)
            for row in plan.get("candidates") or []
            if isinstance(row, Mapping) and row.get("carrier") == carrier
        ),
        key=lambda row: (str(row["carrier"]), str(row["objectRef"])),
    )
    if len(ordered) < count:
        raise ValueError(
            f"{SOURCE_POOL_SHORTFALL}: {carrier} candidateCount={len(ordered)} required={count}"
        )
    candidate_ids = [str(row["candidateId"]) for row in ordered[:count]]
    stable_selection: dict[str, Any] = {
        "carrier": carrier,
        "candidateIds": candidate_ids,
        "candidateCount": len(candidate_ids),
    }
    selection = {**stable_selection, "selectionDigest": _digest(stable_selection)}
    binding = {
        "poolId": str(plan["poolId"]),
        "targetScale": str(plan["targetScale"]),
        "workloadMode": str(plan["workloadMode"]),
        "activeCarriers": list(plan["activeCarriers"]),
        "workloadTargets": dict(plan["workloadTargets"]),
        "sourceRevision": str(plan["sourceRevision"]),
        "sourceDigest": str(plan["sourceDigest"]),
        "entityCatalogDigest": str(plan["entityCatalogDigest"]),
        "planRef": _relative(resolved_plan, output_root, label="scale source pool"),
        "planDigest": str(plan["planDigest"]),
        "planFileSha256": _file_sha256(resolved_plan),
    }
    evidence_ref = _relative(
        resolved_evidence, output_root, label="source pool evidence root"
    )
    assert_valid(binding, "execution", "scale_source_pool_binding")
    assert_valid(selection, "execution", "scale_source_pool_selection")
    return binding, evidence_ref, selection


def validate_bound_scale_source_pool(
    binding: Mapping[str, Any],
    *,
    evidence_root_ref: str,
    output_root: Path,
) -> dict[str, Any]:
    """Re-read exact plan/evidence bytes; no discovery or fallback is allowed."""

    try:
        assert_valid(dict(binding), "execution", "scale_source_pool_binding")
        plan_path = (output_root / str(binding["planRef"])).resolve()
        evidence_root = (output_root / evidence_root_ref).resolve()
        plan_path.relative_to(output_root.resolve())
        evidence_root.relative_to(output_root.resolve())
        if _file_sha256(plan_path) != binding["planFileSha256"]:
            raise ValueError("source-pool planFileSha256 drift")
        plan = read_json(plan_path)
        if not isinstance(plan, Mapping):
            raise TypeError("source-pool plan must be an object")
        if any(
            plan.get(field) != binding.get(field)
            for field in (
                "poolId", "targetScale", "workloadMode", "activeCarriers", "workloadTargets",
                "sourceRevision", "sourceDigest",
                "entityCatalogDigest", "planDigest",
            )
        ):
            raise ValueError("source-pool binding drift")
        validate_scale_source_pool_evidence(plan, evidence_root=evidence_root)
        return dict(plan)
    except (OSError, TypeError, ValueError, ScaleSourcePoolError) as exc:
        raise _shortfall(exc) from exc


def materialize_bound_scale_source_pool(
    binding: Mapping[str, Any],
    *,
    evidence_root_ref: str,
    output_root: Path,
    destination: Path,
    lane_selections: Mapping[str, Mapping[str, Any]],
    expected_snapshot_digest: str | None = None,
) -> str:
    """Copy the plan plus only selected evidence/CAS into a capsule."""

    plan = validate_bound_scale_source_pool(
        binding,
        evidence_root_ref=evidence_root_ref,
        output_root=output_root,
    )
    source_evidence = (output_root / evidence_root_ref).resolve()
    target_evidence = destination / "evidence"
    destination.mkdir(parents=True, exist_ok=False)
    snapshot = _snapshot_document(plan, lane_selections)
    refs = _selected_evidence_refs(
        snapshot["selectedCandidates"], evidence_root=source_evidence
    )
    link_evidence_surface_from_library(
        refs,
        source_evidence=source_evidence,
        target_evidence=target_evidence,
        library_root=library_root_for_output(output_root),
    )
    source_plan = (output_root / str(binding["planRef"])).resolve()
    shutil.copyfile(source_plan, destination / "plan.json")
    from core.io import write_json

    write_json(destination / "selected.json", snapshot)
    _validate_selected_evidence(
        snapshot["selectedCandidates"], evidence_root=target_evidence
    )
    if (
        expected_snapshot_digest is not None
        and snapshot["snapshotDigest"] != expected_snapshot_digest
    ):
        raise ValueError(
            f"{SOURCE_POOL_SHORTFALL}: source-pool snapshot digest drift"
        )
    return str(snapshot["snapshotDigest"])


def bound_scale_source_pool_snapshot_digest(
    binding: Mapping[str, Any],
    *,
    evidence_root_ref: str,
    output_root: Path,
    lane_selections: Mapping[str, Mapping[str, Any]],
) -> str:
    """Derive the selected-only snapshot identity before capsule creation."""

    plan = validate_bound_scale_source_pool(
        binding,
        evidence_root_ref=evidence_root_ref,
        output_root=output_root,
    )
    return str(_snapshot_document(plan, lane_selections)["snapshotDigest"])


def resolve_capsule_scale_source_pool_identity(
    binding: Mapping[str, Any] | None,
    *,
    evidence_root_ref: str | None,
    output_root: Path,
    lane_selections: Mapping[str, Mapping[str, Any]] | None,
) -> tuple[str | None, str | None]:
    values = (binding, evidence_root_ref, lane_selections)
    if not any(value is not None for value in values):
        return None, None
    if not all(value is not None for value in values):
        raise ValueError(f"{SOURCE_POOL_SHORTFALL}: incomplete capsule pool binding")
    assert binding is not None and evidence_root_ref is not None
    assert lane_selections is not None
    digest = bound_scale_source_pool_snapshot_digest(
        binding,
        evidence_root_ref=evidence_root_ref,
        output_root=output_root,
        lane_selections=lane_selections,
    )
    return "scale-source-pool", digest


def validate_capsule_scale_source_pool(
    binding: Mapping[str, Any],
    *,
    snapshot_root: Path,
    lane_selections: Mapping[str, Mapping[str, Any]],
    expected_snapshot_digest: str | None = None,
) -> dict[str, Any]:
    try:
        plan_path = snapshot_root / "plan.json"
        if _file_sha256(plan_path) != binding["planFileSha256"]:
            raise ValueError("capsule source-pool plan bytes drift")
        plan = read_json(plan_path)
        if not isinstance(plan, Mapping):
            raise TypeError("capsule source-pool plan must be an object")
        if any(
            plan.get(field) != binding.get(field)
            for field in (
                "poolId", "targetScale", "workloadMode", "activeCarriers", "workloadTargets",
                "sourceRevision", "sourceDigest",
                "entityCatalogDigest", "planDigest",
            )
        ):
            raise ValueError("capsule source-pool identity drift")
        validate_scale_source_pool(plan)
        snapshot = read_json(snapshot_root / "selected.json")
        if not isinstance(snapshot, Mapping):
            raise TypeError("capsule selected source-pool snapshot must be an object")
        assert_valid(dict(snapshot), "execution", "scale_source_pool_snapshot")
        stable = {key: value for key, value in snapshot.items() if key != "snapshotDigest"}
        if (
            snapshot.get("snapshotDigest") != _digest(stable)
            or snapshot.get("planDigest") != binding.get("planDigest")
            or snapshot.get("laneSourcePoolSelections")
            != {
                carrier: dict(lane_selections[carrier])
                for carrier in normalize_active_carriers(lane_selections)
            }
            or snapshot.get("selectedCandidates")
            != _selected_candidates(plan, lane_selections)
            or (
                expected_snapshot_digest is not None
                and snapshot.get("snapshotDigest") != expected_snapshot_digest
            )
        ):
            raise ValueError("capsule selected source-pool snapshot drift")
        _validate_selected_evidence(
            list(snapshot["selectedCandidates"]),
            evidence_root=snapshot_root / "evidence",
        )
        return dict(plan)
    except (
        OSError, TypeError, ValueError, ScaleSourcePoolError,
        HomepageArticleSourceReadyBatchError,
    ) as exc:
        raise _shortfall(exc) from exc


def capsule_source_pool_fields(
    binding: dict[str, Any] | None,
    selections: dict[str, dict[str, Any]] | None,
    snapshot_root_ref: str | None,
    snapshot_digest: str | None = None,
) -> dict[str, Any]:
    values = (binding, selections, snapshot_root_ref, snapshot_digest)
    if any(value is not None for value in values) and not all(
        value is not None for value in values
    ):
        raise ValueError(f"{SOURCE_POOL_SHORTFALL}: incomplete capsule pool binding")
    if binding is None:
        return {}
    return {
        "scaleSourcePool": binding,
        "laneSourcePoolSelections": selections,
        "sourcePoolSnapshotRootRef": snapshot_root_ref,
        "sourcePoolSnapshotDigest": snapshot_digest,
    }


def load_capsule_source_pool(
    stable: Mapping[str, Any], *, capsule_path: Path
) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]] | None, str | None]:
    binding = stable.get("scaleSourcePool")
    selections = stable.get("laneSourcePoolSelections")
    root_ref = stable.get("sourcePoolSnapshotRootRef")
    snapshot_digest = stable.get("sourcePoolSnapshotDigest")
    if binding is None:
        return None, None, None
    if not isinstance(binding, Mapping) or not isinstance(selections, Mapping):
        raise TypeError("campaign capsule source-pool binding is invalid")
    result: dict[str, dict[str, Any]] = {}
    for carrier in normalize_active_carriers(selections):
        selection = selections.get(carrier)
        if not isinstance(selection, Mapping):
            raise TypeError(f"campaign capsule lacks {carrier} pool selection")
        result[carrier] = validate_lane_source_pool_selection(
            selection,
            carrier=carrier,
            count=int(selection.get("candidateCount") or 0),
        )
    validate_capsule_scale_source_pool(
        binding,
        snapshot_root=capsule_path / str(root_ref),
        lane_selections=result,
        expected_snapshot_digest=str(snapshot_digest),
    )
    return dict(binding), result, str(root_ref)


def validate_lane_source_pool_selection(
    selection: Mapping[str, Any], *, carrier: str, count: int
) -> dict[str, Any]:
    try:
        value = dict(selection)
        assert_valid(value, "execution", "scale_source_pool_selection")
        stable = {key: item for key, item in value.items() if key != "selectionDigest"}
        if (
            value.get("carrier") != carrier
            or value.get("candidateCount") != len(value.get("candidateIds") or [])
            or value.get("candidateCount") != count
            or value.get("selectionDigest") != _digest(stable)
        ):
            raise ValueError("lane source-pool selection drift")
        return value
    except (TypeError, ValueError) as exc:
        raise _shortfall(exc) from exc


__all__ = [
    "bind_scale_source_pool",
    "bound_scale_source_pool_snapshot_digest",
    "capsule_source_pool_fields",
    "load_capsule_source_pool",
    "materialize_bound_scale_source_pool",
    "resolve_capsule_scale_source_pool_identity",
    "validate_bound_scale_source_pool",
    "validate_capsule_scale_source_pool",
    "validate_lane_source_pool_selection",
]
