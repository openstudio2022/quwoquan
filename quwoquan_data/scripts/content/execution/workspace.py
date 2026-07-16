"""Filesystem contract for one content execution work package."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from core import paths as core_paths
from core.paths import WORKSPACE_ROOT_BY_COMMAND, normalize_execution_workspace_command
from core.io import read_json, write_json

from .identity import SelectionPolicy, parse_execution_id, validate_execution_id


MANIFEST_FILENAME = "execution_manifest.json"
TARGET_SET_REF = "0.plan/target_set.json"
WORK_PACKAGE_DIRECTORIES = (
    "0.plan",
    "sources",
    "entities",
    "posts",
    "_shared",
    "evidence",
)
def execution_root(execution_id: str) -> Path:
    """Resolve the only execution work-package root through ``core.paths``."""
    return core_paths.execution_root(validate_execution_id(execution_id))


def execution_manifest_path(execution_id: str) -> Path:
    return execution_root(execution_id) / MANIFEST_FILENAME


def execution_target_set_path(execution_id: str) -> Path:
    return execution_root(execution_id) / TARGET_SET_REF


@dataclass(frozen=True, slots=True)
class ExecutionWorkspace:
    """The sole runtime address for one immutable execution work package."""

    execution_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "execution_id", validate_execution_id(self.execution_id))

    @property
    def root(self) -> Path:
        return execution_root(self.execution_id)

    @property
    def shared_dir(self) -> Path:
        return self.root / "_shared"

    def command_root(self, command: str) -> Path:
        normalized = normalize_execution_workspace_command(command)
        return self.shared_dir / "workspace" / WORKSPACE_ROOT_BY_COMMAND[normalized]

    @property
    def workflow_state_path(self) -> Path:
        return self.shared_dir / "workflow_state.json"

    def workflow_packet_path(self, stage: str) -> Path:
        return self.shared_dir / "workflow_packets" / f"{stage}.json"


def execution_command_root(execution_id: str, command: str) -> Path:
    return ExecutionWorkspace(execution_id).command_root(command)


def execution_content_plan_packet_path(execution_id: str) -> Path:
    return ExecutionWorkspace(execution_id).shared_dir / "content_plan_packet.json"


def execution_catalog_path(execution_id: str) -> Path:
    return ExecutionWorkspace(execution_id).shared_dir / "catalog.ndjson"


def execution_explore_packet_path(execution_id: str) -> Path:
    return ExecutionWorkspace(execution_id).shared_dir / "explore_packet.json"


def execution_baseline_freeze_packet_path(execution_id: str) -> Path:
    return ExecutionWorkspace(execution_id).shared_dir / "baseline_freeze_packet.json"


def execution_shared_path(execution_id: str, filename: str) -> Path:
    return ExecutionWorkspace(execution_id).shared_dir / filename


def ensure_execution_work_package_layout(execution_id: str) -> Path:
    workspace = ExecutionWorkspace(execution_id)
    workspace.root.mkdir(parents=True, exist_ok=True)
    for directory in WORK_PACKAGE_DIRECTORIES:
        (workspace.root / directory).mkdir(exist_ok=True)
    return workspace.root


def ensure_execution_command_layout(execution_id: str, command: str) -> Path:
    root = execution_command_root(execution_id, command)
    for child in ("inputs", "results", "assistant_tasks"):
        (root / child).mkdir(parents=True, exist_ok=True)
    return root


def relative_execution_ref(target: Path, execution_id: str) -> str:
    return os.path.relpath(Path(target).resolve(), execution_root(execution_id).resolve()).replace(os.sep, "/")


def execution_id_from_spec_path(path: Path) -> str:
    candidate = path.parent.parent.name if path.name == "execution_spec.yaml" else path.parent.name
    return validate_execution_id(candidate)


def execution_progress_path(execution_id: str) -> Path:
    return ExecutionWorkspace(execution_id).shared_dir / "execution_progress.json"


def execution_runs_dir(execution_id: str) -> Path:
    return execution_root(execution_id) / "evidence" / "runs"


def execution_notes_path(execution_id: str) -> Path:
    return execution_root(execution_id) / "0.plan" / "operator_notes.md"


def execution_workflow_state_path(execution_id: str) -> Path:
    return ExecutionWorkspace(execution_id).workflow_state_path


def execution_workflow_packet_path(execution_id: str, stage: str) -> Path:
    return ExecutionWorkspace(execution_id).workflow_packet_path(stage)


def iter_execution_specs() -> list[Path]:
    if not core_paths.DATA_EXECUTIONS_ROOT.is_dir():
        return []
    return sorted(core_paths.DATA_EXECUTIONS_ROOT.glob("*/0.plan/execution_spec.yaml"))


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_payload_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_frozen_target_set(
    execution_id: str,
    *,
    targets: Iterable[dict[str, Any]],
    source_ref: str,
) -> tuple[Path, str]:
    """Freeze the exact execution target set before an execution manifest exists."""
    normalized: list[dict[str, Any]] = []
    refs: set[str] = set()
    for raw in targets:
        target = dict(raw)
        name = str(target.get("name") or "").strip()
        entity_type = str(target.get("entityType") or "").strip().strip("/")
        if not name or len(entity_type.split("/")) != 2:
            raise ValueError(f"invalid frozen target: {raw}")
        ref = f"{entity_type}/{name}"
        if ref in refs:
            raise ValueError(f"duplicate frozen target: {ref}")
        refs.add(ref)
        normalized.append(target)
    if not normalized:
        raise ValueError("frozen target set must not be empty")
    payload = {
        "contractVersion": "content-target-set-v1",
        "executionId": validate_execution_id(execution_id),
        "selectionPolicy": SelectionPolicy.FROZEN.value,
        "sourceRef": str(source_ref).strip(),
        "targetCount": len(normalized),
        "targetRefs": sorted(refs),
        "targets": normalized,
    }
    from core.schema import assert_valid

    assert_valid(payload, "execution", "target_set", label=f"target_set:{execution_id}")
    digest = _canonical_payload_sha256(payload)
    path = execution_target_set_path(execution_id)
    if path.is_file():
        existing = read_json(path)
        if existing != payload:
            raise ValueError(
                f"executionId {execution_id} already has a different frozen target set"
            )
    else:
        write_json(path, payload)
    return path, digest


def load_frozen_target_set(execution_id: str) -> dict[str, Any]:
    path = execution_target_set_path(execution_id)
    if not path.is_file():
        raise FileNotFoundError(f"frozen target set does not exist: {path}")
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"frozen target set is not an object: {path}")
    from core.schema import assert_valid

    assert_valid(payload, "execution", "target_set", label=f"target_set:{execution_id}")
    return payload


def frozen_target_set_sha256(execution_id: str) -> str:
    return _canonical_payload_sha256(load_frozen_target_set(execution_id))


def create_execution_manifest(
    *,
    execution_id: str,
    recipe_ref: str,
    resolved_params: dict[str, Any],
    selection_policy: SelectionPolicy,
    target_set_ref: str,
    target_set_sha256: str,
    retry_of: str | None = None,
) -> dict[str, Any]:
    """Create exactly one immutable execution manifest and work-package tree.

    Reusing an existing ID is a resume only when its immutable inputs match.
    A new attempt must receive a new sequence and point at ``retryOf``.
    """
    identity = parse_execution_id(execution_id)
    root = execution_root(identity.execution_id)
    manifest_path = root / MANIFEST_FILENAME
    recipe_file = core_paths.recipe_path(recipe_ref)
    if not recipe_file.is_file():
        raise FileNotFoundError(f"recipeRef does not exist: {recipe_ref}")
    if not isinstance(selection_policy, SelectionPolicy):
        raise TypeError("selection_policy must be SelectionPolicy")
    if target_set_ref != TARGET_SET_REF:
        raise ValueError(f"targetSetRef must be {TARGET_SET_REF}")
    actual_target_set_sha256 = frozen_target_set_sha256(identity.execution_id)
    if target_set_sha256 != actual_target_set_sha256:
        raise ValueError("targetSetSha256 does not match the frozen target set")
    normalized_retry_of = validate_execution_id(retry_of) if retry_of else None
    if normalized_retry_of:
        retry_identity = parse_execution_id(normalized_retry_of)
        comparable = (
            "vertical",
            "content_type",
            "intent",
            "scope",
            "milestone",
        )
        if normalized_retry_of == identity.execution_id or any(
            getattr(retry_identity, field) != getattr(identity, field) for field in comparable
        ):
            raise ValueError("retryOf must reference an earlier sequence of the same execution scope")
        if retry_identity.sequence >= identity.sequence:
            raise ValueError("retryOf sequence must be lower than the new execution sequence")

    candidate = {
        "contractVersion": "content-execution-v2",
        "executionId": identity.execution_id,
        "vertical": identity.vertical,
        "contentType": identity.content_type,
        "intent": identity.intent,
        "scope": identity.scope,
        "milestone": identity.milestone,
        "sequence": identity.sequence,
        "recipe": {"ref": recipe_ref, "sha256": _file_sha256(recipe_file)},
        "resolvedParams": resolved_params,
        "selectionPolicy": selection_policy.value,
        "targetSetRef": target_set_ref,
        "targetSetSha256": target_set_sha256,
        "retryOf": normalized_retry_of,
        "createdAt": _utc_now(),
        "repoRoot": str(core_paths.REPO_ROOT),
    }
    if manifest_path.is_file():
        existing = load_execution_manifest(identity.execution_id)
        immutable_keys = (
            "contractVersion",
            "executionId",
            "vertical",
            "contentType",
            "intent",
            "scope",
            "milestone",
            "sequence",
            "recipe",
            "resolvedParams",
            "selectionPolicy",
            "targetSetRef",
            "targetSetSha256",
            "retryOf",
        )
        drift = [key for key in immutable_keys if existing.get(key) != candidate.get(key)]
        if drift:
            raise ValueError(
                f"executionId {identity.execution_id} already exists with different "
                f"immutable fields: {', '.join(drift)}; create a new sequence and retryOf"
            )
        return existing

    ensure_execution_work_package_layout(identity.execution_id)
    from core.schema import assert_valid

    assert_valid(candidate, "execution", "content_execution_manifest", label=f"execution_manifest:{identity.execution_id}")
    write_json(manifest_path, candidate)
    return candidate


def load_execution_manifest(execution_id: str) -> dict[str, Any]:
    manifest_path = execution_manifest_path(execution_id)
    if not manifest_path.is_file():
        raise FileNotFoundError(f"execution manifest does not exist: {manifest_path}")
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError(f"execution manifest is not an object: {manifest_path}")
    if manifest.get("executionId") != validate_execution_id(execution_id):
        raise ValueError(f"execution manifest identity mismatch: {manifest_path}")
    from core.schema import assert_valid

    assert_valid(manifest, "execution", "content_execution_manifest", label=f"execution_manifest:{execution_id}")
    if manifest.get("targetSetSha256") != frozen_target_set_sha256(execution_id):
        raise ValueError(f"execution manifest target set digest mismatch: {manifest_path}")
    return manifest


def _canonical_object_refs(refs: Iterable[str], *, kind: str) -> list[str]:
    singular = {"entities": "entity", "posts": "post"}.get(kind)
    if singular is None:
        raise ValueError(f"unsupported canonical object kind: {kind}")
    prefix = f"/{singular}/"
    normalized: set[str] = set()
    for raw in refs:
        ref = str(raw or "").strip().strip("/")
        if raw and str(raw).startswith(prefix):
            ref = str(raw)[len(prefix):].strip("/")
        candidate = Path(ref)
        if not ref or candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError(f"unsafe canonical {kind} ref: {raw}")
        normalized.add(ref)
    return sorted(normalized)


def write_publish_ref(
    execution_id: str,
    *,
    entity_refs: Iterable[str] = (),
    post_refs: Iterable[str] = (),
) -> Path:
    """Record this execution's canonical object closure, never a release alias."""
    target = execution_root(execution_id) / "publish_ref.json"
    write_json(
        target,
        {
            "schemaVersion": "quwoquan_data.execution_publish_ref/1",
            "executionId": validate_execution_id(execution_id),
            "canonicalPublishRoot": "quwoquan_data/publish",
            "publishedRefs": {
                "entities": _canonical_object_refs(entity_refs, kind="entities"),
                "posts": _canonical_object_refs(post_refs, kind="posts"),
            },
        },
    )
    return target
