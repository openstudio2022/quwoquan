"""批次级公共信息上提（规格 §2.2/§4/§14）。

对象优先布局把任务/批次级公共信息从对象目录抽到 batch 根，避免在每个实体/内容
目录重复：
- ``batch_manifest.json``：批次定义快照（taskId/batchId/layout/env/salt/params/
  coverageTargets/commandChain/时间），是「批次怎么跑出来的」的唯一公共记录。
- ``_shared/source_catalog.json``：本批次受控来源类目投影（从 committed
  ``source_catalog.yaml`` 唯一真相源投影，供对象目录引用，不再各自维护）。

两者均幂等：重复调用只刷新 ``updatedAt`` 与命令链，不破坏既有事实。
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from _common.io import read_json, write_json
from _common.paths import (
    batch_content_type,
    batch_manifest_path,
    batch_phase,
    batch_source_catalog_path,
    batch_supply_mode,
    task_manifest,
)
from _common.global_batch_seq import allocate_global_batch_seq
from _common.source_catalog import load_source_catalog

BATCH_MANIFEST_SCHEMA = "quwoquan_data.batch_manifest"
SOURCE_CATALOG_SCHEMA = "quwoquan_data.batch_source_catalog"
TASK_MANIFEST_SCHEMA = "quwoquan.task.manifest"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coverage(targets: Sequence[Mapping[str, Any]] | None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for target in targets or []:
        if not isinstance(target, Mapping):
            continue
        name = str(target.get("name") or "").strip()
        if not name:
            continue
        out.append({"name": name, "entityType": str(target.get("entityType") or "").strip()})
    return out


def load_batch_manifest(task_id: str, batch_id: str) -> dict[str, Any]:
    path = batch_manifest_path(task_id, batch_id)
    if not path.is_file():
        return {}
    data = read_json(path)
    return data if isinstance(data, dict) else {}


def _coerce_global_batch_seq(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def write_batch_manifest(
    task_id: str,
    batch_id: str,
    *,
    coverage_targets: Sequence[Mapping[str, Any]] | None = None,
    command: str = "",
    content_type: str = "",
    supply_mode: str = "",
    source_key: str = "",
) -> Path:
    """写/刷新批次定义快照（幂等）。

    首次创建固化 env/salt/params/coverageTargets 与目录规范三级主键
    （phase/contentType/supplyMode + sourceKey 字段）；后续调用只追加命令链、
    刷新时间，并在首次缺失 coverageTargets 时补齐（download 独跑无 spec → 由 task run 补）。
    显式入参（如 site-supply 桥接声明 site_primary + siteId）优先于 env 声明。
    """
    path = batch_manifest_path(task_id, batch_id)
    now = _now_iso()
    manifest = load_batch_manifest(task_id, batch_id)
    if not manifest:
        manifest = {
            "schemaVersion": BATCH_MANIFEST_SCHEMA,
            "taskId": task_id,
            "batchId": batch_id,
            "layout": "object-first",
            # 目录规范三级主键（批次唯一声明，写入后不可变；目录层级与字段同源）。
            "phase": batch_phase(),
            "contentType": content_type or batch_content_type(),
            "supplyMode": supply_mode or batch_supply_mode(),
            # sourceKey 降级为 manifest 字段（site_primary 记 siteId，search_supplement 记检索键）。
            "sourceKey": source_key or os.environ.get("QWQ_BATCH_SOURCE_KEY", ""),
            "env": os.environ.get("QWQ_RUNTIME_ENV", "alpha"),
            "salt": os.environ.get("QWQ_BATCH_SALT", ""),
            "params": {},
            "coverageTargets": _coverage(coverage_targets),
            "commandChain": [],
            "createdAt": now,
            "globalBatchSeq": allocate_global_batch_seq(),
        }
    else:
        seq = _coerce_global_batch_seq(manifest.get("globalBatchSeq"))
        if seq > 0:
            manifest["globalBatchSeq"] = seq
        else:
            manifest["globalBatchSeq"] = allocate_global_batch_seq()
        # 三级主键写入后不可变：仅在缺失（legacy manifest）时补齐，不覆盖既有声明。
        if not manifest.get("phase"):
            manifest["phase"] = batch_phase()
        if not manifest.get("contentType"):
            manifest["contentType"] = content_type or batch_content_type()
        if not manifest.get("supplyMode"):
            manifest["supplyMode"] = supply_mode or batch_supply_mode()
        if not manifest.get("sourceKey") and (source_key or os.environ.get("QWQ_BATCH_SOURCE_KEY")):
            manifest["sourceKey"] = source_key or os.environ.get("QWQ_BATCH_SOURCE_KEY", "")
    if coverage_targets and not manifest.get("coverageTargets"):
        manifest["coverageTargets"] = _coverage(coverage_targets)
    if command:
        chain = manifest.setdefault("commandChain", [])
        if command not in chain:
            chain.append(command)
    manifest["updatedAt"] = now
    write_json(path, manifest)
    return path


def write_task_manifest(task_id: str, spec: Mapping[str, Any] | None) -> Path:
    """写/刷新任务定义快照（§14.1，幂等）：垂类/组织方式/口径/角度，来源 committed task.yaml。"""
    spec = spec or {}
    scope_in = spec.get("scope") if isinstance(spec.get("scope"), Mapping) else {}
    content_in = spec.get("content") if isinstance(spec.get("content"), Mapping) else {}
    path = task_manifest(task_id)
    created = _now_iso()
    if path.is_file():
        existing = read_json(path)
        if isinstance(existing, dict) and existing.get("createdAt"):
            created = str(existing["createdAt"])
    manifest = {
        "schemaVersion": TASK_MANIFEST_SCHEMA,
        "taskId": task_id,
        "intentLabel": str(spec.get("intentLabel") or "").strip(),
        "vertical": str(spec.get("vertical") or ""),
        "organizeBy": str(spec.get("organizeBy") or scope_in.get("organizeBy") or ""),
        "scope": {
            "region": str(scope_in.get("region") or ""),
            "entityTypes": [str(t) for t in (scope_in.get("entityTypes") or []) if t],
            "coverageTargets": _coverage(scope_in.get("coverageTargets")),
        },
        "content": {"angles": [str(a) for a in (content_in.get("angles") or []) if a]},
        "createdAt": created,
        "updatedAt": _now_iso(),
    }
    write_json(path, manifest)
    return path


def write_source_catalog(task_id: str, batch_id: str) -> Path:
    """把 committed 受控来源类目投影到批次 _shared（只读引用，不另维护第二套清单）。"""
    path = batch_source_catalog_path(task_id, batch_id)
    catalog = load_source_catalog()
    kinds: list[dict[str, str]] = []
    for category in catalog.get("categories") or []:
        if not isinstance(category, Mapping):
            continue
        cid = str(category.get("id") or "").strip()
        if not cid:
            continue
        kinds.append(
            {
                "kind": cid,
                "label": str(category.get("label") or category.get("name") or cid),
                "note": str(category.get("note") or ""),
            }
        )
    write_json(
        path,
        {
            "schemaVersion": SOURCE_CATALOG_SCHEMA,
            "source": "templates/_registry/catalogs/source_catalog.yaml",
            "sourceKinds": kinds,
        },
    )
    return path
