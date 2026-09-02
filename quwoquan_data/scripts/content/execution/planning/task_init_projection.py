"""Project one confirmed WorkRequest package into task-init inputs."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.execution.planning.request_envelope_io import load_campaign_envelope
from content.execution.planning.work_request_store import _assert_work_request_identity
from content.execution.source_pool.binding import (
    validate_bound_scale_source_pool,
    validate_lane_source_pool_selection,
)
from content.source.research.homepage_article_source_ready_batch import (
    validate_source_ready_candidate_capsule,
)
from core import paths
from core.entity_object import parse_entity_ref
from core.io import read_json
from core.schema import assert_valid


class TaskInitProjectionError(ValueError):
    """The confirmed request cannot be projected into immutable init inputs."""


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        + b"\n"
    )


def _portable_path(ref: object, *, output_root: Path, label: str) -> Path:
    relative = Path(str(ref or "").strip())
    if not str(relative) or relative.is_absolute() or ".." in relative.parts:
        raise TaskInitProjectionError(f"{label} must be a portable output ref")
    resolved = (output_root / relative).resolve()
    try:
        resolved.relative_to(output_root)
    except ValueError as exc:
        raise TaskInitProjectionError(f"{label} escapes output root") from exc
    return resolved


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise TaskInitProjectionError(f"{label} must contain one JSON object")
    return value


def _write_create_once(path: Path, value: Mapping[str, Any]) -> str:
    body = _canonical_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = handle.name
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != body:
                raise TaskInitProjectionError(
                    f"task-init input already frozen with different bytes: {path}"
                )
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _post_coordinates(row: Mapping[str, Any], *, carrier: str) -> tuple[str, str, int]:
    parts = Path(str(row.get("objectRef") or "")).parts
    if len(parts) < 3 or parts[0:2] != ("posts", carrier):
        raise TaskInitProjectionError(
            f"{carrier} candidate objectRef is invalid: {row.get('objectRef')!r}"
        )
    suffix = tuple(str(value).strip() for value in parts[2:] if str(value).strip())
    if len(suffix) >= 3 and suffix[-1].isdigit():
        return "/".join(suffix[:-2]), suffix[-2], int(suffix[-1])
    if len(suffix) == 2:
        return suffix[0], suffix[1], 1
    if len(suffix) == 1:
        title = suffix[0]
        angle = {"article": "攻略", "image": "美图", "video": "体验"}[carrier]
        return angle, title, 1
    raise TaskInitProjectionError(f"{carrier} candidate lacks frozen post coordinates")


def _homepage_source(row: Mapping[str, Any], *, evidence_root: Path) -> dict[str, str]:
    member_root = Path(str(row.get("sourceReadyEvidenceRootRef") or "."))
    capsule_ref = Path(str(row.get("sourceUnitRef") or ""))
    if (
        member_root.is_absolute()
        or ".." in member_root.parts
        or capsule_ref.is_absolute()
        or ".." in capsule_ref.parts
        or not str(capsule_ref)
    ):
        raise TaskInitProjectionError("homepage source-ready capsule ref is unsafe")
    capsule_root = evidence_root if str(member_root) == "." else evidence_root / member_root
    capsule = _read_object(capsule_root / capsule_ref, label="homepage source-ready capsule")
    capsule = validate_source_ready_candidate_capsule(capsule, evidence_root=capsule_root)
    candidate = capsule.get("candidate")
    primary = candidate.get("primarySource") if isinstance(candidate, Mapping) else None
    if not isinstance(primary, Mapping):
        raise TaskInitProjectionError("homepage primarySource is missing")
    source = {
        "provider": str(primary.get("sourceKind") or ""),
        "title": str(primary.get("platform") or ""),
        "url": str(primary.get("sourceUrl") or ""),
    }
    if not source["provider"] or not source["title"] or not source["url"].startswith("https://"):
        raise TaskInitProjectionError("homepage primarySource is incomplete")
    return source


def _target(row: Mapping[str, Any], *, carrier: str, evidence_root: Path) -> dict[str, Any]:
    parsed = parse_entity_ref(str(row.get("entityRef") or ""))
    if parsed is None:
        raise TaskInitProjectionError(f"candidate entityRef is invalid: {row.get('entityRef')!r}")
    domain, entity_type, name = parsed
    target: dict[str, Any] = {"name": name, "entityType": f"{domain}/{entity_type}"}
    if carrier == "homepage":
        target["qualifiedHomepageSource"] = _homepage_source(row, evidence_root=evidence_root)
    else:
        angle, title, sequence = _post_coordinates(row, carrier=carrier)
        target.update(
            {"publishAngle": angle, "publishTitle": title, "publishSeq": sequence}
        )
    return target


def project_task_init_inputs(
    *, work_request_path: Path, output_dir: Path, output_root: Path | None = None
) -> dict[str, Any]:
    """Revalidate exact confirmed bytes and create one input pair per carrier."""

    root = (output_root or paths.OUTPUT_ROOT).expanduser().resolve()
    request_path = work_request_path.expanduser().resolve()
    try:
        request_path.relative_to(root)
    except ValueError as exc:
        raise TaskInitProjectionError("WorkRequest must stay under output root") from exc
    work_request = _read_object(request_path, label="WorkRequest")
    work_request_digest = _assert_work_request_identity(work_request)
    request_ref = request_path.relative_to(root).as_posix()
    binding = work_request.get("sourcePool")
    if not isinstance(binding, Mapping):
        raise TaskInitProjectionError("WorkRequest sourcePool binding is missing")
    envelope_rows = work_request.get("carrierEnvelopes")
    if not isinstance(envelope_rows, list) or not envelope_rows:
        raise TaskInitProjectionError("WorkRequest carrierEnvelopes are missing")
    by_carrier = {
        str(row.get("carrier")): row for row in envelope_rows if isinstance(row, Mapping)
    }
    active = tuple(str(value) for value in work_request.get("activeCarriers") or ())
    if set(by_carrier) != set(active):
        raise TaskInitProjectionError("WorkRequest carrier envelope set drift")
    first_envelope = load_campaign_envelope(
        _portable_path(by_carrier[active[0]]["envelopeRef"], output_root=root, label="envelopeRef")
    )
    pool_binding = first_envelope.get("scaleSourcePool")
    evidence_ref = str(first_envelope.get("sourcePoolEvidenceRootRef") or "")
    if not isinstance(pool_binding, Mapping) or not evidence_ref:
        raise TaskInitProjectionError("carrier envelope source-pool binding is incomplete")
    plan = validate_bound_scale_source_pool(
        pool_binding, evidence_root_ref=evidence_ref, output_root=root
    )
    evidence_root = _portable_path(evidence_ref, output_root=root, label="sourcePoolEvidenceRootRef")
    candidates = {
        str(row.get("candidateId")): dict(row)
        for row in plan.get("candidates") or []
        if isinstance(row, Mapping)
    }
    target_root = output_dir.expanduser().resolve()
    try:
        target_root.relative_to(root)
    except ValueError as exc:
        raise TaskInitProjectionError("task-init input output must stay under output root") from exc
    artifacts: list[dict[str, Any]] = []
    projected: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for carrier in active:
        envelope_path = _portable_path(
            by_carrier[carrier]["envelopeRef"], output_root=root, label="envelopeRef"
        )
        envelope = load_campaign_envelope(envelope_path)
        if (
            envelope.get("carrier") != carrier
            or envelope.get("requestDigest") != by_carrier[carrier].get("requestDigest")
            or envelope.get("sourceDigest", {}).get("digest") != work_request.get("sourceDigest")
            or envelope.get("entityCatalogDigest") != work_request.get("entityCatalogDigest")
            or envelope.get("scaleSourcePool") != pool_binding
            or envelope.get("sourcePoolEvidenceRootRef") != evidence_ref
        ):
            raise TaskInitProjectionError(f"{carrier} envelope drifts from WorkRequest")
        selection = envelope.get("sourcePoolSelection")
        if not isinstance(selection, Mapping):
            raise TaskInitProjectionError(f"{carrier} sourcePoolSelection is missing")
        frozen = validate_lane_source_pool_selection(
            selection,
            carrier=carrier,
            count=int(envelope.get("quota") or 0),
        )
        selected: list[dict[str, Any]] = []
        for candidate_id in frozen["candidateIds"]:
            row = candidates.get(str(candidate_id))
            if row is None or row.get("carrier") != carrier:
                raise TaskInitProjectionError(
                    f"{carrier} candidate is absent from frozen source pool: {candidate_id}"
                )
            if any(
                row.get(field) != envelope.get(field)
                for field in ("sourceRevision", "entityCatalogDigest")
            ) or row.get("sourceDigest") != envelope["sourceDigest"]["digest"]:
                raise TaskInitProjectionError(f"{carrier} candidate source identity drift")
            selected.append(row)
        demand = {
            "schema": "quwoquan_data.carrier_demand",
            "status": "confirmed",
            "executionId": envelope["executionId"],
            "carrier": carrier,
            "familyRef": envelope["familyRef"],
            "quota": envelope["quota"],
            "workRequestRef": request_ref,
            "workRequestDigest": work_request_digest,
            "sourceDigest": envelope["sourceDigest"],
            "executionBundle": envelope["executionBundle"],
            "entityCatalogDigest": envelope["entityCatalogDigest"],
            "retryOf": envelope.get("retryOf"),
        }
        targets = [
            _target(row, carrier=carrier, evidence_root=evidence_root) for row in selected
        ]
        bindings = {
            "schema": "quwoquan_data.immutable_candidate_bindings",
            "executionId": envelope["executionId"],
            "carrier": carrier,
            "sourceRef": str(pool_binding["planRef"]),
            "entityCatalogDigest": envelope["entityCatalogDigest"],
            "candidateCount": len(targets),
            "targets": targets,
        }
        assert_valid(demand, "execution", "carrier_demand", label=f"{carrier} carrier demand")
        assert_valid(
            bindings,
            "execution",
            "immutable_candidate_bindings",
            label=f"{carrier} immutable candidate bindings",
        )
        projected.append((carrier, demand, bindings))
    for carrier, demand, bindings in projected:
        lane_root = target_root / carrier
        demand_path = lane_root / "carrier-demand.json"
        bindings_path = lane_root / "immutable-candidate-bindings.json"
        demand_digest = _write_create_once(demand_path, demand)
        bindings_digest = _write_create_once(bindings_path, bindings)
        artifacts.append(
            {
                "carrier": carrier,
                "executionId": demand["executionId"],
                "carrierDemandRef": demand_path.relative_to(root).as_posix(),
                "carrierDemandDigest": demand_digest,
                "candidateBindingsRef": bindings_path.relative_to(root).as_posix(),
                "candidateBindingsDigest": bindings_digest,
                "candidateCount": int(bindings["candidateCount"]),
                "quota": int(demand["quota"]),
            }
        )
    return {
        "schema": "quwoquan_data.task_init_input_projection_result",
        "workRequestRef": request_ref,
        "workRequestDigest": work_request_digest,
        "artifacts": artifacts,
    }


__all__ = ["TaskInitProjectionError", "project_task_init_inputs"]
