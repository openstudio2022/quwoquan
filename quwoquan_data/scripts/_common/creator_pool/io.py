"""Creator pool path and gate helpers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from _common.io import read_json, write_json
from _common.paths import (
    REPO_ROOT,
    SCHEMA_ROOT,
    SERVICE_CONTRACTS_METADATA_ROOT,
    _REPO_DATA_ROOT,
    creator_pool_batch_root,
    creator_pool_object_dir,
    creator_pool_shared_dir,
    creator_pool_stage_dir,
    now_iso,
)


def repo_creator_profiles_dir(vertical: str, batch_id: str) -> Path:
    return _REPO_DATA_ROOT / "templates" / "creator_profiles" / vertical / batch_id


def repo_seed_fixture_dir() -> Path:
    return SERVICE_CONTRACTS_METADATA_ROOT / "_shared" / "test_fixtures" / "creator_pool"


def artifacts_readiness_path(name: str) -> Path:
    return REPO_ROOT / "artifacts" / name


def write_gate(path: Path, *, gate_id: str, passed: bool, issues: list[str] | None = None) -> dict[str, Any]:
    payload = {
        "schemaVersion": "quwoquan.gate_verdict",
        "gateId": gate_id,
        "decision": "passed" if passed else "failed",
        "final": True,
        "inputHash": f"sha256:{hashlib.sha256(gate_id.encode()).hexdigest()}",
        "outputHash": f"sha256:{hashlib.sha256(str(passed).encode()).hexdigest()}",
        "issues": issues or [],
        "retryable": not passed,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, payload)
    return payload


def read_review_gate(vertical: str, batch_id: str, creator_ref: str) -> dict[str, Any] | None:
    gate_path = creator_pool_stage_dir(vertical, batch_id, creator_ref, "5.validate") / "review_gate.json"
    if not gate_path.is_file():
        return None
    data = read_json(gate_path)
    return data if isinstance(data, dict) else None


def load_schema(name: str) -> dict[str, Any]:
    path = SCHEMA_ROOT / "creator" / name
    return read_json(path)


def ensure_batch_dirs(vertical: str, batch_id: str) -> Path:
    root = creator_pool_batch_root(vertical, batch_id)
    shared = creator_pool_shared_dir(vertical, batch_id)
    shared.mkdir(parents=True, exist_ok=True)
    (root / "creators").mkdir(parents=True, exist_ok=True)
    return root


def iter_creator_refs(vertical: str, batch_id: str) -> list[str]:
    plan_path = creator_pool_shared_dir(vertical, batch_id) / "creator_pool_plan.json"
    if not plan_path.is_file():
        return []
    plan = read_json(plan_path)
    refs = plan.get("creatorRefs") if isinstance(plan, dict) else None
    if not isinstance(refs, list):
        return []
    return [str(r) for r in refs if str(r).strip()]


def iter_candidates(vertical: str, batch_id: str) -> list[dict[str, Any]]:
    pool_path = creator_pool_shared_dir(vertical, batch_id) / "candidate_pool.json"
    if not pool_path.is_file():
        return []
    data = read_json(pool_path)
    candidates = data.get("candidates") if isinstance(data, dict) else None
    if not isinstance(candidates, list):
        return []
    return [c for c in candidates if isinstance(c, dict)]


def stage_gate_path(vertical: str, batch_id: str, creator_ref: str, stage: str, gate_name: str) -> Path:
    return creator_pool_stage_dir(vertical, batch_id, creator_ref, stage) / gate_name


def write_stage_result(
    vertical: str,
    batch_id: str,
    creator_ref: str,
    stage: str,
    payload: dict[str, Any],
    *,
    filename: str = "stage_result.json",
) -> Path:
    out = creator_pool_stage_dir(vertical, batch_id, creator_ref, stage) / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    payload.setdefault("generatedAt", now_iso())
    write_json(out, payload)
    return out
