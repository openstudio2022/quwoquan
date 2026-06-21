"""Helpers for active entity homepage artifacts in managed batches."""
from __future__ import annotations

import shutil
from collections.abc import Iterable
from pathlib import Path

from _common.paths import batch_root


GENERATED_ENTITY_FILES = (
    "page.md",
    "_entity.json",
    "_object.json",
    "manifest.json",
)

GENERATED_ENTITY_DIRS = (
    "3.compose",
    "4.draft",
    "5.review",
    "assets",
)


def _entity_key(entity_dir: Path) -> tuple[str, str, str] | None:
    try:
        etype = entity_dir.parent.name
        domain = entity_dir.parent.parent.name
    except IndexError:
        return None
    name = entity_dir.name
    if not domain or not etype or not name:
        return None
    return domain, etype, name


def generated_entity_artifacts(entity_dir: Path) -> list[Path]:
    """Return generated homepage artifacts under one entity directory."""

    artifacts: list[Path] = []
    for filename in GENERATED_ENTITY_FILES:
        path = entity_dir / filename
        if path.exists():
            artifacts.append(path)
    for dirname in GENERATED_ENTITY_DIRS:
        path = entity_dir / dirname
        if path.exists():
            artifacts.append(path)
    return artifacts


def inactive_entity_artifact_rows(
    task_id: str,
    batch_id: str,
    *,
    active_entity_names: Iterable[str],
) -> list[dict[str, object]]:
    """List generated homepage artifacts outside the active target set.

    Download/source evidence is intentionally not treated as generated homepage
    output; abandoned targets must remain auditable without being publishable.
    """

    root = batch_root(task_id, batch_id)
    entities_root = root / "entities"
    if not entities_root.is_dir():
        return []
    active = {str(name or "").strip() for name in active_entity_names if str(name or "").strip()}
    rows: list[dict[str, object]] = []
    for entity_dir in sorted(entities_root.glob("*/*/*")):
        if not entity_dir.is_dir():
            continue
        key = _entity_key(entity_dir)
        if not key:
            continue
        domain, etype, name = key
        if name in active:
            continue
        artifacts = generated_entity_artifacts(entity_dir)
        if not artifacts:
            continue
        rows.append(
            {
                "entity": name,
                "entityType": f"{domain}/{etype}",
                "artifacts": [
                    path.relative_to(root).as_posix()
                    for path in artifacts
                ],
            }
        )
    return rows


def prune_inactive_entity_artifacts(
    task_id: str,
    batch_id: str,
    *,
    active_entity_names: Iterable[str],
) -> list[dict[str, object]]:
    """Remove generated homepage artifacts outside the active target set."""

    root = batch_root(task_id, batch_id)
    rows = inactive_entity_artifact_rows(
        task_id,
        batch_id,
        active_entity_names=active_entity_names,
    )
    for row in rows:
        for rel in row.get("artifacts") or []:
            path = root / str(rel)
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
    return rows
