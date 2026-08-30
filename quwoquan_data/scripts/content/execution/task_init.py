"""Deterministic host-only work-package initialization."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from content.execution.identity import parse_execution_id, validate_execution_id
from content.execution.workspace import REQUEST_REF, TARGET_SET_REF
from core import paths
from core.io import read_json
from core.schema import assert_valid
from core.source_digest import ExecutionBundleIdentity, SourceDefinitionSnapshot


class TaskInitError(ValueError):
    """The immutable init inputs cannot create one host-only work package."""


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _portable_ref(path: Path, *, output_root: Path) -> str:
    resolved = path.expanduser().resolve()
    root = output_root.expanduser().resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise TaskInitError(f"init input must stay under output root: {resolved}") from exc


def _load_bound_document(path: Path, *, schema_name: str) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise TaskInitError(f"{schema_name} must contain one JSON object")
    assert_valid(value, "execution", schema_name, label=f"task init {schema_name}")
    return value


def _normalized_targets(value: object, *, carrier: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise TaskInitError("immutable candidate bindings must contain targets")
    normalized: list[dict[str, Any]] = []
    refs: set[str] = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            raise TaskInitError("immutable candidate target must be an object")
        target = dict(raw)
        name = str(target.get("name") or "").strip()
        entity_type = str(target.get("entityType") or "").strip().strip("/")
        ref = f"{entity_type}/{name}"
        if not name or len(entity_type.split("/")) != 2 or ref in refs:
            raise TaskInitError(f"invalid or duplicate immutable candidate target: {ref}")
        if carrier != "homepage" and (
            not str(target.get("publishAngle") or "").strip()
            or not str(target.get("publishTitle") or "").strip()
        ):
            raise TaskInitError(f"post candidate lacks frozen publish coordinates: {name}")
        refs.add(ref)
        normalized.append(target)
    return normalized


def _validate_retry(execution_id: str, retry_of: object) -> str | None:
    if retry_of is None:
        return None
    normalized = validate_execution_id(str(retry_of))
    current = parse_execution_id(execution_id)
    previous = parse_execution_id(normalized)
    if (
        normalized == execution_id
        or previous.run_date != current.run_date
        or previous.vertical != current.vertical
        or previous.content_type != current.content_type
        or previous.intent != current.intent
        or previous.scope != current.scope
        or previous.phase != current.phase
        or previous.sequence >= current.sequence
    ):
        raise TaskInitError("retryOf must be an earlier sequence of the same execution scope")
    return normalized


@contextmanager
def _init_lock(execution_id: str) -> Iterator[None]:
    root = paths.DATA_EXECUTIONS_ROOT
    root.mkdir(parents=True, exist_ok=True)
    lock_root = paths.DATA_LOCAL_ROOT / "locks/task-init"
    lock_root.mkdir(parents=True, exist_ok=True)
    lock_path = lock_root / f"{execution_id}.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_stage_document(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(value))
    with path.open("rb") as handle:
        os.fsync(handle.fileno())
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _documents_match(root: Path, documents: Mapping[str, Mapping[str, Any]]) -> bool:
    allowed = {"execution_manifest.json", "0.plan"}
    if not root.is_dir() or {path.name for path in root.iterdir()} != allowed:
        return False
    plan = root / "0.plan"
    if not plan.is_dir() or {path.name for path in plan.iterdir()} != {"request.json", "target_set.json"}:
        return False
    return all((root / rel).is_file() and (root / rel).read_bytes() == _canonical_bytes(value) for rel, value in documents.items())


def initialize_task(*, carrier_demand_path: Path, candidate_bindings_path: Path) -> dict[str, Any]:
    """Validate all immutable inputs, then publish exactly three files atomically."""
    output_root = paths.OUTPUT_ROOT.resolve()
    demand_path = carrier_demand_path.expanduser().resolve()
    candidates_path = candidate_bindings_path.expanduser().resolve()
    demand = _load_bound_document(demand_path, schema_name="carrier_demand")
    bindings = _load_bound_document(candidates_path, schema_name="immutable_candidate_bindings")
    execution_id = validate_execution_id(str(demand["executionId"]))
    identity = parse_execution_id(execution_id)
    carrier = identity.content_type.value
    if demand["carrier"] != carrier or bindings["carrier"] != carrier:
        raise TaskInitError("carrier demand/candidate binding does not match executionId")
    if bindings["executionId"] != execution_id:
        raise TaskInitError("candidate binding executionId does not match demand")
    if demand["entityCatalogDigest"] != bindings["entityCatalogDigest"]:
        raise TaskInitError("candidate binding entity catalog digest drift")
    SourceDefinitionSnapshot.from_document(demand["sourceDigest"])
    ExecutionBundleIdentity.from_document(demand["executionBundle"])
    family_ref = str(demand["familyRef"])
    if f"/{carrier}/" not in f"/{family_ref}/":
        raise TaskInitError("carrier demand familyRef does not match carrier")
    family_path = paths.recipe_path(family_ref)
    if not family_path.is_file():
        raise TaskInitError(f"familyRef does not exist: {family_ref}")
    targets = _normalized_targets(bindings["targets"], carrier=carrier)
    candidate_count = int(bindings["candidateCount"])
    quota = int(demand["quota"])
    if candidate_count != len(targets):
        raise TaskInitError("candidateCount must equal immutable target count")
    if candidate_count < quota:
        raise TaskInitError("accepted candidate count cannot be below demand quota")
    retry_of = _validate_retry(execution_id, demand.get("retryOf"))
    demand_ref = _portable_ref(demand_path, output_root=output_root)
    candidate_ref = _portable_ref(candidates_path, output_root=output_root)
    demand_digest = _file_digest(demand_path)
    candidate_digest = _file_digest(candidates_path)
    request: dict[str, Any] = {
        "schema": "quwoquan_data.task_init_request",
        "executionId": execution_id,
        "familyRef": family_ref,
        "carrier": carrier,
        "quota": quota,
        "workUnitCount": candidate_count,
        "carrierDemand": {
            "ref": demand_ref,
            "digest": demand_digest,
            "workRequestRef": demand["workRequestRef"],
            "workRequestDigest": demand["workRequestDigest"],
        },
        "candidateBinding": {"ref": candidate_ref, "digest": candidate_digest},
        "retryOf": retry_of,
    }
    target_refs = sorted(f"{row['entityType'].strip('/')}/{row['name'].strip()}" for row in targets)
    target_set: dict[str, Any] = {
        "executionId": execution_id,
        "selectionPolicy": "frozen",
        "sourceRef": str(bindings["sourceRef"]),
        "candidateBinding": {"ref": candidate_ref, "digest": candidate_digest, "candidateCount": candidate_count},
        "entityCatalogDigest": str(bindings["entityCatalogDigest"]),
        "targetCount": candidate_count,
        "targetRefs": target_refs,
        "targets": targets,
    }
    target_digest = hashlib.sha256(_canonical_bytes(target_set)).hexdigest()
    manifest: dict[str, Any] = {
        "executionId": execution_id,
        "familyRef": {"ref": family_ref, "sha256": hashlib.sha256(family_path.read_bytes()).hexdigest()},
        "sourceDigest": demand["sourceDigest"],
        "executionBundle": demand["executionBundle"],
        "hostRuntime": "external_host_agent",
        "carrierDemand": request["carrierDemand"],
        "requestRef": REQUEST_REF,
        "targetSetRef": TARGET_SET_REF,
        "targetSetDigest": target_digest,
        "retryOf": retry_of,
    }
    assert_valid(request, "execution", "task_init_request", label=f"task init request:{execution_id}")
    assert_valid(target_set, "execution", "target_set", label=f"task init target set:{execution_id}")
    assert_valid(manifest, "execution", "content_execution_manifest", label=f"task init manifest:{execution_id}")
    documents = {"execution_manifest.json": manifest, REQUEST_REF: request, TARGET_SET_REF: target_set}
    target_root = paths.DATA_EXECUTIONS_ROOT / execution_id
    with _init_lock(execution_id):
        if target_root.exists():
            if _documents_match(target_root, documents):
                return {"executionId": execution_id, "status": "replayed", "artifacts": list(documents)}
            raise TaskInitError("executionId already exists with different bytes")
        staging = Path(tempfile.mkdtemp(prefix=f".{execution_id}.init-", dir=paths.DATA_EXECUTIONS_ROOT))
        try:
            for rel, value in documents.items():
                _write_stage_document(staging / rel, value)
            os.rename(staging, target_root)
            root_fd = os.open(paths.DATA_EXECUTIONS_ROOT, os.O_RDONLY)
            try:
                os.fsync(root_fd)
            finally:
                os.close(root_fd)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    return {"executionId": execution_id, "status": "created", "artifacts": list(documents)}


__all__ = ["TaskInitError", "initialize_task"]
