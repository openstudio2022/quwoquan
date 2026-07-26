"""实体主页对象 helper：一个 execution 工作包内只有一个对象真相源。"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.paths import (
    OBJECT_STAGES,
    execution_entity_object_dir,
    execution_root,
    iter_execution_ids as _paths_iter_execution_ids,
    object_index_path,
)

_ENTITY_SURFACE_FILES = ("_entity.json", "page.md", "manifest.json")
_SCENIC_LOCATION_ETYPES = frozenset({"景区", "打卡地"})


def entity_rel_path(domain: str, etype: str, name: str) -> Path:
    return Path("entities") / domain / etype / name


def parse_entity_rel(entity_rel: str | Path) -> tuple[str, str, str] | None:
    parts = Path(str(entity_rel)).parts
    if parts and parts[0] == "entities":
        parts = parts[1:]
    if len(parts) < 3:
        return None
    return parts[0], parts[1], "/".join(parts[2:])


def parse_entity_ref(value: str) -> tuple[str, str, str] | None:
    """Decode the canonical entity identity used by execution jobs.

    This is deliberately separate from filesystem-relative object paths:
    callers that carry an entity reference must not infer identity from a
    prompt, filename, or display text.
    """
    parts = str(value or "").strip().strip("/").split("/", 3)
    if len(parts) != 4 or parts[0] != "entity" or not all(parts[1:]):
        return None
    return parts[1], parts[2], parts[3]


def _scenic_location_conflict_key(domain: str, etype: str, name: str) -> tuple[str, str] | None:
    if domain == "地点" and etype in _SCENIC_LOCATION_ETYPES:
        return domain, name
    return None


def execution_entity_type_conflicts(execution_id: str) -> list[dict[str, Any]]:
    """检测单一执行内 `地点/景区` 与 `地点/打卡地` 同名双树并存。"""
    root = execution_root(execution_id) / "entities"
    if not root.is_dir():
        return []

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for path in root.rglob("*"):
        if not path.is_dir():
            continue
        rel = path.relative_to(execution_root(execution_id)).as_posix()
        parsed = parse_entity_rel(rel)
        if parsed is None:
            continue
        domain, etype, name = parsed
        key = _scenic_location_conflict_key(domain, etype, name)
        if key is None:
            continue
        if not _looks_like_entity_object(path):
            continue
        row = grouped.setdefault(
            key,
            {
                "executionId": execution_id,
                "domain": domain,
                "name": name,
                "etypes": set(),
                "paths": [],
            },
        )
        row["etypes"].add(etype)
        row["paths"].append(rel)

    conflicts: list[dict[str, Any]] = []
    for row in grouped.values():
        if len(row["etypes"]) < 2:
            continue
        conflicts.append(
            {
                **row,
                "etypes": sorted(row["etypes"]),
                "paths": sorted(set(row["paths"])),
            }
        )
    return sorted(conflicts, key=lambda row: (row["domain"], row["name"]))


def entity_type_conflict_issues_for_rows(rows: list[dict[str, Any]]) -> list[str]:
    """检测选中实体集合中的 `景区/打卡地` 同名双树漂移。"""
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        parsed = parse_entity_rel(str(row.get("entityRel") or ""))
        if parsed is None:
            continue
        domain, etype, name = parsed
        key = _scenic_location_conflict_key(domain, etype, name)
        if key is None:
            continue
        bucket = grouped.setdefault(key, {"etypes": set(), "paths": []})
        bucket["etypes"].add(etype)
        bucket["paths"].append(str(row.get("entityRel") or ""))

    issues: list[str] = []
    for (domain, name), row in sorted(grouped.items()):
        if len(row["etypes"]) < 2:
            continue
        issues.append(
            f"entity type drift: {domain}/{name} dual trees coexist under scenic-location pair "
            f"{sorted(row['etypes'])} -> {sorted(set(row['paths']))}"
        )
    return issues


def iter_execution_ids(execution_id: str) -> list[str]:
    """返回当前 executionId。"""
    return _paths_iter_execution_ids(execution_id)


def _entity_surface_mtime(entity_dir: Path) -> float:
    times: list[float] = []
    for name in _ENTITY_SURFACE_FILES:
        path = entity_dir / name
        if path.is_file():
            try:
                times.append(path.stat().st_mtime)
            except OSError:
                continue
    if not times:
        try:
            return entity_dir.stat().st_mtime
        except OSError:
            return 0.0
    return max(times)


def _looks_like_entity_object(entity_dir: Path) -> bool:
    return (
        any((entity_dir / name).exists() for name in _ENTITY_SURFACE_FILES)
        or (entity_dir / "1.download").is_dir()
    )


def entity_review_decision(entity_dir: Path) -> str:
    review = entity_dir / "5.review" / "review.json"
    if not review.is_file():
        return ""
    from core.io import read_json

    try:
        payload = read_json(review)
    except Exception:
        return ""
    return str(payload.get("decision") or "")


def entity_review_approved(entity_dir: Path) -> bool:
    return entity_review_decision(entity_dir) == "approved"


def find_entity_object_dir(
    execution_id: str,
    domain: str,
    etype: str,
    name: str,
) -> Path | None:
    obj = execution_entity_object_dir(execution_id, domain, etype, name)
    if _looks_like_entity_object(obj):
        return obj
    return None


def collect_execution_entity_objects(
    execution_id: str,
    *,
    approved_only: bool = False,
    enforce_type_consistency: bool = False,
) -> list[dict[str, Any]]:
    """收集一个执行工作包内的实体主页对象，按相对路径去重。"""

    selected: dict[str, dict[str, Any]] = {}
    root = execution_root(execution_id) / "entities"
    if not root.is_dir():
        return []
    for marker in ("_entity.json", "page.md"):
        for path in root.rglob(marker):
            entity_dir = path.parent
            rel = entity_dir.relative_to(root.parent).as_posix()
            row = {
                "executionId": execution_id,
                "entityRel": rel,
                "entityDir": entity_dir,
                "mtime": _entity_surface_mtime(entity_dir),
                "reviewDecision": entity_review_decision(entity_dir),
            }
            if approved_only and row["reviewDecision"] != "approved":
                continue
            previous = selected.get(rel)
            if previous is None or float(row["mtime"]) >= float(previous["mtime"]):
                selected[rel] = row
    rows = sorted(selected.values(), key=lambda row: row["entityRel"])
    if enforce_type_consistency:
        issues = entity_type_conflict_issues_for_rows(rows)
        if issues:
            raise ValueError("; ".join(issues))
    return rows


def write_entity_object_index(
    execution_id: str,
    domain: str,
    etype: str,
    name: str,
) -> Path:
    obj_dir = execution_entity_object_dir(execution_id, domain, etype, name)
    rel = obj_dir.relative_to(execution_root(execution_id)).as_posix()
    stages = {
        stage: ("done" if (obj_dir / stage).is_dir() else "pending")
        for stage in OBJECT_STAGES
    }
    path = object_index_path(obj_dir)
    from core.io import write_json

    write_json(
        path,
        {
            "schema": "quwoquan.object.index",
            "objectKind": "entity",
            "objectRef": f"/entity/{domain}/{etype}/{name}",
            "publishTargetRef": rel,
            "finalRef": rel,
            "stages": stages,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        },
    )
    return path


__all__ = [
    "entity_rel_path",
    "parse_entity_rel",
    "parse_entity_ref",
    "iter_execution_ids",
    "execution_entity_type_conflicts",
    "entity_type_conflict_issues_for_rows",
    "find_entity_object_dir",
    "collect_execution_entity_objects",
    "entity_review_decision",
    "entity_review_approved",
    "write_entity_object_index",
]
