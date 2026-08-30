"""Deterministic encyclopedia-primary qualification for discovered travel objects."""
from __future__ import annotations

import hashlib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from core.schema import assert_valid
from core.source_digest import current_source_definition_snapshot
from governance.coverage.coverage_runtime import coverage_workspace_root, now_iso
from governance.coverage.source_readiness_candidates import (
    SourceReadinessTargetError,
    canonical_source_ready_entity_ref,
    canonical_source_ready_name,
    _dedupe_candidates,
    _master_candidates,
    _qualify_candidate,
    _read_candidates,
    _readiness_key,
    _source_ready_type_evidence,
    _wikipedia_evidence,
    resolve_required_master_candidates,
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
    required_entity_refs: tuple[str, ...] = (),
    required_master_candidates: list[dict[str, Any]] | None = None,
) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.resolve()).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\n")
    digest.update(f"includeMasterList={include_master_list}".encode("ascii"))
    if required_entity_refs:
        digest.update(b"\0requiredEntityRefs=")
        digest.update(
            json.dumps(
                required_entity_refs,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        digest.update(b"\0requiredMasterCandidates=")
        digest.update(
            json.dumps(
                required_master_candidates or [],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
    elif include_master_list:
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
    freeze_all: bool = False,
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
        while groups and (freeze_all or rank < minimum_per_province):
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
                if not freeze_all and rank >= minimum_per_province:
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


def _exact_frozen_targets(
    rows: list[dict[str, Any]],
    *,
    required_entity_refs: tuple[str, ...],
) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
    """Freeze every qualified exact target in requested canonical order."""

    by_ref: dict[str, list[dict[str, Any]]] = {
        entity_ref: [] for entity_ref in required_entity_refs
    }
    for row in rows:
        candidate = row.get("candidate") or {}
        classified = _source_ready_type_evidence(candidate)
        if classified is None:
            continue
        try:
            entity_ref = canonical_source_ready_entity_ref(
                candidate,
                entity_type=classified[0],
            )
        except ValueError:
            continue
        if entity_ref in by_ref:
            by_ref[entity_ref].append(row)

    ambiguous = [
        entity_ref
        for entity_ref, matched_rows in by_ref.items()
        if len(matched_rows) > 1
    ]
    if ambiguous:
        raise SourceReadinessTargetError(
            [f"qualified exact targets are ambiguous: {ambiguous}"]
        )

    selected: list[dict[str, Any]] = []
    province_ranks: dict[str, int] = {}
    missing: list[str] = []
    for entity_ref in required_entity_refs:
        matched_rows = by_ref[entity_ref]
        if not matched_rows:
            missing.append(entity_ref)
            continue
        row = matched_rows[0]
        candidate = row.get("candidate") or {}
        classified = _source_ready_type_evidence(candidate)
        if classified is None:
            missing.append(entity_ref)
            continue
        province = str(candidate.get("province") or "")
        province_ranks[province] = province_ranks.get(province, 0) + 1
        selected.append(
            {
                **row,
                "candidate": {
                    **candidate,
                    "canonicalName": canonical_source_ready_name(candidate),
                    "canonicalEntityRef": entity_ref,
                    "entityType": classified[0],
                    "typeTagRefs": classified[1],
                },
                "selection": {
                    "provinceRank": province_ranks[province],
                    "coverageCell": {
                        "city": str(candidate.get("city") or ""),
                        "district": str(candidate.get("district") or ""),
                        "entityType": classified[0],
                    },
                },
            }
        )
    covered_cells = {
        province: len(
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
        for province in province_ranks
    }
    return selected, covered_cells, missing


def qualify_source_ready_candidates(
    *,
    run_id: str,
    provinces: list[str],
    candidate_files: list[Path],
    sources: list[str],
    minimum_per_province: int,
    max_concurrent_workers: int,
    include_master_list: bool,
    exhaust_input: bool,
    resume: bool,
    required_entity_refs: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("source-readiness run-id 不合法")
    if (
        isinstance(max_concurrent_workers, bool)
        or not isinstance(max_concurrent_workers, int)
        or max_concurrent_workers < 1
    ):
        raise ValueError(
            "source-readiness max-concurrent-workers 必须由调用方显式给出正整数"
        )
    normalized_sources = tuple(dict.fromkeys(str(item).strip() for item in sources))
    unsupported = sorted(set(normalized_sources) - _ALLOWED_SOURCES)
    if unsupported or not normalized_sources:
        raise ValueError(f"source-readiness 来源不合法: {unsupported}")
    if minimum_per_province < 1:
        raise ValueError("minimum-per-province 必须为正整数")
    normalized_required_refs, required_master_candidates = (
        resolve_required_master_candidates(
            required_entity_refs,
            provinces=provinces,
        )
    )
    exact_target_mode = bool(normalized_required_refs)
    effective_candidate_files = [] if exact_target_mode else candidate_files
    effective_include_master_list = include_master_list or exact_target_mode
    effective_exhaust_input = exhaust_input or exact_target_mode
    missing = [
        str(path) for path in effective_candidate_files if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError(f"候选文件不存在: {missing}")

    run_dir = coverage_workspace_root() / "source-readiness" / run_id
    manifest_path = run_dir / "manifest.json"
    ready_path = run_dir / "source_ready.ndjson"
    inconclusive_path = run_dir / "source_inconclusive.ndjson"
    input_digest = _input_digest(
        effective_candidate_files,
        include_master_list=effective_include_master_list,
        provinces=provinces,
        required_entity_refs=normalized_required_refs,
        required_master_candidates=required_master_candidates,
    )
    existing_manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if resume and manifest_path.is_file()
        else None
    )
    # A resume reads only the capture stored by the original run.  It must not
    # scan the changing live source tree merely to rediscover an identity it is
    # explicitly forbidden to replace.
    source_digest = (
        existing_manifest.get("sourceDigest")
        if isinstance(existing_manifest, dict)
        else current_source_definition_snapshot().to_document()
    )
    manifest = {
        "schema": "quwoquan_data.source_readiness_manifest",
        "runId": run_id,
        "provinces": provinces,
        "candidateFiles": [str(path) for path in effective_candidate_files],
        "includeMasterList": effective_include_master_list,
        "exhaustInput": effective_exhaust_input,
        "sources": list(normalized_sources),
        "minimumPerProvince": minimum_per_province,
        "inputDigest": input_digest,
        "sourceDigest": source_digest,
        **(
            {"requiredEntityRefs": list(normalized_required_refs)}
            if exact_target_mode
            else {}
        ),
    }
    if manifest_path.is_file():
        existing = existing_manifest or json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
        if not resume:
            raise FileExistsError(f"source-readiness run 已存在: {run_dir}")
        # Source qualification is a long-running acquisition against the
        # immutable definitions captured by the first manifest.  Executor or
        # live policy edits after capture must not invalidate already written
        # evidence.  Compare every request/input field, then reuse the frozen
        # source snapshot instead of comparing the live tree.
        if existing != manifest:
            raise ValueError("source-readiness resume 输入或冻结来源摘要漂移")
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

    if exact_target_mode:
        candidates = required_master_candidates
    else:
        all_candidates = _read_candidates(effective_candidate_files)
        if effective_include_master_list:
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
            exact_target_mode
            or effective_exhaust_input
            or qualified_by_province.get(str(candidate.get("province") or ""), 0)
            < minimum_per_province
        )
    ]

    # 一个 wave 就是一次满并发：规模增长只增加 wave 数，不增加同时运行的进程数。
    wave_size = max_concurrent_workers
    workers = max_concurrent_workers
    with (
        ready_path.open("a", encoding="utf-8") as ready_handle,
        inconclusive_path.open("a", encoding="utf-8") as inconclusive_handle,
    ):
        for offset in range(0, len(pending), wave_size):
            if not exact_target_mode and not effective_exhaust_input and all(
                qualified_by_province.get(province, 0) >= minimum_per_province
                for province in provinces
            ):
                break
            wave = [
                candidate
                for candidate in pending[offset : offset + wave_size]
                if exact_target_mode
                or effective_exhaust_input
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
    missing_required_refs: list[str] = []
    if exact_target_mode:
        frozen_targets, covered_cells, missing_required_refs = (
            _exact_frozen_targets(
                ready_rows,
                required_entity_refs=normalized_required_refs,
            )
        )
    else:
        frozen_targets, covered_cells = _balanced_frozen_targets(
            ready_rows,
            provinces=provinces,
            minimum_per_province=minimum_per_province,
            freeze_all=effective_exhaust_input,
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
    below_minimum = {} if exact_target_mode else {
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
        "exhaustInput": effective_exhaust_input,
        "inputExhausted": len(processed) >= len(candidates),
        "inputUniqueByProvince": input_by_province,
        "qualifiedByProvince": qualified_by_province,
        "frozenByProvince": frozen_by_province,
        "coveredCellsByProvince": covered_cells,
        "processed": len(processed),
        "belowMinimum": below_minimum,
        "decision": (
            "GO"
            if not (missing_required_refs if exact_target_mode else below_minimum)
            else "NO_GO"
        ),
        **(
            {
                "requiredEntityRefs": list(normalized_required_refs),
                "frozenEntityRefs": [
                    str((row.get("candidate") or {}).get("canonicalEntityRef") or "")
                    for row in frozen_targets
                ],
                "missingRequiredEntityRefs": missing_required_refs,
            }
            if exact_target_mode
            else {}
        ),
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


__all__ = [
    "SourceReadinessTargetError",
    "qualify_source_ready_candidates",
]
