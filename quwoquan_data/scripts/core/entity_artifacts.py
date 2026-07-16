"""Helpers for active entity homepage artifacts in managed batches."""
from __future__ import annotations

import shutil
from collections.abc import Iterable
from pathlib import Path

from core.io import read_json
from core.paths import execution_root


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


def inactive_entity_artifact_rows(
    execution_id: str,
    *,
    active_entity_names: Iterable[str],
) -> list[dict[str, object]]:
    """List complete work-package objects outside the active target set."""

    root = execution_root(execution_id)
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
        artifacts = [entity_dir]
        sources_root = root / "sources"
        if sources_root.is_dir():
            for meta_path in sorted(sources_root.glob("*/meta.json")):
                try:
                    meta = read_json(meta_path)
                except (OSError, ValueError, TypeError):
                    continue
                if str(meta.get("entityName") or "").strip() == name:
                    artifacts.append(meta_path.parent)
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
    execution_id: str,
    *,
    active_entity_names: Iterable[str],
) -> list[dict[str, object]]:
    """Delete inactive work objects; the caller persists the deletion ledger."""

    root = execution_root(execution_id)
    rows = inactive_entity_artifact_rows(
        execution_id,
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
