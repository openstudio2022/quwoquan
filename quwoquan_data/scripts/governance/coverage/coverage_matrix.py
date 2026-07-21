"""Coverage discovery 行政区矩阵、checkpoint、resume 与饱和证明。

本模块只管理运行契约和证据；网络 adapter 由 ``coverage_discovery`` 提供。任何
资源 limit 都只写入护栏配置，绝不自动等价为 exhausted/saturated。
"""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import paths as _paths
from core.runtime_policy import RuntimePolicy
from core.source_digest import current_source_digest
from governance.coverage.master_list import (
    admin_children,
    admin_geo_ref,
    city_is_district_level,
)
from governance.coverage.entity_type_taxonomy import PRIMARY_TYPE_PRIORITY


ENTITY_TYPES: tuple[str, ...] = tuple(
    f"地点/{type_name}" for type_name in PRIMARY_TYPE_PRIORITY
)

DISCOVERY_SOURCES: tuple[str, ...] = (
    "wiki_category",
    "wikidata_geo",
    "osm_poi",
    "baidu_baike_search",
    "toutiao_baike_search",
)

CELL_STATUSES = frozenset(
    {"pending", "running", "exhausted", "saturated", "empty", "partial", "failed"}
)
TERMINAL_CELL_STATUSES = frozenset({"exhausted", "saturated", "empty", "partial", "failed"})
SATURATED_CELL_STATUSES = frozenset({"saturated", "empty"})


