"""Pure path and immutable-input helpers for one execution work package."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from content.execution.identity import validate_execution_id
from core import paths as core_paths
from core.io import read_json, write_json
from core.schema import assert_valid

MANIFEST_FILENAME = "execution_manifest.json"
REQUEST_REF = "0.plan/request.json"
TARGET_SET_REF = "0.plan/target_set.json"
_TRANSACTION_OBJECT_MARKERS = ("--entity-", "--post-")


def transaction_workspace_root() -> Path:
    return core_paths.DATA_LOCAL_ROOT / "workspace" / "object-transactions"


def orphaned_transaction_workspaces() -> tuple[Path, ...]:
    root = transaction_workspace_root()
    if not root.is_dir():
        return ()
    orphaned: list[Path] = []
    for candidate in sorted(path for path in root.iterdir() if path.is_dir()):
        execution_id = next(
            (candidate.name.rsplit(marker, 1)[0] for marker in _TRANSACTION_OBJECT_MARKERS if marker in candidate.name),
            "",
        )
        if not execution_id:
            continue
        try:
            validate_execution_id(execution_id)
        except ValueError:
            continue
        if not execution_root(execution_id).is_dir():
            orphaned.append(candidate)
    return tuple(orphaned)


def execution_root(execution_id: str) -> Path:
    return core_paths.DATA_EXECUTIONS_ROOT / validate_execution_id(execution_id)


def execution_manifest_path(execution_id: str) -> Path:
    return execution_root(execution_id) / MANIFEST_FILENAME


def execution_request_path(execution_id: str) -> Path:
    return execution_root(execution_id) / REQUEST_REF


def execution_target_set_path(execution_id: str) -> Path:
    return execution_root(execution_id) / TARGET_SET_REF


def ensure_execution_work_package_layout(execution_id: str) -> Path:
    root = execution_root(execution_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def relative_execution_ref(target: Path, execution_id: str) -> str:
    root = execution_root(execution_id).resolve()
    candidate = Path(target).resolve()
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"path is outside execution root: {candidate}") from exc


def _json_object(path: Path, *, label: str) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return value


def load_frozen_target_set(execution_id: str) -> dict[str, Any]:
    path = execution_target_set_path(execution_id)
    if not path.is_file():
        raise FileNotFoundError(f"frozen target set does not exist: {path}")
    value = _json_object(path, label="target set")
    assert_valid(value, "execution", "target_set", label=f"target_set:{execution_id}")
    if value.get("executionId") != validate_execution_id(execution_id):
        raise ValueError(f"target set executionId mismatch: {path}")
    return value


def load_frozen_execution_manifest(execution_id: str) -> dict[str, Any]:
    path = execution_manifest_path(execution_id)
    if not path.is_file():
        raise FileNotFoundError(f"execution manifest does not exist: {path}")
    value = _json_object(path, label="execution manifest")
    assert_valid(value, "execution", "content_execution_manifest", label=f"execution_manifest:{execution_id}")
    if value.get("executionId") != validate_execution_id(execution_id):
        raise ValueError(f"execution manifest identity mismatch: {path}")
    target = value.get("targetSet")
    if not isinstance(target, Mapping):
        raise ValueError("execution manifest targetSet binding is required")
    target_set_path = execution_target_set_path(execution_id)
    expected = str(target.get("digest") or "")
    actual = "sha256:" + hashlib.sha256(target_set_path.read_bytes()).hexdigest()
    if expected != actual:
        raise ValueError(f"execution target set bytes drifted: {target_set_path}")
    return value


def load_execution_manifest(execution_id: str) -> dict[str, Any]:
    return load_frozen_execution_manifest(execution_id)


def frozen_target_by_name(execution_id: str, name: str) -> dict[str, Any] | None:
    expected = str(name or "").strip()
    if not expected:
        return None
    for target in load_frozen_target_set(execution_id).get("targets", []):
        if isinstance(target, Mapping) and str(target.get("name") or "").strip() == expected:
            return dict(target)
    return None


def entity_catalog_digest(source_ref: str) -> str:
    ref = PurePosixPath(str(source_ref or "").strip())
    if not ref.as_posix() or ref.is_absolute() or any(part in {"", ".", ".."} for part in ref.parts):
        raise ValueError("entity catalog sourceRef must be a safe repository-relative path")
    repo_root = core_paths.REPO_ROOT.resolve()
    source = (repo_root / ref.as_posix()).resolve()
    try:
        source.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError("entity catalog must be inside the repository") from exc
    if not source.exists():
        raise FileNotFoundError(f"entity catalog does not exist: {source}")
    files = (source,) if source.is_file() else tuple(path for path in sorted(source.rglob("*")) if path.is_file())
    if not files:
        raise ValueError(f"entity catalog is empty: {source}")
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(repo_root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _canonical_refs(refs: Iterable[str]) -> list[str]:
    normalized: set[str] = set()
    for raw in refs:
        value = str(raw or "").strip().strip("/")
        ref = PurePosixPath(value)
        if not value or ref.is_absolute() or any(part in {"", ".", ".."} for part in ref.parts):
            raise ValueError(f"unsafe canonical publish ref: {raw!r}")
        normalized.add(value)
    return sorted(normalized)


def write_publish_ref(
    execution_id: str,
    *,
    entity_refs: Iterable[str] = (),
    post_refs: Iterable[str] = (),
    publish_discards: Iterable[Mapping[str, Any]] = (),
) -> Path:
    discards = []
    for raw in publish_discards:
        object_ref = str(raw.get("objectRef") or "").strip()
        issues = sorted({str(issue).strip() for issue in raw.get("issues", []) if str(issue).strip()})
        if not object_ref or not issues:
            raise ValueError("publish discard requires objectRef and non-empty issues")
        discards.append({"objectRef": object_ref, "issues": issues})
    payload = {
        "schema": "quwoquan_data.execution_publish_ref",
        "executionId": validate_execution_id(execution_id),
        "canonicalPublishRoot": core_paths.CANONICAL_PUBLISH_ROOT_REF,
        "publishedRefs": {
            "entities": _canonical_refs(entity_refs),
            "posts": _canonical_refs(post_refs),
        },
        "publishDiscards": sorted(discards, key=lambda row: row["objectRef"]),
    }
    assert_valid(payload, "execution", "publish_ref", label=f"publish_ref:{execution_id}")
    target = execution_root(execution_id) / "publish_ref.json"
    write_json(target, payload)
    return target


__all__ = [
    "MANIFEST_FILENAME",
    "REQUEST_REF",
    "TARGET_SET_REF",
    "entity_catalog_digest",
    "ensure_execution_work_package_layout",
    "execution_manifest_path",
    "execution_request_path",
    "execution_root",
    "execution_target_set_path",
    "frozen_target_by_name",
    "load_execution_manifest",
    "load_frozen_execution_manifest",
    "load_frozen_target_set",
    "orphaned_transaction_workspaces",
    "relative_execution_ref",
    "transaction_workspace_root",
    "write_publish_ref",
]
