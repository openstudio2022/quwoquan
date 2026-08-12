"""Filesystem contract for one content execution work package."""
from __future__ import annotations

import hashlib
import json
import os
import yaml
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from core import paths as core_paths
from core.paths import WORKSPACE_ROOT_BY_COMMAND, normalize_execution_workspace_command
from core.io import read_json, write_json
from core.source_digest import (
    ExecutionBundleIdentity,
    SourceDefinitionSnapshot,
    SourceDigestError,
    current_execution_bundle_identity,
    current_source_definition_snapshot,
)
from content.source.contracts import QualifiedHomepageSource

from .identity import SelectionPolicy, parse_execution_id, validate_execution_id


MANIFEST_FILENAME = "execution_manifest.json"
REQUEST_REF = "0.plan/request.json"
TARGET_SET_REF = "0.plan/target_set.json"
WORK_PACKAGE_DIRECTORIES = (
    "0.plan",
    "sources",
    "entities",
    "posts",
    "_shared",
    "evidence",
)
_TRANSACTION_OBJECT_MARKERS = ("--entity-", "--post-")
class ExecutionSourceDigestDriftError(ValueError):
    """The immutable execution was created from different repository inputs."""


def transaction_workspace_root() -> Path:
    return core_paths.DATA_LOCAL_ROOT / "workspace" / "object-transactions"
def frozen_target_archive_path(execution_id: str) -> Path:
    archive_root = core_paths.DATA_LOCAL_ROOT / "workspace" / "frozen-target-sets"
    return archive_root / f"{validate_execution_id(execution_id)}.json"


def orphaned_transaction_workspaces() -> tuple[Path, ...]:
    """Return transaction evidence whose execution work package no longer exists."""
    root = transaction_workspace_root()
    if not root.is_dir():
        return ()
    orphaned: list[Path] = []
    for candidate in sorted(path for path in root.iterdir() if path.is_dir()):
        execution_id = ""
        for marker in _TRANSACTION_OBJECT_MARKERS:
            if marker in candidate.name:
                execution_id = candidate.name.rsplit(marker, 1)[0]
                break
        if not execution_id:
            continue
        try:
            validate_execution_id(execution_id)
        except ValueError:
            continue
        if not (core_paths.DATA_EXECUTIONS_ROOT / execution_id).is_dir():
            orphaned.append(candidate)
    return tuple(orphaned)


def require_clean_transaction_workspace(execution_id: str) -> None:
    """Reject a new execution ID that is shadowed by deleted output evidence."""
    normalized = validate_execution_id(execution_id)
    prefix = f"{normalized}--"
    stale = [
        path for path in orphaned_transaction_workspaces()
        if path.name.startswith(prefix)
    ]
    if stale:
        raise ValueError(
            "execution output reset is incomplete; remove stale transaction workspace: "
            + ", ".join(path.as_posix() for path in stale)
        )


def execution_root(execution_id: str) -> Path:
    """Resolve the only execution work-package root through ``core.paths``."""
    return core_paths.execution_root(validate_execution_id(execution_id))


def execution_manifest_path(execution_id: str) -> Path:
    return execution_root(execution_id) / MANIFEST_FILENAME
def execution_target_set_path(execution_id: str) -> Path:
    return execution_root(execution_id) / TARGET_SET_REF


def execution_request_path(execution_id: str) -> Path:
    return execution_root(execution_id) / REQUEST_REF


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
    def execution_state_path(self) -> Path:
        return self.shared_dir / "execution_state.json"

    def command_packet_path(self, stage: str) -> Path:
        return self.shared_dir / "command_packets" / f"{stage}.json"


@dataclass(frozen=True, slots=True)
class FrozenTarget:
    """A target admitted from the immutable execution target set."""

    name: str
    entity_type: str
    qualified_homepage_source: QualifiedHomepageSource | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "FrozenTarget":
        name = str(payload.get("name") or "").strip()
        entity_type = str(payload.get("entityType") or "").strip().strip("/")
        if not name or len(entity_type.split("/")) != 2:
            raise ValueError(f"invalid frozen target: {dict(payload)!r}")
        raw_source = payload.get("qualifiedHomepageSource")
        if raw_source is not None and not isinstance(raw_source, Mapping):
            raise TypeError("frozen target qualifiedHomepageSource must be an object")
        return cls(
            name=name,
            entity_type=entity_type,
            qualified_homepage_source=(
                QualifiedHomepageSource.from_mapping(raw_source)
                if isinstance(raw_source, Mapping)
                else None
            ),
        )


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