@dataclass(frozen=True, slots=True)
class CoverageMatrixGuardrails:
    until_saturated: bool
    saturation_threshold: float
    saturation_rounds: int
    max_pages_per_cell: int
    max_candidates_per_city_source: int
    max_new_per_cell: int
    request_budget: int
    max_total_candidates: int
    safe_pool_minimum: int
    required_empty_pages: int
    request_timeout_seconds: int
    rate_limit_per_second: float

    @classmethod
    def from_runtime_policy(
        cls,
        policy: RuntimePolicy,
        *,
        safe_pool_minimum: int,
        until_saturated: bool,
    ) -> "CoverageMatrixGuardrails":
        if safe_pool_minimum < 1:
            raise ValueError("coverage safe pool minimum must be positive")
        config = policy.coverage_discovery
        return cls(
            until_saturated=until_saturated,
            saturation_threshold=config.saturation_threshold,
            saturation_rounds=config.saturation_rounds,
            max_pages_per_cell=config.max_pages_per_cell,
            max_candidates_per_city_source=config.max_candidates_per_city_source,
            max_new_per_cell=config.max_new_per_cell,
            request_budget=config.request_budget,
            max_total_candidates=config.max_total_candidates,
            safe_pool_minimum=safe_pool_minimum,
            required_empty_pages=config.required_empty_pages,
            request_timeout_seconds=config.request_timeout_seconds,
            rate_limit_per_second=config.rate_limit_per_second,
        )

    def as_document(self) -> dict[str, int | float | bool]:
        return {
            "untilSaturated": self.until_saturated,
            "saturationThreshold": self.saturation_threshold,
            "saturationRounds": self.saturation_rounds,
            "maxPagesPerCell": self.max_pages_per_cell,
            "maxCandidatesPerCitySource": self.max_candidates_per_city_source,
            "maxNewPerCell": self.max_new_per_cell,
            "requestBudget": self.request_budget,
            "maxTotalCandidates": self.max_total_candidates,
            "safePoolMinimum": self.safe_pool_minimum,
            "requiredEmptyPages": self.required_empty_pages,
            "requestTimeoutSeconds": self.request_timeout_seconds,
            "rateLimitPerSecond": self.rate_limit_per_second,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _runtime_root() -> Path:
    output_root = Path(os.environ.get("QWQ_OUTPUT_ROOT", _paths.OUTPUT_ROOT))
    return output_root / "data" / "local" / "workspace" / "coverage" / "matrix"


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f"{path.suffix}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _admin_tree(provinces: list[str], country: str = "中国") -> dict[str, dict[str, list[str]]]:
    tree: dict[str, dict[str, list[str]]] = {}
    for province in provinces:
        province_ref = admin_geo_ref(country, province)
        cities: dict[str, list[str]] = {}
        for city in admin_children(province_ref):
            cities[city] = (
                [city]
                if city_is_district_level(country, province, city)
                else admin_children(f"{province_ref}/{city}")
            )
        tree[province] = cities
    return tree


def _cell_id(
    province: str,
    city: str,
    district: str,
    entity_type: str,
    source: str,
) -> str:
    return _digest([province, city, district, entity_type, source]).removeprefix("sha256:")[:20]


def prepare_coverage_matrix(
    *,
    run_id: str,
    provinces: list[str],
    cities: list[str] | None = None,
    sources: list[str] | None = None,
    resume: bool = False,
    guardrails: CoverageMatrixGuardrails,
    admin_tree: dict[str, dict[str, list[str]]] | None = None,
    runtime_root: Path | None = None,
) -> dict[str, Any]:
    """创建或恢复省→市州→区县→10类→来源矩阵，不发网络请求。"""
    selected_sources = sources or list(DISCOVERY_SOURCES)
    unknown = sorted(set(selected_sources) - set(DISCOVERY_SOURCES))
    if unknown:
        raise ValueError(f"unsupported coverage discovery sources: {unknown}")
    effective_guardrails = guardrails.as_document()
    tree = admin_tree or _admin_tree(provinces)
    if cities:
        selected_cities = set(cities)
        tree = {
            province: {
                city: districts
                for city, districts in province_cities.items()
                if city in selected_cities
            }
            for province, province_cities in tree.items()
        }
        missing_cities = selected_cities - {
            city for province_cities in tree.values() for city in province_cities
        }
        if missing_cities:
            raise ValueError(f"unknown city shards: {sorted(missing_cities)}")
    root = runtime_root or _runtime_root()
    run_dir = root / run_id
    matrix_path = run_dir / "matrix.json"
    if matrix_path.exists() and not resume:
        raise FileExistsError(f"coverage run already exists; use --resume: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)

    source_digest = current_source_digest()
    revisions = {
        "adminTreeRevision": _digest(tree),
        "typeTaxonomyRevision": _digest(ENTITY_TYPES),
        "adapterRevision": "coverage-discovery-matrix",
        "sourceDigest": source_digest.digest,
    }
    checkpoint_paths: list[str] = []
    cell_count = 0
    resumed_cells = 0
    for province in provinces:
        for city, districts in (tree.get(province) or {}).items():
            checkpoint_path = run_dir / f"checkpoint_{province}_{city}.json"
            existing: dict[str, Any] = {}
            if resume and checkpoint_path.is_file():
                existing = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                if existing.get("revisions") != revisions:
                    raise ValueError(
                        f"checkpoint revision drift for {province}/{city}; start a new run-id"
                    )
                if existing.get("guardrails") != effective_guardrails:
                    raise ValueError(
                        f"checkpoint guardrail drift for {province}/{city}; start a new run-id"
                    )
            old_cells = {
                str(cell.get("cellId")): cell
                for cell in (existing.get("cells") or [])
                if isinstance(cell, dict)
            }
            cells: list[dict[str, Any]] = []
            for district in districts:
                for entity_type in ENTITY_TYPES:
                    for source in selected_sources:
                        cell_id = _cell_id(province, city, district, entity_type, source)
                        if cell_id in old_cells:
                            cell = old_cells[cell_id]
                            resumed_cells += 1
                        else:
                            cell = {
                                "cellId": cell_id,
                                "identity": {
                                    "province": province,
                                    "city": city,
                                    "district": district,
                                    "entityType": entity_type,
                                    "source": source,
                                },
                                "sourceRevision": _digest({"source": source, **revisions}),
                                "status": "pending",
                                "sourceState": {"cursor": None, "page": 0},
                                "counts": {
                                    "raw": 0,
                                    "semanticAdmitted": 0,
                                    "semanticRejected": 0,
                                    "dedupUnique": 0,
                                    "dedupDuplicate": 0,
                                },
                                "attemptState": {
                                    "attempt": 0,
                                    "retryCount": 0,
                                    "retryState": None,
                                },
                                "saturationEvidence": {
                                    "driverComplete": False,
                                    "consecutiveEmptyPages": 0,
                                    "newRatios": [],
                                    "duplicateRatios": [],
                                },
                                "stopReason": None,
                                "lastSuccessAt": None,
                                "lastPageSnapshot": None,
                                "truncated": False,
                            }
                        cells.append(cell)
            checkpoint = {
                "schema": "quwoquan_data.coverage_city_checkpoint",
                "runId": run_id,
                "province": province,
                "city": city,
                "revisions": revisions,
                "sourceDigest": source_digest.to_document(),
                "guardrails": effective_guardrails,
                "updatedAt": _now_iso(),
                "cells": cells,
            }
            _atomic_write_json(checkpoint_path, checkpoint)
            checkpoint_paths.append(str(checkpoint_path))
            cell_count += len(cells)

    matrix = {
        "schema": "quwoquan_data.coverage_discovery_matrix",
        "runId": run_id,
        "createdAt": (
            json.loads(matrix_path.read_text(encoding="utf-8")).get("createdAt")
            if resume and matrix_path.is_file()
            else _now_iso()
        ),
        "updatedAt": _now_iso(),
        "provinces": provinces,
        "sources": selected_sources,
        "entityTypes": list(ENTITY_TYPES),
        "revisions": revisions,
        "sourceDigest": source_digest.to_document(),
        "guardrails": effective_guardrails,
        "checkpointFiles": checkpoint_paths,
        "cellCount": cell_count,
    }
    _atomic_write_json(matrix_path, matrix)
    status = coverage_matrix_status(run_dir=run_dir)
    _atomic_write_json(
        run_dir / "rollup.json",
        {
            "schema": "quwoquan_data.coverage_discovery_rollup",
            "runId": run_id,
            "updatedAt": _now_iso(),
            **status,
        },
    )
    return {
        "runId": run_id,
        "runDir": str(run_dir),
        "matrixPath": str(matrix_path),
        "cityCheckpointCount": len(checkpoint_paths),
        "cellCount": cell_count,
        "resumedCellCount": resumed_cells,
        "status": status,
    }


def resumable_cells(*, run_dir: Path) -> list[dict[str, Any]]:
    """按市州 checkpoint 顺序返回非终态 cell，供分页 adapter 逐 cell 恢复。"""
    pending: list[dict[str, Any]] = []
    for checkpoint_path in sorted(run_dir.glob("checkpoint_*.json")):
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        for cell in checkpoint.get("cells") or []:
            if str(cell.get("status") or "pending") in TERMINAL_CELL_STATUSES:
                continue
            pending.append(
                {
                    "checkpointPath": str(checkpoint_path),
                    "cell": cell,
                }
            )
    return pending


def completed_discovery_shards(
    *,
    run_dir: Path,
    sources: list[str],
) -> set[tuple[str, str, str, str]]:
    """返回已成功终结的 province/city/district/source，供进程崩溃后跳过。"""
    successful = {"exhausted", "saturated", "empty"}
    grouped: dict[tuple[str, str, str, str], list[str]] = {}
    for checkpoint_path in sorted(run_dir.glob("checkpoint_*.json")):
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        for cell in checkpoint.get("cells") or []:
            identity = cell.get("identity") if isinstance(cell, dict) else None
            if not isinstance(identity, dict):
                continue
            source = str(identity.get("source") or "")
            if source not in sources:
                continue
            key = (
                str(identity.get("province") or ""),
                str(identity.get("city") or ""),
                str(identity.get("district") or ""),
                source,
            )
            grouped.setdefault(key, []).append(str(cell.get("status") or "pending"))
    return {
        key
        for key, statuses in grouped.items()
        if len(statuses) == len(ENTITY_TYPES)
        and all(status in successful for status in statuses)
    }


def record_cell_page(
    *,
    checkpoint_path: Path,
    cell_id: str,
    raw_rows: list[dict[str, Any]],
    semantic_admitted_count: int | None = None,
    semantic_rejected_count: int = 0,
    dedup_unique_count: int | None = None,
    dedup_duplicate_count: int = 0,
    semantic_admitted_rows: list[dict[str, Any]] | None = None,
    semantic_rejections: list[dict[str, Any]] | None = None,
    dedup_results: list[dict[str, Any]] | None = None,
    accepted_count: int | None = None,
    unique_new_count: int | None = None,
    next_cursor: str | None = None,
    request_succeeded: bool = True,
    exhausted: bool = False,
    truncated: bool = False,
    retry_state: dict[str, Any] | None = None,
    attempt: int = 1,
    retry_count: int = 0,
) -> dict[str, Any]:
    """每页先追加 raw NDJSON，再原子推进单 cell checkpoint。"""
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    guardrails = checkpoint.get("guardrails")
    if not isinstance(guardrails, dict):
        raise ValueError("coverage checkpoint guardrails missing")
    try:
        saturation_threshold = float(guardrails["saturationThreshold"])
        saturation_rounds = int(guardrails["saturationRounds"])
        required_empty_pages = int(guardrails["requiredEmptyPages"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("coverage checkpoint saturation guardrails invalid") from exc
    cells = checkpoint.get("cells") or []
    cell = next((row for row in cells if row.get("cellId") == cell_id), None)
    if not isinstance(cell, dict):
        raise KeyError(f"unknown coverage cell: {cell_id}")
    admitted = (
        int(semantic_admitted_count)
        if semantic_admitted_count is not None
        else int(accepted_count or 0)
    )
    unique = (
        int(dedup_unique_count)
        if dedup_unique_count is not None
        else int(unique_new_count or 0)
    )
    rejected = int(semantic_rejected_count)
    duplicate = int(dedup_duplicate_count)
    if min(admitted, rejected, unique, duplicate) < 0:
        raise ValueError("coverage page counts must be non-negative")
    if admitted + rejected != len(raw_rows):
        raise ValueError(
            "semantic admitted/rejected counts must exactly partition raw rows"
        )
    if unique + duplicate != admitted:
        raise ValueError("dedup unique/duplicate counts must exactly partition admitted rows")
    admitted_rows = semantic_admitted_rows or []
    rejection_rows = semantic_rejections or []
    dedup_rows = dedup_results or []
    if admitted_rows and len(admitted_rows) != admitted:
        raise ValueError("semantic_admitted_rows length must match admitted count")
    if rejection_rows and len(rejection_rows) != rejected:
        raise ValueError("semantic_rejections length must match rejected count")
    if dedup_rows and len(dedup_rows) != admitted:
        raise ValueError("dedup_results length must match admitted count")

    source_state = cell["sourceState"]
    cursor_before = source_state.get("cursor")
    captured_at = _now_iso()
    page_sha256 = _digest(raw_rows)
    snapshot = {
        "sha256": page_sha256,
        "rawCount": len(raw_rows),
        "capturedAt": captured_at,
    }
    raw_path = checkpoint_path.parent / (
        f"raw_{checkpoint.get('province')}_{checkpoint.get('city')}.ndjson"
    )
    with raw_path.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "schema": "quwoquan_data.coverage_raw_page",
                    "cellId": cell_id,
                    "identity": cell["identity"],
                    "capturedAt": captured_at,
                    "sourceCursorBefore": cursor_before,
                    "sourceCursorAfter": next_cursor,
                    "pageSnapshot": snapshot,
                    "rows": raw_rows,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    candidate_path = checkpoint_path.parent / (
        f"candidates_{checkpoint.get('province')}_{checkpoint.get('city')}.ndjson"
    )
    with candidate_path.open("a", encoding="utf-8") as fh:
        for index, row in enumerate(admitted_rows):
            dedup = dedup_rows[index] if index < len(dedup_rows) else {}
            if str(dedup.get("result") or "unique") != "unique":
                continue
            fh.write(
                json.dumps(
                    {
                        "cellId": cell_id,
                        "identity": cell["identity"],
                        "capturedAt": captured_at,
                        "identityKey": dedup.get("identityKey"),
                        "candidate": row,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    gaps_path = checkpoint_path.parent / (
        f"gaps_{checkpoint.get('province')}_{checkpoint.get('city')}.json"
    )
    existing_gaps = (
        json.loads(gaps_path.read_text(encoding="utf-8"))
        if gaps_path.is_file()
        else {
            "schema": "quwoquan_data.coverage_city_gaps",
            "province": checkpoint.get("province"),
            "city": checkpoint.get("city"),
            "rejectReasons": {},
            "items": [],
        }
    )
    existing_gaps["items"].extend(
        {
            "cellId": cell_id,
            "identity": cell["identity"],
            "capturedAt": captured_at,
            **row,
        }
        for row in rejection_rows
    )
    reason_counts = Counter(
        str(row.get("reason") or "unspecified") for row in existing_gaps["items"]
    )
    existing_gaps["rejectReasons"] = dict(sorted(reason_counts.items()))
    existing_gaps["updatedAt"] = captured_at
    _atomic_write_json(gaps_path, existing_gaps)

    source_state["cursor"] = next_cursor
    source_state["page"] = int(source_state.get("page") or 0) + (
        1 if request_succeeded else 0
    )
    counts = cell["counts"]
    counts["raw"] = int(counts.get("raw") or 0) + len(raw_rows)
    counts["semanticAdmitted"] = int(counts.get("semanticAdmitted") or 0) + admitted
    counts["semanticRejected"] = int(counts.get("semanticRejected") or 0) + rejected
    counts["dedupUnique"] = int(counts.get("dedupUnique") or 0) + unique
    counts["dedupDuplicate"] = int(counts.get("dedupDuplicate") or 0) + duplicate
    cell["attemptState"] = {
        "attempt": max(0, int(attempt)),
        "retryCount": max(0, int(retry_count)),
        "retryState": retry_state,
    }
    cell["lastPageSnapshot"] = snapshot
    cell["truncated"] = bool(cell.get("truncated")) or truncated
    saturation = cell["saturationEvidence"]
    if not request_succeeded:
        cell["status"] = "failed"
        cell["stopReason"] = str((retry_state or {}).get("reason") or "request_failed")
    else:
        cell["lastSuccessAt"] = captured_at
        denominator = max(1, admitted)
        new_ratios = list(saturation.get("newRatios") or [])
        duplicate_ratios = list(saturation.get("duplicateRatios") or [])
        new_ratios.append(unique / denominator)
        duplicate_ratios.append(duplicate / denominator)
        saturation["newRatios"] = new_ratios[-max(2, saturation_rounds) :]
        saturation["duplicateRatios"] = duplicate_ratios[-max(2, saturation_rounds) :]
        saturation["consecutiveEmptyPages"] = (
            int(saturation.get("consecutiveEmptyPages") or 0) + 1
            if not raw_rows
            else 0
        )
        saturation["driverComplete"] = bool(exhausted)
        if truncated:
            cell["status"] = "partial"
            cell["stopReason"] = "resource_guardrail_reached"
        elif exhausted and int(counts.get("raw") or 0) == 0:
            cell["status"] = "empty"
            cell["stopReason"] = "driver_exhausted_empty"
        elif (
            exhausted
            and int(saturation["consecutiveEmptyPages"]) >= required_empty_pages
            and len(new_ratios) >= saturation_rounds
            and all(
                ratio < saturation_threshold
                for ratio in new_ratios[-saturation_rounds:]
            )
        ):
            cell["status"] = "saturated"
            cell["stopReason"] = "driver_exhausted_and_decay_saturated"
        elif exhausted:
            cell["status"] = "exhausted"
            cell["stopReason"] = "driver_exhausted_without_decay_proof"
        else:
            cell["status"] = "running"
            cell["stopReason"] = None
    checkpoint["updatedAt"] = _now_iso()
    _atomic_write_json(checkpoint_path, checkpoint)
    run_dir = checkpoint_path.parent
    _atomic_write_json(
        run_dir / "rollup.json",
        {
            "schema": "quwoquan_data.coverage_discovery_rollup",
            "runId": checkpoint.get("runId"),
            "updatedAt": _now_iso(),
            **coverage_matrix_status(run_dir=run_dir),
        },
    )
    return cell


from governance.coverage.coverage_status import coverage_matrix_status
