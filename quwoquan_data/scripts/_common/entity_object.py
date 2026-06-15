"""实体主页对象 helper：batch object-first + task 镜像派生。

真相源：
- batch 对象根：`batches/{batch}/entities/{domain}/{type}/{name}`
- task 根 `entities/` 仅作兼容镜像，不得比 batch 对象更完整
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _common.paths import (
    OBJECT_STAGES,
    batch_entity_object_dir,
    batch_root,
    object_index_path,
    task_data,
    task_root,
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


def _scenic_location_conflict_key(domain: str, etype: str, name: str) -> tuple[str, str] | None:
    if domain == "地点" and etype in _SCENIC_LOCATION_ETYPES:
        return domain, name
    return None


def batch_entity_type_conflicts(task_id: str, batch_id: str) -> list[dict[str, Any]]:
    """检测单批次 `地点/景区` ↔ `地点/打卡地` 同名双树并存。"""
    root = batch_root(task_id, batch_id) / "entities"
    if not root.is_dir():
        return []

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for path in root.rglob("*"):
        if not path.is_dir():
            continue
        rel = path.relative_to(batch_root(task_id, batch_id)).as_posix()
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
                "taskId": task_id,
                "batchId": batch_id,
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


def iter_task_batch_ids(task_id: str) -> list[str]:
    batches_dir = task_root(task_id) / "batches"
    if not batches_dir.is_dir():
        return []
    return sorted(path.name for path in batches_dir.iterdir() if path.is_dir())


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
    from _common.io import read_json

    try:
        payload = read_json(review)
    except Exception:
        return ""
    return str(payload.get("decision") or "")


def entity_review_approved(entity_dir: Path) -> bool:
    return entity_review_decision(entity_dir) == "approved"


def find_entity_object_dir(
    task_id: str,
    domain: str,
    etype: str,
    name: str,
    *,
    batch_id: str = "",
    include_task_mirror_fallback: bool = True,
) -> Path | None:
    preferred: list[str] = []
    if batch_id:
        preferred.append(batch_id)
    preferred.extend(b for b in iter_task_batch_ids(task_id) if b != batch_id)
    for candidate_batch in preferred:
        obj = batch_entity_object_dir(task_id, candidate_batch, domain, etype, name)
        if _looks_like_entity_object(obj):
            return obj
    if include_task_mirror_fallback:
        mirror = task_data(task_id).entity_dir(domain, etype, name)
        if _looks_like_entity_object(mirror):
            return mirror
    return None


def collect_task_entity_objects(
    task_id: str,
    *,
    batch_id: str = "",
    include_task_mirror_fallback: bool = False,
    approved_only: bool = False,
    enforce_type_consistency: bool = False,
) -> list[dict[str, Any]]:
    """收集任务内实体主页对象，按相对实体路径去重。

    多批次出现同一实体时，优先取：
    1. 显式 `batch_id`
    2. surface mtime 更新较新的对象
    """

    selected: dict[str, dict[str, Any]] = {}
    batch_ids = [batch_id] if batch_id else iter_task_batch_ids(task_id)
    for current_batch in batch_ids:
        root = batch_root(task_id, current_batch) / "entities"
        if not root.is_dir():
            continue
        for marker in ("_entity.json", "page.md"):
            for path in root.rglob(marker):
                entity_dir = path.parent
                rel = entity_dir.relative_to(batch_root(task_id, current_batch)).as_posix()
                row = {
                    "taskId": task_id,
                    "batchId": current_batch,
                    "entityRel": rel,
                    "entityDir": entity_dir,
                    "mtime": _entity_surface_mtime(entity_dir),
                    "reviewDecision": entity_review_decision(entity_dir),
                }
                if approved_only and row["reviewDecision"] != "approved":
                    continue
                prev = selected.get(rel)
                if prev is None:
                    selected[rel] = row
                    continue
                if prev["batchId"] != batch_id and current_batch == batch_id:
                    selected[rel] = row
                    continue
                if float(row["mtime"]) >= float(prev["mtime"]):
                    selected[rel] = row
    if not selected and include_task_mirror_fallback:
        mirror_root = task_data(task_id).entities_dir()
        if mirror_root.is_dir():
            for marker in ("_entity.json", "page.md"):
                for path in mirror_root.rglob(marker):
                    entity_dir = path.parent
                    rel = entity_dir.relative_to(task_root(task_id)).as_posix()
                    selected[rel] = {
                        "taskId": task_id,
                        "batchId": "",
                        "entityRel": rel,
                        "entityDir": entity_dir,
                        "mtime": _entity_surface_mtime(entity_dir),
                        "reviewDecision": entity_review_decision(entity_dir),
                    }
    rows = sorted(selected.values(), key=lambda row: row["entityRel"])
    if enforce_type_consistency:
        issues = entity_type_conflict_issues_for_rows(rows)
        if issues:
            raise ValueError("; ".join(issues))
    return rows


def sync_entity_object_to_task_mirror(
    task_id: str,
    batch_id: str,
    domain: str,
    etype: str,
    name: str,
) -> Path:
    """把 batch 实体对象的最终面同步到 task 镜像。

    镜像只保留最终面三件套 + assets，不复制过程阶段，避免比 batch 对象更完整。
    """

    src = batch_entity_object_dir(task_id, batch_id, domain, etype, name)
    dst = task_data(task_id).entity_dir(domain, etype, name)
    dst.mkdir(parents=True, exist_ok=True)
    for child in dst.iterdir():
        if child.is_dir() and child.name[0].isdigit():
            shutil.rmtree(child)
    for name_ in _ENTITY_SURFACE_FILES:
        src_file = src / name_
        dst_file = dst / name_
        if src_file.is_file():
            shutil.copy2(src_file, dst_file)
        elif dst_file.exists():
            dst_file.unlink()
    src_assets = src / "assets"
    dst_assets = dst / "assets"
    if src_assets.is_dir():
        if dst_assets.exists():
            shutil.rmtree(dst_assets)
        shutil.copytree(src_assets, dst_assets)
    elif dst_assets.exists():
        shutil.rmtree(dst_assets)
    return dst


def write_entity_object_index(
    task_id: str,
    batch_id: str,
    domain: str,
    etype: str,
    name: str,
) -> Path:
    obj_dir = batch_entity_object_dir(task_id, batch_id, domain, etype, name)
    rel = obj_dir.relative_to(batch_root(task_id, batch_id)).as_posix()
    stages = {
        stage: ("done" if (obj_dir / stage).is_dir() else "pending")
        for stage in OBJECT_STAGES
    }
    path = object_index_path(obj_dir)
    from _common.io import write_json

    write_json(
        path,
        {
            "schemaVersion": "quwoquan.object.index",
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
    "iter_task_batch_ids",
    "batch_entity_type_conflicts",
    "entity_type_conflict_issues_for_rows",
    "find_entity_object_dir",
    "collect_task_entity_objects",
    "entity_review_decision",
    "entity_review_approved",
    "sync_entity_object_to_task_mirror",
    "write_entity_object_index",
]