def execution_state_path(execution_id: str) -> Path:
    return ExecutionWorkspace(execution_id).execution_state_path


def execution_command_packet_path(execution_id: str, stage: str) -> Path:
    return ExecutionWorkspace(execution_id).command_packet_path(stage)


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


def entity_catalog_digest(source_ref: str) -> str:
    """Fingerprint one reusable entity catalog without execution-local identity.

    Carrier executions may select different candidates, but a coordinated run
    must prove that all selectors observed the same version-controlled catalog.
    """
    normalized = str(source_ref or "").strip().strip("/")
    if not normalized:
        raise ValueError("entity catalog sourceRef is required")
    root = (core_paths.REPO_ROOT / normalized).resolve()
    repo_root = core_paths.REPO_ROOT.resolve()
    try:
        root.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError("entity catalog must be inside the repository") from exc
    if not root.exists():
        raise FileNotFoundError(f"entity catalog does not exist: {root}")
    files = (root,) if root.is_file() else tuple(
        path for path in sorted(root.rglob("*")) if path.is_file()
    )
    if not files:
        raise ValueError(f"entity catalog is empty: {root}")
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(repo_root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


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
        "executionId": validate_execution_id(execution_id),
        "selectionPolicy": SelectionPolicy.FROZEN.value,
        "sourceRef": str(source_ref).strip(),
        "entityCatalogDigest": entity_catalog_digest(source_ref),
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
        path = frozen_target_archive_path(execution_id)
    if not path.is_file():
        raise FileNotFoundError(
            f"frozen target set and retry archive do not exist: {execution_id}"
        )
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"frozen target set is not an object: {path}")
    from core.schema import assert_valid

    assert_valid(payload, "execution", "target_set", label=f"target_set:{execution_id}")
    return payload


def archive_frozen_target_set(execution_id: str) -> Path:
    """Create-once archive needed to retry after task output cleanup."""
    normalized = validate_execution_id(execution_id)
    source = execution_target_set_path(normalized)
    if not source.is_file():
        raise FileNotFoundError(f"frozen target set does not exist: {source}")
    payload = read_json(source)
    if not isinstance(payload, dict):
        raise ValueError(f"frozen target set is not an object: {source}")
    from core.schema import assert_valid

    assert_valid(payload, "execution", "target_set", label=f"target_set:{normalized}")
    destination = frozen_target_archive_path(normalized)
    if destination.is_file():
        if read_json(destination) != payload:
            raise ValueError(
                f"frozen target retry archive drift detected: {normalized}"
            )
    else:
        write_json(destination, payload)
    return destination


def frozen_target_by_name(execution_id: str, name: str) -> FrozenTarget | None:
    """Resolve one target from the only immutable target-set source."""
    expected_name = str(name or "").strip()
    if not expected_name:
        return None
    payload = load_frozen_target_set(execution_id)
    targets = payload.get("targets")
    if not isinstance(targets, list):
        raise ValueError(f"frozen target set targets must be an array: {execution_id}")
    for raw_target in targets:
        if not isinstance(raw_target, Mapping):
            raise ValueError(f"frozen target set contains a non-object target: {execution_id}")
        target = FrozenTarget.from_mapping(raw_target)
        if target.name == expected_name:
            return target
    return None


def frozen_target_set_digest(execution_id: str) -> str:
    return _canonical_payload_sha256(load_frozen_target_set(execution_id))


