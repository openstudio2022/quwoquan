"""Materialize one frozen selection into its canonical execution work package."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.io import write_json, write_ndjson
from core.paths import (
    REPO_ROOT,
    ensure_object_stages,
    execution_catalog,
    execution_entity_object_dir,
    execution_post_object_dir,
)
from content.execution import store
from content.execution.identity import SelectionPolicy
from content.execution.workspace import TARGET_SET_REF, write_frozen_target_set

_POST_CARRIERS = {"article", "image", "video"}


def _object_stage_root(
    execution_id: str,
    *,
    carrier: str,
    target: dict[str, Any],
    type_parts: list[str],
    name: str,
) -> Path:
    """Resolve one frozen target's object root by carrier (DEC-027, fail closed)."""
    if carrier == "homepage":
        return execution_entity_object_dir(
            execution_id, type_parts[0], type_parts[1], name
        )
    if carrier not in _POST_CARRIERS:
        raise ValueError(f"unsupported content carrier: {carrier}")
    angle = str(target.get("publishAngle") or "").strip()
    title = str(target.get("publishTitle") or "").strip()
    seq = target.get("publishSeq") or 1
    if not angle or not title:
        raise ValueError(
            f"post carrier target requires frozen publishAngle/publishTitle: {name}"
        )
    return execution_post_object_dir(
        execution_id, carrier, angle, title, seq=int(seq)
    )


def write_selected_task(spec: dict[str, Any], report: dict[str, Any]) -> Path:
    if store.spec_exists(spec["executionId"]):
        raise FileExistsError(f"execution already exists: {spec['executionId']}")
    spec_path = store.save_spec(spec)
    targets = (spec.get("scope") or {}).get("coverageTargets") or []
    source_ref = str(report.get("discoveryPath") or "").strip()
    try:
        source_ref = Path(source_ref).resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("target selection source must be inside the repository") from exc
    target_set_path, target_set_digest = write_frozen_target_set(
        spec["executionId"],
        targets=targets,
        source_ref=source_ref,
    )
    report["selectionPolicy"] = SelectionPolicy.FROZEN.value
    report["targetSetRef"] = TARGET_SET_REF
    report["targetSetDigest"] = target_set_digest
    remaining = [f"{target['entityType']}/{target['name']}" for target in targets]
    store.save_progress(store.init_progress(spec["executionId"], remaining=remaining))
    rows = []
    region = str((spec.get("scope") or {}).get("region") or "")
    carriers = [
        str(value) for value in (spec.get("content") or {}).get("carriers") or []
    ]
    if len(carriers) != 1:
        raise ValueError("execution spec must freeze exactly one content carrier")
    carrier = carriers[0]
    for target in targets:
        entity_type = str(target.get("entityType") or "").strip()
        name = str(target.get("name") or "").strip()
        if not entity_type or not name:
            continue
        type_parts = entity_type.strip("/").split("/")
        if len(type_parts) != 2:
            raise ValueError(f"invalid target entityType: {entity_type}")
        ensure_object_stages(
            _object_stage_root(
                spec["executionId"],
                carrier=carrier,
                target=target,
                type_parts=type_parts,
                name=name,
            )
        )
        rows.append(
            {
                "topic_id": f"{entity_type}/{name}",
                "domain": type_parts[0],
                "entity_type": entity_type,
                "canonical_name": name,
                "region": region,
                "source_count": 1,
                "geo_tag_ref": str(target.get("geoTagRef") or "").strip(),
                "source_kind": "coverageTarget",
                "status": "candidate",
                "executionId": spec["executionId"],
            }
        )
    write_ndjson(execution_catalog(spec["executionId"]), rows)
    report_path = store.execution_root(spec["executionId"]) / "_shared/target_selection.json"
    write_json(report_path, report)
    if target_set_path != store.execution_root(spec["executionId"]) / TARGET_SET_REF:
        raise AssertionError("frozen target set path drift")
    return spec_path
