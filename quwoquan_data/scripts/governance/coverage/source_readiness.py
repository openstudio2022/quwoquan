"""Deterministic encyclopedia-primary qualification for discovered travel objects."""
from __future__ import annotations

import hashlib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from core.runtime_policy import active_runtime_policy
from core.schema import assert_valid
from core.source_digest import current_source_digest
from governance.coverage.coverage_runtime import coverage_workspace_root, now_iso
from governance.coverage.source_readiness_candidates import (
    _dedupe_candidates,
    _master_candidates,
    _qualify_candidate,
    _read_candidates,
    _readiness_key,
    _source_ready_type_evidence,
    _wikipedia_evidence,
)


_ALLOWED_SOURCES = frozenset({"wikipedia", "baidu_baike", "toutiao_baike"})
_RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,95}$")


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _input_digest(
    paths: list[Path],
    *,
    include_master_list: bool,
    provinces: list[str],
) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.resolve()).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\n")
    digest.update(f"includeMasterList={include_master_list}".encode("ascii"))
    if include_master_list:
        digest.update(b"\0")
        digest.update(
            json.dumps(
                _master_candidates(provinces),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
    return "sha256:" + digest.hexdigest()


def _load_processed(*paths: Path) -> tuple[set[str], dict[str, int]]:
    processed: set[str] = set()
    qualified_by_province: dict[str, int] = {}
    for path in paths:
        if not path.is_file():
            continue
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                key = str(row.get("identityKey") or "")
                candidate = row.get("candidate") or {}
                province = str(candidate.get("province") or "")
                if key:
                    processed.add(key)
                if path.name == "source_ready.ndjson" and province:
                    qualified_by_province[province] = (
                        qualified_by_province.get(province, 0) + 1
                    )
    return processed, qualified_by_province


def _load_ready_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as handle:
        return [
            json.loads(line)
            for line in handle
            if line.strip()
        ]


def _balanced_frozen_targets(
    rows: list[dict[str, Any]],
    *,
    provinces: list[str],
    minimum_per_province: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    selected: list[dict[str, Any]] = []
    covered_cells: dict[str, int] = {}
    for province in provinces:
        groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for row in rows:
            candidate = row.get("candidate") or {}
            if str(candidate.get("province") or "") != province:
                continue
            classified = _source_ready_type_evidence(candidate)
            if classified is None:
                continue
            cell = (
                str(candidate.get("city") or ""),
                str(candidate.get("district") or ""),
                classified[0],
            )
            if all(cell):
                groups.setdefault(cell, []).append(row)
        for values in groups.values():
            values.sort(key=lambda item: str(item.get("identityKey") or ""))
        rank = 0
        while groups and rank < minimum_per_province:
            progressed = False
            for cell in sorted(groups):
                values = groups[cell]
                if not values:
                    continue
                row = values.pop(0)
                rank += 1
                selected.append(
                    {
                        **row,
                        "selection": {
                            "provinceRank": rank,
                            "coverageCell": {
                                "city": cell[0],
                                "district": cell[1],
                                "entityType": cell[2],
                            },
                        },
                    }
                )
                progressed = True
                if rank >= minimum_per_province:
                    break
            if not progressed:
                break
        covered_cells[province] = len(
            {
                (
                    item["selection"]["coverageCell"]["city"],
                    item["selection"]["coverageCell"]["district"],
                    item["selection"]["coverageCell"]["entityType"],
                )
                for item in selected
                if (item.get("candidate") or {}).get("province") == province
            }
        )
    return selected, covered_cells


def qualify_source_ready_candidates(
    *,
    run_id: str,
    provinces: list[str],
    candidate_files: list[Path],
    sources: list[str],
    minimum_per_province: int,
    include_master_list: bool,
    exhaust_input: bool,
    resume: bool,
) -> dict[str, Any]:
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("source-readiness run-id 不合法")
    normalized_sources = tuple(dict.fromkeys(str(item).strip() for item in sources))
    unsupported = sorted(set(normalized_sources) - _ALLOWED_SOURCES)
    if unsupported or not normalized_sources:
        raise ValueError(f"source-readiness 来源不合法: {unsupported}")
    if minimum_per_province < 1:
        raise ValueError("minimum-per-province 必须为正整数")
    missing = [str(path) for path in candidate_files if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"候选文件不存在: {missing}")

    run_dir = coverage_workspace_root() / "source-readiness" / run_id
    manifest_path = run_dir / "manifest.json"
    ready_path = run_dir / "source_ready.ndjson"
    inconclusive_path = run_dir / "source_inconclusive.ndjson"
    input_digest = _input_digest(
        candidate_files,
        include_master_list=include_master_list,
        provinces=provinces,
    )
    source_digest = current_source_digest().to_document()
    manifest = {
        "schema": "quwoquan_data.source_readiness_manifest",
        "runId": run_id,
        "provinces": provinces,
        "candidateFiles": [str(path) for path in candidate_files],
        "includeMasterList": include_master_list,
        "exhaustInput": exhaust_input,
        "sources": list(normalized_sources),
        "minimumPerProvince": minimum_per_province,
        "inputDigest": input_digest,
        "sourceDigest": source_digest,
    }
    if manifest_path.is_file():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not resume:
            raise FileExistsError(f"source-readiness run 已存在: {run_dir}")
        if existing != manifest:
            raise ValueError("source-readiness resume 输入或源码摘要漂移")
    else:
        if resume:
            raise FileNotFoundError(f"source-readiness resume run 不存在: {run_dir}")
        run_dir.mkdir(parents=True, exist_ok=False)
        assert_valid(
            manifest,
            "governance",
            "source_readiness_manifest",
            label="source-readiness manifest",
        )
        _atomic_write_json(manifest_path, manifest)

    all_candidates = _read_candidates(candidate_files)
    if include_master_list:
        all_candidates.extend(_master_candidates(provinces))
    candidates = _dedupe_candidates(all_candidates, provinces=provinces)
    processed, qualified_by_province = _load_processed(
        ready_path,
        inconclusive_path,
    )
    for province in provinces:
        qualified_by_province.setdefault(province, 0)
    pending = [
        candidate
        for candidate in candidates
        if _readiness_key(candidate) not in processed
        and (
            exhaust_input
            or qualified_by_province.get(str(candidate.get("province") or ""), 0)
            < minimum_per_province
        )
    ]

    policy = active_runtime_policy()
    wave_size = max(policy.research_wave_size, policy.research_workers)
    workers = max(1, policy.research_workers)
    with (
        ready_path.open("a", encoding="utf-8") as ready_handle,
        inconclusive_path.open("a", encoding="utf-8") as inconclusive_handle,
    ):
        for offset in range(0, len(pending), wave_size):
            if not exhaust_input and all(
                qualified_by_province.get(province, 0) >= minimum_per_province
                for province in provinces
            ):
                break
            wave = [
                candidate
                for candidate in pending[offset : offset + wave_size]
                if exhaust_input
                or qualified_by_province.get(
                    str(candidate.get("province") or ""),
                    0,
                ) < minimum_per_province
            ]
            if not wave:
                continue
            with ThreadPoolExecutor(max_workers=min(workers, len(wave))) as pool:
                futures = [
                    pool.submit(
                        _qualify_candidate,
                        candidate,
                        sources=normalized_sources,
                    )
                    for candidate in wave
                ]
                results = [future.result() for future in as_completed(futures)]
            for result in sorted(
                results,
                key=lambda item: str(item.get("identityKey") or ""),
            ):
                assert_valid(
                    result,
                    "governance",
                    "source_ready_candidate",
                    label="source-ready candidate",
                )
                candidate = result.get("candidate") or {}
                province = str(candidate.get("province") or "")
                handle = ready_handle if result.get("qualified") else inconclusive_handle
                handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                if result.get("qualified"):
                    qualified_by_province[province] = (
                        qualified_by_province.get(province, 0) + 1
                    )
            ready_handle.flush()
            inconclusive_handle.flush()
            os.fsync(ready_handle.fileno())
            os.fsync(inconclusive_handle.fileno())

    processed, qualified_by_province = _load_processed(
        ready_path,
        inconclusive_path,
    )
    input_by_province = {
        province: sum(
            1 for candidate in candidates if candidate.get("province") == province
        )
        for province in provinces
    }
    ready_rows = _load_ready_rows(ready_path)
    frozen_targets, covered_cells = _balanced_frozen_targets(
        ready_rows,
        provinces=provinces,
        minimum_per_province=minimum_per_province,
    )
    for frozen_target in frozen_targets:
        assert_valid(
            frozen_target,
            "governance",
            "source_ready_candidate",
            label="source-ready frozen target",
        )
    frozen_path = run_dir / "frozen_targets.ndjson"
    frozen_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n"
            for row in frozen_targets
        ),
        encoding="utf-8",
    )
    frozen_by_province = {
        province: sum(
            1
            for row in frozen_targets
            if (row.get("candidate") or {}).get("province") == province
        )
        for province in provinces
    }
    below_minimum = {
        province: {
            "required": minimum_per_province,
            "actual": frozen_by_province.get(province, 0),
        }
        for province in provinces
        if frozen_by_province.get(province, 0) < minimum_per_province
    }
    report = {
        "schema": "quwoquan_data.source_readiness_report",
        "runId": run_id,
        "generatedAt": now_iso(),
        "sourceDigest": source_digest,
        "inputDigest": input_digest,
        "sources": list(normalized_sources),
        "minimumPerProvince": minimum_per_province,
        "exhaustInput": exhaust_input,
        "inputExhausted": len(processed) >= len(candidates),
        "inputUniqueByProvince": input_by_province,
        "qualifiedByProvince": qualified_by_province,
        "frozenByProvince": frozen_by_province,
        "coveredCellsByProvince": covered_cells,
        "processed": len(processed),
        "belowMinimum": below_minimum,
        "decision": "GO" if not below_minimum else "NO_GO",
        "outputs": {
            "ready": str(ready_path),
            "inconclusive": str(inconclusive_path),
            "frozenTargets": str(frozen_path),
        },
    }
    assert_valid(
        report,
        "governance",
        "source_readiness_report",
        label="source-readiness report",
    )
    _atomic_write_json(run_dir / "report.json", report)
    return report


__all__ = ["qualify_source_ready_candidates"]
