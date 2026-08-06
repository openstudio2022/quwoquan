"""Create-once evidence for taking ownership of a shared Data workstream.

The receipt snapshots only repository state and explicitly protected runtime
evidence.  It is diagnostic evidence under ``data/local/cache``; it never
becomes a second source of truth for executions or releases.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from content.execution.workspace import entity_catalog_digest
from core.paths import DATA_LOCAL_ROOT, REPO_ROOT
from core.schema import assert_valid
from core.source_digest import content_source_revision, current_source_digest


SCHEMA = "quwoquan_data.data_workstream_baseline"
DEFAULT_SCOPES = (
    "quwoquan_data",
    "specs/feature-tree/discovery-content/object-homepage-coverage-scaling",
)
_TODO_ID = re.compile(r"^\s*-\s+id:\s+([^\s#]+)\s*$")
_TODO_STATUS = re.compile(r"^\s+status:\s+([^\s#]+)\s*$")


class WorkstreamBaselineError(ValueError):
    """The requested baseline cannot be represented without guessing."""


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_digest(value: object) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _repo_relative(path: Path, *, repo_root: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise WorkstreamBaselineError(
            f"baseline path must be inside repository: {resolved}"
        ) from exc


def _git(repo_root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise WorkstreamBaselineError(f"git {' '.join(args)} failed: {detail}") from exc
    # Porcelain status uses a leading space as part of the two-column status;
    # trimming the left edge would corrupt both the status and the path.
    return result.stdout.rstrip("\n")


def _status_entries(repo_root: Path, scopes: tuple[str, ...]) -> tuple[dict[str, object], ...]:
    output = _git(
        repo_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        *scopes,
    )
    entries: list[dict[str, object]] = []
    for raw_line in output.splitlines():
        if len(raw_line) < 4:
            continue
        status = raw_line[:2]
        rendered = raw_line[3:]
        if " -> " in rendered:
            rendered = rendered.rsplit(" -> ", 1)[1]
        if rendered.startswith('"'):
            raise WorkstreamBaselineError(
                "quoted git status path is unsupported; rename the path before baseline"
            )
        path = repo_root / rendered
        digest = _sha256_bytes(path.read_bytes()) if path.is_file() else None
        entries.append(
            {
                "path": rendered,
                "status": status,
                "fileSha256": digest,
            }
        )
    return tuple(sorted(entries, key=lambda item: str(item["path"])))


def _parse_owner_rules(values: Iterable[str]) -> tuple[tuple[str, str], ...]:
    rules: list[tuple[str, str]] = []
    for value in values:
        prefix, separator, owner = str(value).partition("=")
        prefix = prefix.strip().strip("/")
        owner = owner.strip()
        if not separator or not prefix or not owner:
            raise WorkstreamBaselineError(
                f"owner rule must be <repo-prefix>=<owner>: {value!r}"
            )
        rules.append((prefix, owner))
    if not rules:
        raise WorkstreamBaselineError("at least one owner rule is required")
    return tuple(sorted(rules, key=lambda item: (-len(item[0]), item[0], item[1])))


def _bind_owners(
    entries: tuple[dict[str, object], ...],
    rules: tuple[tuple[str, str], ...],
) -> tuple[dict[str, object], ...]:
    bound: list[dict[str, object]] = []
    for entry in entries:
        path = str(entry["path"])
        owner = next(
            (
                candidate_owner
                for prefix, candidate_owner in rules
                if path == prefix or path.startswith(prefix + "/")
            ),
            "",
        )
        if not owner:
            raise WorkstreamBaselineError(f"dirty path has no owner rule: {path}")
        bound.append({**entry, "owner": owner})
    return tuple(bound)


def _protected_evidence(path: Path, *, repo_root: Path) -> dict[str, object]:
    relative = _repo_relative(path, repo_root=repo_root)
    resolved = repo_root / relative
    if not resolved.exists():
        raise WorkstreamBaselineError(f"protected evidence is missing: {relative}")
    files = (resolved,) if resolved.is_file() else tuple(
        child for child in sorted(resolved.rglob("*")) if child.is_file()
    )
    if not files:
        raise WorkstreamBaselineError(f"protected evidence is empty: {relative}")
    digest = hashlib.sha256()
    byte_count = 0
    for child in files:
        child_relative = child.relative_to(repo_root).as_posix()
        body = child.read_bytes()
        byte_count += len(body)
        digest.update(child_relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(body).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return {
        "path": relative,
        "kind": "file" if resolved.is_file() else "directory",
        "fileCount": len(files),
        "byteCount": byte_count,
        "digest": "sha256:" + digest.hexdigest(),
    }


def _cursor_plan(path: Path) -> dict[str, object]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise WorkstreamBaselineError(f"Cursor plan is missing: {resolved}")
    body = resolved.read_bytes()
    task_ids: list[str] = []
    task_statuses: list[str] = []
    for line in body.decode("utf-8").splitlines():
        id_match = _TODO_ID.match(line)
        if id_match:
            task_ids.append(id_match.group(1))
            continue
        status_match = _TODO_STATUS.match(line)
        if status_match:
            task_statuses.append(status_match.group(1))
    if len(task_statuses) != len(task_ids):
        raise WorkstreamBaselineError(
            "Cursor plan todo IDs and statuses do not form a complete one-to-one list"
        )
    return {
        "path": resolved.as_posix(),
        "fileSha256": _sha256_bytes(body),
        "taskCount": len(task_ids),
        "pendingTaskCount": sum(status == "pending" for status in task_statuses),
        "taskIds": task_ids,
    }


def _write_create_once(path: Path, payload: Mapping[str, object]) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(existing, dict) or existing.get("baselineDigest") != payload.get(
            "baselineDigest"
        ):
            raise WorkstreamBaselineError(f"baseline create-once conflict: {path}")
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())


def create_data_workstream_baseline(
    *,
    entity_catalog_ref: str,
    cursor_plan_path: Path,
    protected_paths: Iterable[Path],
    owner_rules: Iterable[str],
    scopes: Iterable[str] = DEFAULT_SCOPES,
    repo_root: Path = REPO_ROOT,
    output_root: Path | None = None,
    freeze_reason: str = "WAIT_CONTENT/GATE_BLOCK",
) -> tuple[dict[str, object], Path]:
    normalized_scopes = tuple(sorted({str(value).strip().strip("/") for value in scopes if str(value).strip()}))
    if not normalized_scopes:
        raise WorkstreamBaselineError("at least one repository scope is required")
    protected = tuple(
        sorted(
            (_protected_evidence(path, repo_root=repo_root) for path in protected_paths),
            key=lambda item: str(item["path"]),
        )
    )
    if not protected:
        raise WorkstreamBaselineError("at least one protected evidence path is required")
    entries = _bind_owners(
        _status_entries(repo_root, normalized_scopes),
        _parse_owner_rules(owner_rules),
    )
    source_digest = current_source_digest(repo_root=repo_root).digest
    catalog_digest = entity_catalog_digest(entity_catalog_ref)
    source_revision = content_source_revision(
        source_digest=source_digest,
        entity_catalog_digest=catalog_digest,
    )
    cursor_plan = _cursor_plan(cursor_plan_path)
    runtime_freeze = {
        "campaignAllowed": False,
        "releaseAllowed": False,
        "stackctlAllowed": False,
        "reason": str(freeze_reason).strip() or "WAIT_CONTENT/GATE_BLOCK",
    }
    worktree_digest = _canonical_digest(entries)
    protected_digest = _canonical_digest(protected)
    ownership_digest = _canonical_digest(
        tuple({"path": entry["path"], "owner": entry["owner"]} for entry in entries)
    )
    stable = {
        "branch": _git(repo_root, "branch", "--show-current"),
        "headRevision": _git(repo_root, "rev-parse", "HEAD"),
        "scopes": list(normalized_scopes),
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogRef": entity_catalog_ref,
        "entityCatalogDigest": catalog_digest,
        "worktreeStatusDigest": worktree_digest,
        "protectedEvidenceManifestDigest": protected_digest,
        "fileOwnershipManifestDigest": ownership_digest,
        "worktreeEntries": list(entries),
        "protectedEvidence": list(protected),
        "cursorPlan": cursor_plan,
        "runtimeFreeze": runtime_freeze,
    }
    baseline_digest = _canonical_digest(stable)
    payload: dict[str, object] = {
        "schema": SCHEMA,
        "recordedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        **stable,
        "baselineDigest": baseline_digest,
    }
    assert_valid(payload, "governance", "data_workstream_baseline", label=SCHEMA)
    root = output_root or (DATA_LOCAL_ROOT / "cache" / "workstream-baselines")
    destination = root / baseline_digest.removeprefix("sha256:") / "baseline.json"
    _write_create_once(destination, payload)
    return payload, destination


__all__ = [
    "DEFAULT_SCOPES",
    "WorkstreamBaselineError",
    "create_data_workstream_baseline",
]