def create_execution_manifest(
    *,
    execution_id: str,
    recipe_ref: str,
    request: dict[str, Any],
    selection_policy: SelectionPolicy,
    target_set_ref: str,
    target_set_digest: str,
    retry_of: str | None = None,
    semantic_selection_id: str = "default",
    semantic_preflight_binding: Mapping[str, Any] | None = None,
    semantic_preflight_require_fresh: bool = True,
) -> dict[str, Any]:
    """Create exactly one immutable execution manifest and work-package tree.

    Reusing an existing ID is a resume only when its immutable inputs match.
    A new attempt must receive a new sequence and point at ``retryOf``.
    """
    identity = parse_execution_id(execution_id)
    root = execution_root(identity.execution_id)
    manifest_path = root / MANIFEST_FILENAME
    recipe_file = core_paths.recipe_path(recipe_ref)
    if not isinstance(selection_policy, SelectionPolicy):
        raise TypeError("selection_policy must be SelectionPolicy")
    if target_set_ref != TARGET_SET_REF:
        raise ValueError(f"targetSetRef must be {TARGET_SET_REF}")
    actual_target_set_digest = frozen_target_set_digest(identity.execution_id)
    if target_set_digest != actual_target_set_digest:
        raise ValueError("targetSetDigest does not match the frozen target set")
    normalized_retry_of = validate_execution_id(retry_of) if retry_of else None
    if normalized_retry_of:
        retry_identity = parse_execution_id(normalized_retry_of)
        comparable = (
            "vertical",
            "content_type",
            "intent",
            "scope",
            "phase",
        )
        if normalized_retry_of == identity.execution_id or any(
            getattr(retry_identity, field) != getattr(identity, field) for field in comparable
        ):
            raise ValueError("retryOf must reference an earlier sequence of the same execution scope")
        if retry_identity.sequence >= identity.sequence:
            raise ValueError("retryOf sequence must be lower than the new execution sequence")

    existing_manifest = (
        load_execution_manifest(identity.execution_id)
        if manifest_path.is_file()
        else None
    )
    from content.execution.planning.semantic_preflight_admission import (
        resolve_manifest_preflight_binding,
    )

    normalized_preflight_binding = resolve_manifest_preflight_binding(
        existing_manifest=existing_manifest,
        requested_binding=semantic_preflight_binding,
        semantic_selection_id=semantic_selection_id,
        output_root=core_paths.OUTPUT_ROOT,
        require_requested_fresh=(
            semantic_preflight_require_fresh and existing_manifest is None
        ),
    )
    if existing_manifest is not None:
        # A v2 work package is its own immutable execution authority.  Resume
        # must not rebuild either identity from the changing checkout: source
        # definitions and the executor bundle were frozen at first creation.
        # The exact request/target/preflight/family lineage is still checked
        # below, so this does not turn resume into a compatibility path.
        family_ref = existing_manifest.get("familyRef")
        if not isinstance(family_ref, Mapping) or family_ref.get("ref") != recipe_ref:
            raise ValueError("execution manifest familyRef drift")
        if existing_manifest.get("semanticSelectionId") != semantic_selection_id:
            raise ValueError("execution manifest semanticSelectionId drift")
        if existing_manifest.get("retryOf") != normalized_retry_of:
            raise ValueError("execution manifest retryOf drift")
        if existing_manifest.get("targetSetRef") != target_set_ref:
            raise ValueError("execution manifest targetSetRef drift")
        if existing_manifest.get("targetSetDigest") != target_set_digest:
            raise ValueError("execution manifest targetSetDigest drift")
        if existing_manifest.get("semanticPreflightReceipt") != normalized_preflight_binding:
            raise ValueError("execution manifest semantic preflight binding drift")
        request_path = execution_request_path(identity.execution_id)
        if not request_path.is_file() or read_json(request_path) != request:
            raise ValueError("execution request is immutable; create a new sequence")
        return existing_manifest

    if not recipe_file.is_file():
        raise FileNotFoundError(f"recipeRef does not exist: {recipe_ref}")
    recipe_payload = yaml.safe_load(recipe_file.read_text(encoding="utf-8"))
    if not isinstance(recipe_payload, dict):
        raise ValueError(f"recipe must be an object: {recipe_file}")
    from content.execution.planning.semantic_selection import semantic_manifest_identity

    semantic_identity = semantic_manifest_identity(
        recipe_payload,
        semantic_selection_id=semantic_selection_id,
        retry_of=normalized_retry_of,
    )
    source_identity = current_source_definition_snapshot().to_document()
    execution_bundle_identity = current_execution_bundle_identity().to_document()
    candidate = {
        "executionId": identity.execution_id,
        "familyRef": {"ref": recipe_ref, "sha256": _file_sha256(recipe_file)},
        "sourceDigest": source_identity,
        "executionBundle": execution_bundle_identity,
        **semantic_identity,
        "requestRef": REQUEST_REF,
        "targetSetRef": target_set_ref,
        "targetSetDigest": target_set_digest,
        "retryOf": normalized_retry_of,
    }
    if normalized_preflight_binding is not None:
        candidate["semanticPreflightReceipt"] = normalized_preflight_binding
    ensure_execution_work_package_layout(identity.execution_id)
    request_path = execution_request_path(identity.execution_id)
    if request_path.is_file():
        existing_request = read_json(request_path)
        if existing_request != request:
            raise ValueError("execution request is immutable; create a new sequence")
    else:
        write_json(request_path, request)
    from core.schema import assert_valid

    assert_valid(candidate, "execution", "content_execution_manifest", label=f"execution_manifest:{identity.execution_id}")
    write_json(manifest_path, candidate)
    return candidate


