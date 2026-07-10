"""Cleanup generated runtime/release artifacts through task CLI."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from _common import paths as _paths
from _common.io import write_json
from _common.paths import batch_root, release_root, task_root


CLEANUP_SCHEMA = "quwoquan_data.generated_cleanup_manifest"


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _entry(path: Path, reason: str) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "kind": "dir" if path.is_dir() else "file" if path.is_file() else "missing",
        "reason": reason,
    }


def _runtime_root() -> Path:
    return _paths.current_runtime_root()


def _release_root() -> Path:
    return Path(os.environ.get("QWQ_RELEASE_ROOT") or _paths.RELEASE_ROOT)


def build_cleanup_manifest(
    *,
    task_id: str | None = None,
    batch_id: str | None = None,
    release_id: str | None = None,
    all_runtime: bool = False,
    all_releases: bool = False,
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    runtime_root = _runtime_root()
    release_root_path = _release_root()
    if all_runtime:
        entries.append(_entry(runtime_root, "all generated runtime artifacts"))
    elif task_id and batch_id:
        entries.append(_entry(batch_root(task_id, batch_id), "generated runtime batch"))
    elif task_id:
        entries.append(_entry(task_root(task_id), "generated runtime task"))

    if all_releases:
        entries.append(_entry(release_root_path, "all isolated release artifacts"))
    elif release_id:
        entries.append(_entry(release_root(release_id), "isolated release artifact"))

    if not entries:
        raise ValueError("cleanup needs --task/--batch, --release, --all-runtime or --all-releases")

    protected_roots = {
        "publish": "publish tree is not generated cleanup scope",
        "committedTasks": "committed task specs are not generated cleanup scope",
        "schema": "schema truth source is not generated cleanup scope",
        "sop": "SOP truth source is not generated cleanup scope",
    }
    issues: list[str] = []
    for item in entries:
        path = Path(item["path"])
        if path.exists() and not (_under(path, runtime_root) or _under(path, release_root_path)):
            issues.append(f"refuse cleanup outside runtime/release roots: {path}")

    return {
        "schemaVersion": CLEANUP_SCHEMA,
        "mode": "confirm-required",
        "preserved": protected_roots,
        "entries": entries,
        "issues": issues,
        "wouldDeleteCount": sum(1 for item in entries if item["exists"]),
    }


def execute_cleanup(manifest: dict[str, Any]) -> dict[str, Any]:
    issues = list(manifest.get("issues") or [])
    if issues:
        raise RuntimeError("cleanup manifest has issues: " + "; ".join(str(i) for i in issues))
    deleted: list[str] = []
    skipped: list[str] = []
    runtime_root = _runtime_root()
    release_root_path = _release_root()
    for item in manifest.get("entries") or []:
        path = Path(str(item.get("path") or ""))
        if not path.exists():
            skipped.append(str(path))
            continue
        if not (_under(path, runtime_root) or _under(path, release_root_path)):
            raise RuntimeError(f"refuse cleanup outside runtime/release roots: {path}")
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        deleted.append(str(path))
    return {
        "schemaVersion": CLEANUP_SCHEMA,
        "deleted": deleted,
        "skipped": skipped,
        "deletedCount": len(deleted),
    }


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    write_json(path, manifest)
