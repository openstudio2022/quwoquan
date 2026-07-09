"""仓外 artifacts 摘要索引层（index-first，数据输出规范）。

裁定：`QWQ_OUTPUT_ROOT/runs/data/**` 只做镜像索引，不承载权威证据；
权威证据唯一真相源是 `batch/_shared/**`（见 paths.BATCH_SHARED_AUTHORITATIVE_ENTRIES）、
仓内 `publish/**` 与 `release/**`。任何 summary 目录必须带 `index.json` 回指：

    runtimeBatchRoot / taskId / publishRoot / releaseId /
    phase / contentType / supplyMode / sourceKey / maturity

目录布局（一级维度 = 用户查找维度）：
    .qwq_output/runs/data/content_runs/{e2e|operations}/{contentType}/{batchId}/
    .qwq_output/runs/data/pools/{creator|user}/{batchId}/
    .qwq_output/runs/data/app/{local-gamma|device-matrix|seed-matrix|startup-probes}/
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from _common import paths
from _common.io import read_json, write_json
from _common.paths import batch_manifest_path, batch_root, now_iso

ARTIFACTS_INDEX_FILENAME = "index.json"
ARTIFACTS_INDEX_SCHEMA = "quwoquan.artifacts.index/v1"
# 索引必填回指字段（缺任一即断链，门禁 BLOCK）。
ARTIFACTS_INDEX_REQUIRED_FIELDS = (
    "runtimeBatchRoot",
    "taskId",
    "publishRoot",
    "releaseId",
    "phase",
    "contentType",
    "supplyMode",
    "sourceKey",
    "maturity",
)
APP_ARTIFACT_KINDS = ("local-gamma", "device-matrix", "seed-matrix", "startup-probes")


def content_run_artifacts_dir(phase: str, content_type: str, batch_id: str) -> Path:
    return paths.OUTPUT_ARTIFACTS_ROOT / "content_runs" / phase / content_type / batch_id


def pool_artifacts_dir(pool_kind: str, batch_id: str) -> Path:
    if pool_kind not in ("creator", "user"):
        raise ValueError(f"unknown pool kind: {pool_kind!r} (expect creator|user)")
    return paths.OUTPUT_ARTIFACTS_ROOT / "pools" / pool_kind / batch_id


def app_artifacts_dir(kind: str) -> Path:
    if kind not in APP_ARTIFACT_KINDS:
        raise ValueError(f"unknown app artifact kind: {kind!r} (expect {APP_ARTIFACT_KINDS})")
    return paths.OUTPUT_ARTIFACTS_ROOT / "app" / kind


def build_artifacts_index_entry(
    task_id: str,
    batch_id: str,
    *,
    release_id: str = "",
    maturity: str = "",
) -> dict[str, Any]:
    """从批次真相源（batch_manifest + paths）构造回指字段，禁止手写第二套。"""
    manifest: Mapping[str, Any] = {}
    manifest_path = batch_manifest_path(task_id, batch_id) if task_id else None
    if manifest_path is not None and manifest_path.is_file():
        try:
            loaded = read_json(manifest_path)
            if isinstance(loaded, Mapping):
                manifest = loaded
        except Exception:  # noqa: BLE001 - 索引层降级为空回指，不阻断报告写出
            manifest = {}
    runtime_batch_root = str(batch_root(task_id, batch_id)) if task_id else ""
    return {
        "schema": ARTIFACTS_INDEX_SCHEMA,
        "runtimeBatchRoot": runtime_batch_root,
        "taskId": task_id,
        "batchId": batch_id,
        "publishRoot": str(paths.PUBLISH_ROOT),
        "releaseId": str(release_id or manifest.get("releaseId") or ""),
        "phase": str(manifest.get("phase") or ""),
        "contentType": str(manifest.get("contentType") or ""),
        "supplyMode": str(manifest.get("supplyMode") or ""),
        "sourceKey": str(manifest.get("sourceKey") or ""),
        "maturity": str(maturity or manifest.get("maturity") or ""),
    }


def register_artifact_report(
    report_path: Path,
    *,
    task_id: str,
    batch_id: str,
    report_kind: str,
    release_id: str = "",
    maturity: str = "",
) -> Path:
    """把一份 summary 报告登记进同目录 `index.json`（merge 追加，不覆盖回指）。

    仅当报告落在 OUTPUT_ARTIFACTS_ROOT 下才登记（batch/_shared 内的权威证据
    不属于摘要索引层）。返回 index.json 路径（未登记时也返回预期路径）。
    """
    report_path = Path(report_path).resolve()
    index_path = report_path.parent / ARTIFACTS_INDEX_FILENAME
    try:
        report_path.relative_to(paths.OUTPUT_ARTIFACTS_ROOT.resolve())
    except ValueError:
        return index_path
    entry = build_artifacts_index_entry(
        task_id, batch_id, release_id=release_id, maturity=maturity
    )
    existing: dict[str, Any] = {}
    if index_path.is_file():
        try:
            loaded = read_json(index_path)
            if isinstance(loaded, dict):
                existing = loaded
        except Exception:  # noqa: BLE001 - 索引损坏时重建
            existing = {}
    merged = {**existing, **{k: v for k, v in entry.items() if v}}
    merged.setdefault("schema", ARTIFACTS_INDEX_SCHEMA)
    for field in ARTIFACTS_INDEX_REQUIRED_FIELDS:
        merged.setdefault(field, entry.get(field, ""))
    reports = [r for r in merged.get("reports") or [] if isinstance(r, dict)]
    rel_name = report_path.name
    reports = [r for r in reports if str(r.get("file")) != rel_name]
    reports.append({"file": rel_name, "kind": report_kind, "writtenAt": now_iso()})
    merged["reports"] = sorted(reports, key=lambda r: str(r.get("file")))
    write_json(index_path, merged)
    return index_path


def artifacts_index_issues(index_path: Path) -> list[str]:
    """索引门：index.json 必须存在、可读、回指字段齐全（可为空串的仅 releaseId/sourceKey/maturity）。"""
    if not index_path.is_file():
        return [f"{index_path}: 摘要目录缺 index.json（artifacts 必须 index-first 回指）"]
    try:
        data = read_json(index_path)
    except Exception as exc:  # noqa: BLE001
        return [f"{index_path}: index.json unreadable ({exc})"]
    if not isinstance(data, Mapping):
        return [f"{index_path}: index.json 须为对象"]
    issues: list[str] = []
    optional_empty = {"releaseId", "sourceKey", "maturity"}
    for field in ARTIFACTS_INDEX_REQUIRED_FIELDS:
        if field not in data:
            issues.append(f"{index_path}: index 缺回指字段 {field}")
        elif field not in optional_empty and not str(data.get(field) or "").strip():
            issues.append(f"{index_path}: index 回指字段 {field} 为空")
    return issues