def load_frozen_execution_manifest(execution_id: str) -> dict[str, Any]:
    """Load immutable execution evidence without comparing it to today's source tree."""
    manifest_path = execution_manifest_path(execution_id)
    if not manifest_path.is_file():
        raise FileNotFoundError(f"execution manifest does not exist: {manifest_path}")
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError(f"execution manifest is not an object: {manifest_path}")
    if manifest.get("executionId") != validate_execution_id(execution_id):
        raise ValueError(f"execution manifest identity mismatch: {manifest_path}")
    from content.execution.execution_terminal import load_terminal_execution_evidence
    from core.schema import assert_valid

    legacy = "executionBundle" not in manifest
    if legacy:
        terminal = load_terminal_execution_evidence(manifest_path.parent)
        if terminal is None:
            raise ExecutionSourceDigestDriftError(
                "GATE_BLOCK DATA.EXECUTION.SOURCE_IDENTITY_MIGRATION_REQUIRED: "
                "legacy nonterminal execution cannot resume"
            )
        if manifest.get("executionId") != validate_execution_id(execution_id):
            raise ValueError(f"execution manifest identity mismatch: {manifest_path}")
        return manifest
    assert_valid(manifest, "execution", "content_execution_manifest", label=f"execution_manifest:{execution_id}")
    try:
        SourceDefinitionSnapshot.from_document(manifest.get("sourceDigest"))
        ExecutionBundleIdentity.from_document(manifest.get("executionBundle"))
    except SourceDigestError as exc:
        raise ValueError(f"execution manifest sourceDigest invalid: {exc}") from exc
    if manifest.get("targetSetDigest") != frozen_target_set_digest(execution_id):
        raise ValueError(f"execution manifest target set digest mismatch: {manifest_path}")
    return manifest


def load_execution_manifest(execution_id: str) -> dict[str, Any]:
    """Load a resumable execution and require its repository inputs to be unchanged."""
    manifest = load_frozen_execution_manifest(execution_id)
    if "executionBundle" not in manifest:
        raise ExecutionSourceDigestDriftError(
            "GATE_BLOCK DATA.EXECUTION.SOURCE_IDENTITY_MIGRATION_REQUIRED: "
            "legacy terminal execution is read-only"
        )
    SourceDefinitionSnapshot.from_document(manifest.get("sourceDigest"))
    ExecutionBundleIdentity.from_document(manifest.get("executionBundle"))
    return manifest


def execution_manifest_recipe_ref(execution_id: str) -> str:
    """Return the sole recipe reference from the immutable manifest."""
    manifest = load_execution_manifest(execution_id)
    family_ref = manifest.get("familyRef")
    if not isinstance(family_ref, dict):
        raise ValueError("execution manifest familyRef must be an object")
    recipe_ref = str(family_ref.get("ref") or "").strip()
    if not recipe_ref:
        raise ValueError("execution manifest recipe.ref is required")
    return recipe_ref


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
    payload = {
        "schema": "quwoquan_data.execution_publish_ref",
        "executionId": validate_execution_id(execution_id),
        "canonicalPublishRoot": "quwoquan_data/publish",
        "publishedRefs": {
            "entities": _canonical_object_refs(entity_refs, kind="entities"),
            "posts": _canonical_object_refs(post_refs, kind="posts"),
        },
    }
    from core.schema import assert_valid

    assert_valid(payload, "execution", "publish_ref", label=f"publish_ref:{execution_id}")
    write_json(target, payload)
    return target
