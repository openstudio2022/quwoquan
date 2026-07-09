"""Quality, downstream and rollup reports for site-supply."""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import functools
import hashlib
import json
import math
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any, Mapping

import yaml

from _common.io import read_json, write_json
from _common.paths import DATA_ROOT, RUNTIME_ROOT, now_iso
from download.fetch import fetch_image_payload, fetch_source_payload

from site_supply.core import *  # noqa: F403
from site_supply.packets import *  # noqa: F403
from site_supply.targets import *  # noqa: F403
from site_supply.content_plan import *  # noqa: F403

def _by_ref(rows: list[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        ref = str(row.get("candidateRef") or "").strip()
        if ref:
            indexed[ref] = row
    return indexed

def _bump(counter: dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1

def _packet_gate_passed(packet: Mapping[str, Any]) -> bool:
    gate = packet.get("gate") if isinstance(packet.get("gate"), Mapping) else {}
    return bool(gate.get("passed"))

def _packet_gate_reasons(packet: Mapping[str, Any], field: str) -> list[str]:
    gate = packet.get("gate") if isinstance(packet.get("gate"), Mapping) else {}
    return [str(item) for item in (gate.get(field) or []) if str(item).strip()]

def _read_packet_rows(root: Path, stage_dir: str, packet_name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((root / stage_dir).glob(f"*/{packet_name}")):
        try:
            payload = read_json(path)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows

def _quality_bucket(overall: float, *, production_eligible: bool, gate_passed: bool) -> str:
    if not gate_passed or not production_eligible:
        return "disqualified"
    if overall >= 0.70:
        return "highQuality"
    if overall >= 0.55:
        return "acceptable"
    if overall >= MIN_PRODUCTION_SCORE:
        return "marginal"
    return "disqualified"

def _ratio(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0

def build_site_quality_distribution_report(
    *,
    vertical: str,
    site_id: str,
    batch_id: str,
) -> dict[str, Any]:
    root = site_supply_root(vertical, site_id, batch_id)
    blockers: list[str] = []
    warnings: list[str] = []
    try:
        frontier = _frontier_packet(vertical, site_id, batch_id)
    except Exception as exc:
        frontier = {}
        blockers.append(f"site_frontier_packet missing or unreadable: {exc}")
    profile = frontier.get("profile") if isinstance(frontier.get("profile"), Mapping) else {}
    controlled = profile.get("controlledTrial") if isinstance(profile.get("controlledTrial"), Mapping) else {}
    admission_mode = str(frontier.get("admissionMode") or ADMISSION_BATCH_CRAWL)
    validation_only = bool(controlled.get("validationOnly")) or admission_mode == ADMISSION_CONTROLLED_TRIAL
    publishable_assets_allowed = bool(controlled.get("publishableAssetsAllowed", True))
    commercial_blockers: list[str] = []
    if validation_only:
        commercial_blockers.append("controlledTrial.validationOnly=true")
    if admission_mode != ADMISSION_LICENSED_ASSET_INGEST and not bool(profile.get("fetchable")):
        commercial_blockers.append("fetchable=false")
    if admission_mode != ADMISSION_LICENSED_ASSET_INGEST and not bool(profile.get("crawlAllowed")):
        commercial_blockers.append("crawlAllowed=false")
    if not publishable_assets_allowed:
        commercial_blockers.append("publishableAssetsAllowed=false")
    if admission_mode == ADMISSION_LICENSED_ASSET_INGEST and str(profile.get("rightsPolicy") or "") not in {
        "licensed_asset_required",
        "commercial_license_required",
    }:
        commercial_blockers.append("licensed_asset_ingest requires authorized asset rights policy")

    candidates = _read_packet_rows(root, "candidates", "site_candidate_packet.json")
    scores = _read_packet_rows(root, "scores", "site_score_packet.json")
    maps = _read_packet_rows(root, "map", "site_map_packet.json")
    scores_by_ref = _by_ref(scores)
    maps_by_ref = _by_ref(maps)
    candidate_refs = {str(candidate.get("candidateRef") or "") for candidate in candidates if str(candidate.get("candidateRef") or "")}
    lane_counts: dict[str, int] = {}
    production_lane_counts: dict[str, int] = {}
    handoff_lane_counts: dict[str, int] = {}
    bucket_counts = {
        "highQuality": 0,
        "acceptable": 0,
        "marginal": 0,
        "disqualified": 0,
    }
    blocker_reasons: dict[str, int] = {}
    warning_reasons: dict[str, int] = {}
    score_values: list[float] = []
    production_eligible = 0
    handoff_eligible = 0

    if not candidates:
        blockers.append("quality report requires at least one site_candidate_packet")
    for reason in commercial_blockers:
        _bump(warning_reasons, reason)
    for candidate in candidates:
        ref = str(candidate.get("candidateRef") or "")
        lane = str(candidate.get("lane") or "unknown")
        _bump(lane_counts, lane)
        for reason in _packet_gate_reasons(candidate, "blockers"):
            _bump(blocker_reasons, reason)
        for reason in _packet_gate_reasons(candidate, "warnings"):
            _bump(warning_reasons, reason)
        score = scores_by_ref.get(ref)
        if score is None:
            bucket_counts["disqualified"] += 1
            _bump(blocker_reasons, "missing site_score_packet")
            continue
        for reason in _packet_gate_reasons(score, "blockers"):
            _bump(blocker_reasons, reason)
        for reason in _packet_gate_reasons(score, "warnings"):
            _bump(warning_reasons, reason)
        scores_payload = score.get("scores") if isinstance(score.get("scores"), Mapping) else {}
        overall = float(scores_payload.get("overall") or 0.0)
        score_values.append(overall)
        score_gate_passed = _packet_gate_passed(score)
        score_production_eligible = bool(score.get("productionEligible"))
        if score_production_eligible:
            production_eligible += 1
            _bump(production_lane_counts, lane)
        bucket_counts[_quality_bucket(overall, production_eligible=score_production_eligible, gate_passed=score_gate_passed)] += 1
        mapped = maps_by_ref.get(ref)
        if mapped is None:
            if score_production_eligible:
                _bump(blocker_reasons, "missing site_map_packet")
            continue
        for reason in _packet_gate_reasons(mapped, "blockers"):
            _bump(blocker_reasons, reason)
        for reason in _packet_gate_reasons(mapped, "warnings"):
            _bump(warning_reasons, reason)
        if bool((mapped.get("contentPlanHandoff") or {}).get("eligible")) and _packet_gate_passed(mapped):
            handoff_eligible += 1
            _bump(handoff_lane_counts, lane)

    for score_ref in sorted(set(scores_by_ref) - candidate_refs):
        _bump(blocker_reasons, f"{score_ref}: orphan site_score_packet")
    for map_ref in sorted(set(maps_by_ref) - set(scores_by_ref)):
        _bump(blocker_reasons, f"{map_ref}: orphan site_map_packet")

    total = len(candidates)
    commercial_ready = bool(total) and not commercial_blockers and not blockers
    if commercial_blockers:
        warnings.append("batch is quality-measurable but not commercial-publishable under current site profile")
    score_summary = {
        "min": round(min(score_values), 4) if score_values else 0.0,
        "avg": round(sum(score_values) / len(score_values), 4) if score_values else 0.0,
        "max": round(max(score_values), 4) if score_values else 0.0,
    }
    report = {
        "schemaVersion": QUALITY_DISTRIBUTION_SCHEMA,
        "vertical": vertical,
        "siteId": site_id,
        "batchId": batch_id,
        "workspaceRoot": str(root),
        "frontier": {
            "admissionMode": admission_mode,
            "articleCommercialAdmission": str(profile.get("articleCommercialAdmission") or ""),
            "validationOnly": validation_only,
            "publishableAssetsAllowed": publishable_assets_allowed,
            "fetchable": bool(profile.get("fetchable")),
            "crawlAllowed": bool(profile.get("crawlAllowed")),
            "rightsPolicy": str(profile.get("rightsPolicy") or ""),
        },
        "qualityFunnel": {
            "candidateCount": total,
            "laneCounts": lane_counts,
            "scoreCount": len(scores),
            "mapCount": len(maps),
            "productionEligibleCount": production_eligible,
            "productionEligibleLaneCounts": production_lane_counts,
            "contentPlanHandoffCount": handoff_eligible,
            "contentPlanHandoffLaneCounts": handoff_lane_counts,
            "successRate": _ratio(production_eligible, total),
            "handoffRate": _ratio(handoff_eligible, total),
        },
        "qualityDistribution": {
            "buckets": bucket_counts,
            "rates": {key: _ratio(value, total) for key, value in bucket_counts.items()},
            "score": score_summary,
        },
        "commercialReadiness": {
            "ready": commercial_ready,
            "decision": "go" if commercial_ready else "trial_only_or_blocked",
            "blockers": commercial_blockers,
        },
        "riskDistribution": {
            "blockerReasons": dict(sorted(blocker_reasons.items())),
            "warningReasons": dict(sorted(warning_reasons.items())),
        },
        "gate": _gate_report("quality_distribution", blockers, warnings),
        "createdAt": now_iso(),
    }
    return report

def write_site_quality_distribution_report(report: Mapping[str, Any]) -> Path:
    root = site_supply_root(str(report["vertical"]), str(report["siteId"]), str(report["batchId"]))
    path = root / "_shared" / "site_quality_distribution_report.json"
    write_json(path, dict(report))
    _write_stage_triplet(root, "quality_distribution", [str(path)], report["gate"])
    return path

def _runtime_batch_root(task_id: str, batch_id: str) -> Path:
    # 顶层批次工作区真相源：runtime/batches/<intentLabel>__<batch>/（不再挂任务根）。
    from _common.paths import batch_root

    return batch_root(task_id, batch_id)

def _publish_root() -> Path:
    from _common.paths import PUBLISH_ROOT

    return PUBLISH_ROOT

def _content_plan_packet_path(task_id: str, batch_id: str) -> Path:
    return _runtime_batch_root(task_id, batch_id) / "_shared" / "content_plan_packet.json"

def _content_object_index_path(task_id: str, batch_id: str) -> Path:
    return _runtime_batch_root(task_id, batch_id) / "_shared" / "content_object_index.json"

def _content_plan_matches_site(
    packet: Mapping[str, Any],
    *,
    vertical: str,
    site_id: str,
    batch_id: str,
) -> bool:
    source = packet.get("sourceSite") if isinstance(packet.get("sourceSite"), Mapping) else {}
    return (
        str(source.get("vertical") or "") == vertical
        and str(source.get("siteId") or "") == site_id
        and str(source.get("batchId") or "") == batch_id
    )

def _site_content_plan_report_source_site(
    shared: Path,
    *,
    vertical: str,
    site_id: str,
    batch_id: str,
    task_id: str,
    target_batch: str,
) -> dict[str, str] | None:
    report_path = shared / "site_supply_content_plan_report.json"
    if not report_path.is_file():
        return None
    try:
        report = read_json(report_path)
    except (OSError, ValueError, TypeError):
        return None
    gate = report.get("gate") if isinstance(report.get("gate"), Mapping) else {}
    if not gate.get("passed"):
        return None
    if (
        str(report.get("vertical") or "") != vertical
        or str(report.get("siteId") or "") != site_id
        or str(report.get("batchId") or "") != batch_id
        or str(report.get("taskId") or "") != task_id
        or str(report.get("targetBatch") or "") != target_batch
    ):
        return None
    return {"vertical": vertical, "siteId": site_id, "batchId": batch_id}

def repair_content_plan_source_site_provenance(
    *,
    vertical: str,
    site_id: str,
    batch_id: str,
    task_id: str,
    target_batch: str,
) -> bool:
    packet_path = _content_plan_packet_path(task_id, target_batch)
    if not packet_path.is_file():
        return False
    packet = read_json(packet_path)
    if not isinstance(packet, dict):
        return False
    if isinstance(packet.get("sourceSite"), Mapping):
        return False
    shared = _runtime_batch_root(task_id, target_batch) / "_shared"
    source_site = _site_content_plan_report_source_site(
        shared,
        vertical=vertical,
        site_id=site_id,
        batch_id=batch_id,
        task_id=task_id,
        target_batch=target_batch,
    )
    if not source_site:
        return False
    packet["sourceSite"] = source_site
    write_json(packet_path, packet)
    return True

def _post_refs_for_content_plan_batch(task_id: str, batch_id: str, packet: Mapping[str, Any]) -> list[str]:
    refs = [
        str(item.get("ref") or "").strip()
        for item in (packet.get("items") or [])
        if isinstance(item, Mapping) and str(item.get("ref") or "").strip()
    ]
    index = read_json(_content_object_index_path(task_id, batch_id)) if _content_object_index_path(task_id, batch_id).is_file() else {}
    coords_by_ref = index.get("refs") if isinstance(index.get("refs"), Mapping) else {}
    out: list[str] = []
    for ref in refs:
        coords = coords_by_ref.get(ref) if isinstance(coords_by_ref, Mapping) else None
        if not isinstance(coords, Mapping):
            continue
        content_type = str(coords.get("contentType") or "").strip()
        angle = str(coords.get("angle") or "").strip()
        title = str(coords.get("title") or "").strip()
        seq = int(coords.get("seq") or 1)
        if content_type and angle and title:
            out.append(f"posts/{content_type}/{angle}/{title}/{seq}")
    return sorted(dict.fromkeys(out))

def _publish_index_post_refs() -> set[str]:
    refs: set[str] = set()
    index_root = _publish_root() / "index" / "posts"
    if not index_root.is_dir():
        return refs
    for path in sorted(index_root.glob("*.ndjson")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ref = str(row.get("postRef") or "").strip()
            if ref:
                refs.add(ref)
    return refs

def _release_contract_post_refs(path: str | Path) -> tuple[bool, set[str]]:
    p = Path(path)
    if not p.is_file():
        return False, set()
    data = read_json(p)
    desired = data.get("desiredRefs") if isinstance(data.get("desiredRefs"), Mapping) else None
    if desired is None or not isinstance(desired.get("posts"), list):
        return False, set()
    return True, {str(ref).strip() for ref in desired.get("posts") or [] if str(ref).strip()}

def _sample_bundle_post_refs(env: str) -> set[str]:
    path = _publish_root() / "sample_bundles" / f"{env}.json"
    if not path.is_file():
        return set()
    data = read_json(path)
    return {str(ref) for ref in (data.get("posts") or []) if str(ref).strip()}

def _report_status_passed(path: str | Path, *, allow_dry_run: bool = False) -> bool:
    p = Path(path)
    if not p.is_file():
        return False
    data = read_json(p)
    status = str(data.get("status") or "").strip()
    if status in {"passed", "active"}:
        return True
    return allow_dry_run and status == "dry-run"

def build_downstream_e2e_report(
    *,
    vertical: str,
    site_id: str,
    batch_id: str,
    task_id: str,
    target_batch: str,
    env: str = "gamma",
    allow_dry_run_import: bool = False,
) -> dict[str, Any]:
    root = _runtime_batch_root(task_id, target_batch)
    shared = root / "_shared"
    packet_path = _content_plan_packet_path(task_id, target_batch)
    blockers: list[str] = []
    warnings: list[str] = []
    evidence_paths: list[str] = []
    packet: dict[str, Any] = {}
    if packet_path.is_file():
        packet = read_json(packet_path)
        evidence_paths.append(str(packet_path))
        if not _content_plan_matches_site(packet, vertical=vertical, site_id=site_id, batch_id=batch_id):
            blockers.append("content_plan sourceSite does not match requested site batch")
    else:
        blockers.append("content_plan_packet missing for downstream batch")

    planned_post_refs = _post_refs_for_content_plan_batch(task_id, target_batch, packet) if packet else []
    if not planned_post_refs:
        blockers.append("no content object post refs found for downstream batch")

    ship_path = shared / "ship_report.json"
    ship = read_json(ship_path) if ship_path.is_file() else {}
    if ship:
        evidence_paths.append(str(ship_path))
    else:
        blockers.append("ship_report.json missing")

    summaries = [row for row in (ship.get("summary") or []) if isinstance(row, Mapping)]
    env_summaries = [row for row in summaries if str(row.get("env") or "") == env]
    if not env_summaries:
        blockers.append(f"ship_report has no summary for env={env}")
    release_verified = False
    release_ref_contract_seen = False
    released_post_refs: set[str] = set()
    for row in env_summaries:
        contract_path = Path(str(row.get("releaseContract") or ""))
        consistency_path = Path(str(row.get("consistencyReport") or ""))
        if contract_path.is_file():
            evidence_paths.append(str(contract_path))
            ref_contract_seen, contract_refs = _release_contract_post_refs(contract_path)
            if ref_contract_seen:
                release_ref_contract_seen = True
                released_post_refs.update(contract_refs)
        if consistency_path.is_file():
            evidence_paths.append(str(consistency_path))
        if contract_path.is_file() and _report_status_passed(consistency_path):
            release_verified = True
    if not release_verified:
        blockers.append(f"release consistency evidence missing or failed for env={env}")
    post_refs = sorted(released_post_refs) if release_ref_contract_seen else planned_post_refs
    if not post_refs:
        blockers.append("no published post refs found after release gate")
    dropped_before_release = max(0, len(set(planned_post_refs)) - len(set(post_refs)))
    if release_ref_contract_seen and dropped_before_release:
        warnings.append(
            f"{dropped_before_release} content_plan object(s) did not pass publish gate; excluded from downstream visibility checks"
        )

    import_path = shared / f"{env}_import_report.json"
    import_report = read_json(import_path) if import_path.is_file() else {}
    import_verified = _report_status_passed(import_path, allow_dry_run=allow_dry_run_import)
    if import_path.is_file():
        evidence_paths.append(str(import_path))
    else:
        blockers.append(f"{env}_import_report.json missing")
    if not import_verified:
        blockers.append(f"import evidence missing or not active for env={env}")
    if allow_dry_run_import and str(import_report.get("status") or "") == "dry-run":
        warnings.append("import evidence is dry-run; acceptable only for controlled local rehearsal")

    indexed_refs = _publish_index_post_refs()
    bundle_refs = _sample_bundle_post_refs(env)
    missing_index = sorted(set(post_refs) - indexed_refs)
    missing_bundle = sorted(set(post_refs) - bundle_refs)
    if missing_index:
        blockers.append(f"publish index missing post ref(s): {missing_index[:5]}")
    current_bundle_visible = bool(post_refs) and not missing_bundle
    if missing_bundle:
        message = f"sample bundle {env} missing post ref(s): {missing_bundle[:5]}"
        if release_ref_contract_seen and release_verified:
            warnings.append(
                message
                + "; current mutable sample bundle may point at another isolated release, "
                + "archived release contract is used for historical visibility evidence"
            )
        else:
            blockers.append(message)
    search_visible = bool(post_refs) and not missing_index and (
        current_bundle_visible or (release_ref_contract_seen and release_verified)
    )

    counts = import_report.get("counts") if isinstance(import_report.get("counts"), Mapping) else {}
    feed_upserted = int(counts.get("feedUpserted") or 0)
    recommendation_ready = bool(import_verified and (feed_upserted >= len(post_refs) or allow_dry_run_import))
    if not recommendation_ready:
        blockers.append("recommendation cold-start/feed import evidence missing")

    report = {
        "schemaVersion": DOWNSTREAM_E2E_SCHEMA,
        "vertical": vertical,
        "siteId": site_id,
        "sourceBatchId": batch_id,
        "taskId": task_id,
        "targetBatch": target_batch,
        "env": env,
        "postRefs": post_refs,
        "plannedPostRefs": planned_post_refs,
        "releasedPostRefs": post_refs,
        "plannedPostRefCount": len(planned_post_refs),
        "releasedPostRefCount": len(post_refs),
        "droppedBeforeReleaseCount": dropped_before_release,
        "checks": {
            "releaseVerified": release_verified,
            "importVerified": import_verified,
            "searchVisible": search_visible,
            "currentSampleBundleVisible": current_bundle_visible,
            "recommendationFeedbackReady": recommendation_ready,
        },
        "importStatus": str(import_report.get("status") or ""),
        "importCounts": dict(counts),
        "evidencePaths": sorted(dict.fromkeys(evidence_paths)),
        "gate": _gate_report("ship_import", blockers, warnings),
        "createdAt": now_iso(),
    }
    return report

def write_downstream_e2e_report(report: Mapping[str, Any]) -> Path:
    task_id = str(report["taskId"])
    target_batch = str(report["targetBatch"])
    path = _runtime_batch_root(task_id, target_batch) / "_shared" / "site_supply_downstream_e2e_report.json"
    payload = dict(report)
    payload["reportPath"] = str(path)
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    if path.is_file() and not bool(gate.get("passed")):
        try:
            previous = read_json(path)
        except Exception:
            previous = {}
        previous_gate = previous.get("gate") if isinstance(previous.get("gate"), Mapping) else {}
        if bool(previous_gate.get("passed")):
            failed_path = path.with_name("site_supply_downstream_e2e_report_last_failed.json")
            payload["reportPath"] = str(failed_path)
            write_json(failed_path, payload)
            return failed_path
    write_json(path, payload)
    root = site_supply_root(str(report["vertical"]), str(report["siteId"]), str(report["sourceBatchId"]))
    outputs = [str(path)] + [str(p) for p in (payload.get("evidencePaths") or [])]
    _write_stage_triplet_append_outputs(root, "ship_import", outputs, payload["gate"])
    return path

def _iter_downstream_e2e_reports(vertical: str, site_id: str, batch_id: str) -> list[dict[str, Any]]:
    from _common.paths import batches_root

    root = batches_root()
    if not root.is_dir():
        return []
    reports: list[dict[str, Any]] = []
    # 顶层 runtime/batches/<intentLabel>__<batch>/_shared/...（不再扫任务根 batches/）。
    for path in sorted(root.glob("*/_shared/site_supply_downstream_e2e_report.json")):
        try:
            report = read_json(path)
        except Exception:
            continue
        if (
            str(report.get("vertical") or "") == vertical
            and str(report.get("siteId") or "") == site_id
            and str(report.get("sourceBatchId") or "") == batch_id
        ):
            reports.append(report)
    return reports

def _downstream_readiness_from_reports(vertical: str, site_id: str, batch_id: str) -> dict[str, bool]:
    reports = [
        report
        for report in _iter_downstream_e2e_reports(vertical, site_id, batch_id)
        if bool((report.get("gate") or {}).get("passed"))
    ]
    if not reports:
        return {
            "releaseVerified": False,
            "importVerified": False,
            "searchVisible": False,
            "recommendationFeedbackReady": False,
        }
    checks = [report.get("checks") if isinstance(report.get("checks"), Mapping) else {} for report in reports]
    return {
        "releaseVerified": any(bool(row.get("releaseVerified")) for row in checks),
        "importVerified": any(bool(row.get("importVerified")) for row in checks),
        "searchVisible": any(bool(row.get("searchVisible")) for row in checks),
        "recommendationFeedbackReady": any(bool(row.get("recommendationFeedbackReady")) for row in checks),
    }

def build_site_rollup_report(
    *,
    vertical: str,
    site_id: str,
    batch_id: str,
    objects_per_hour: float = 0.0,
    first_pass_rate: float | None = None,
    token_ledger_count: int = 0,
    release_verified: bool = False,
    import_verified: bool = False,
    search_visible: bool = False,
    recommendation_feedback_ready: bool = False,
    http_429_count: int = 0,
    http_403_count: int = 0,
    probe_page_count: int = 0,
    empty_extract_count: int = 0,
    duplicate_count: int = 0,
    dead_letter_count: int = 0,
) -> dict[str, Any]:
    root = site_supply_root(vertical, site_id, batch_id)
    frontier = _frontier_packet(vertical, site_id, batch_id)
    fetch_paths = sorted((root / "fetches").glob("*/site_fetch_packet.json"))
    candidate_paths = sorted((root / "candidates").glob("*/site_candidate_packet.json"))
    score_paths = sorted((root / "scores").glob("*/site_score_packet.json"))
    map_paths = sorted((root / "map").glob("*/site_map_packet.json"))
    fetches = [read_json(path) for path in fetch_paths]
    candidates = [read_json(path) for path in candidate_paths]
    scores = [read_json(path) for path in score_paths]
    maps = [read_json(path) for path in map_paths]
    scores_by_ref = _by_ref(scores)
    maps_by_ref = _by_ref(maps)
    candidates_by_ref = _by_ref(candidates)
    lane_counts: dict[str, int] = {}
    production_lane_counts: dict[str, int] = {}
    handoff_lane_counts: dict[str, int] = {}
    for candidate in candidates:
        lane = str(candidate.get("lane") or "unknown")
        _bump(lane_counts, lane)
    for score in scores:
        if score.get("productionEligible"):
            _bump(production_lane_counts, str(score.get("lane") or "unknown"))
    for mapped in maps:
        if not ((mapped.get("contentPlanHandoff") or {}).get("eligible")):
            continue
        ref = str(mapped.get("candidateRef") or "")
        candidate = candidates_by_ref.get(ref, {})
        lane = str(candidate.get("lane") or mapped.get("targetContentType") or "unknown")
        _bump(handoff_lane_counts, lane)
    production_eligible = sum(1 for s in scores if s.get("productionEligible"))
    handoff_count = sum(1 for m in maps if ((m.get("contentPlanHandoff") or {}).get("eligible")))
    entity_handoff_count = 0
    unresolved_entity_mention_count = 0
    topic_candidate_count = 0
    for mapped in maps:
        if not ((mapped.get("contentPlanHandoff") or {}).get("eligible")):
            continue
        gaps = mapped.get("knowledgeGaps") if isinstance(mapped.get("knowledgeGaps"), Mapping) else {}
        if gaps.get("entityHomepageCandidates"):
            entity_handoff_count += 1
        unresolved_entity_mention_count += len(gaps.get("unresolvedEntityMentions") or [])
        topic_candidate_count += len(gaps.get("topicCandidates") or [])
    blockers: list[str] = []
    warnings: list[str] = []
    total = len(candidates)
    if not frontier.get("gate", {}).get("passed"):
        blockers.append("site_frontier gate failed")
    if total <= 0:
        blockers.append("site rollup requires at least one candidate")
    stage_failures = {
        "site_fetch": 0,
        "site_extract": 0,
        "site_score": 0,
        "site_map": 0,
        "missing_candidate_after_fetch": 0,
        "missing_score": 0,
        "missing_map": 0,
        "orphan_score": 0,
        "orphan_map": 0,
        "missing_object_evidence": 0,
    }
    candidate_refs = {str(c.get("candidateRef") or "") for c in candidates if str(c.get("candidateRef") or "")}
    fetch_pass_refs: set[str] = set()
    for fetched in fetches:
        ref = str(fetched.get("candidateRef") or "<missing>")
        missing_fetch = _object_triplet_missing(root / "fetches" / ref)
        if missing_fetch:
            stage_failures["missing_object_evidence"] += 1
            blockers.append(f"{ref}: missing site_fetch object evidence {missing_fetch}")
        if _packet_gate_passed(fetched):
            fetch_pass_refs.add(ref)
        else:
            stage_failures["site_fetch"] += 1
    for ref in sorted(fetch_pass_refs - candidate_refs):
        stage_failures["missing_candidate_after_fetch"] += 1
        blockers.append(f"{ref}: site_fetch passed but site_candidate_packet is missing")
    for candidate in candidates:
        ref = str(candidate.get("candidateRef") or "<missing>")
        missing = _object_triplet_missing(root / "candidates" / ref)
        if missing:
            stage_failures["missing_object_evidence"] += 1
            blockers.append(f"{ref}: missing site_extract object evidence {missing}")
        if not _packet_gate_passed(candidate):
            stage_failures["site_extract"] += 1
            blockers.append(f"{ref}: site_extract gate failed; repair at site_extract")
            continue
        score = scores_by_ref.get(ref)
        if score is None:
            stage_failures["missing_score"] += 1
            blockers.append(f"{ref}: missing site_score_packet; re-inject at site_score")
            continue
        missing_score = _object_triplet_missing(root / "scores" / ref)
        if missing_score:
            stage_failures["missing_object_evidence"] += 1
            blockers.append(f"{ref}: missing site_score object evidence {missing_score}")
        if not _packet_gate_passed(score):
            stage_failures["site_score"] += 1
            continue
        if score.get("productionEligible"):
            mapped = maps_by_ref.get(ref)
            if mapped is None:
                stage_failures["missing_map"] += 1
                blockers.append(f"{ref}: missing site_map_packet; re-inject at site_map")
                continue
            missing_map = _object_triplet_missing(root / "map" / ref)
            if missing_map:
                stage_failures["missing_object_evidence"] += 1
                blockers.append(f"{ref}: missing site_map object evidence {missing_map}")
            if not _packet_gate_passed(mapped):
                stage_failures["site_map"] += 1
                blockers.append(f"{ref}: site_map gate failed; repair at site_map")
            elif not ((mapped.get("contentPlanHandoff") or {}).get("eligible")):
                stage_failures["site_map"] += 1
                blockers.append(f"{ref}: site_map did not produce eligible content_plan handoff")
    for ref in sorted(set(scores_by_ref) - candidate_refs):
        stage_failures["orphan_score"] += 1
        blockers.append(f"{ref}: orphan site_score_packet without candidate")
    for ref in sorted(set(maps_by_ref) - set(scores_by_ref)):
        stage_failures["orphan_map"] += 1
        blockers.append(f"{ref}: orphan site_map_packet without score")
    for mapped in maps:
        ref = str(mapped.get("candidateRef") or "<missing>")
        if ((mapped.get("contentPlanHandoff") or {}).get("eligible")) and not scores_by_ref.get(ref, {}).get("productionEligible"):
            stage_failures["site_map"] += 1
            blockers.append(f"{ref}: site_map handoff is eligible without productionEligible score")
    stability_denominator = len(fetches) or total
    if stability_denominator:
        if dead_letter_count / stability_denominator > MAX_DEAD_LETTER_RATE:
            blockers.append(f"deadLetter rate exceeds {MAX_DEAD_LETTER_RATE:.0%}")
        if (http_429_count + http_403_count) / stability_denominator > MAX_THROTTLE_FORBIDDEN_RATE:
            blockers.append(f"site throttle/forbidden rate exceeds {MAX_THROTTLE_FORBIDDEN_RATE:.0%}")
        if probe_page_count / stability_denominator > MAX_PROBE_PAGE_RATE:
            blockers.append(f"probe page rate exceeds {MAX_PROBE_PAGE_RATE:.0%}")
        if empty_extract_count / stability_denominator > MAX_EMPTY_EXTRACT_RATE:
            blockers.append(f"empty extract rate exceeds {MAX_EMPTY_EXTRACT_RATE:.0%}")
        if duplicate_count / stability_denominator > 0.40:
            warnings.append("duplicate rate exceeds 40%; keep dedupe budget visible before expansion")
    elif dead_letter_count:
        blockers.append(f"deadLetterCount present without fetch/candidate denominator; got {dead_letter_count}")
    if production_eligible and handoff_count < production_eligible:
        blockers.append("all productionEligible candidates must have site_map handoff packets")
    target_count = int(((frontier.get("frontier") or {}).get("targetCount")) or 0)
    if target_count and handoff_count < target_count:
        blockers.append(f"contentPlanHandoffCount {handoff_count} < targetCount {target_count}")
    report = {
        "schemaVersion": ROLLUP_SCHEMA,
        "vertical": vertical,
        "siteId": site_id,
        "batchId": batch_id,
        "passed": not blockers,
        "decision": "go" if not blockers else "no_go",
        "workspaceRoot": str(root),
        "frontier": {
            "admissionMode": frontier.get("admissionMode") or ADMISSION_BATCH_CRAWL,
            "profile": frontier.get("profile") or {},
            "queuePolicy": frontier.get("queuePolicy") or {},
            "timeWindow": frontier.get("timeWindow") or {},
        },
        "siteFunnel": {
            "frontierReady": bool(frontier.get("gate", {}).get("passed")),
            "fetchCount": len(fetches),
            "fetchGatePassedCount": len(fetch_pass_refs),
            "candidateCount": total,
            "laneCounts": lane_counts,
            "scoreCount": len(scores),
            "productionEligibleCount": production_eligible,
            "productionEligibleLaneCounts": production_lane_counts,
            "contentPlanHandoffCount": handoff_count,
            "entityMappedContentPlanHandoffCount": entity_handoff_count,
            "unresolvedEntityMentionCount": unresolved_entity_mention_count,
            "topicCandidateCount": topic_candidate_count,
            "contentPlanHandoffLaneCounts": handoff_lane_counts,
            "blockedCount": max(0, len(scores) - production_eligible),
            "http429Count": int(http_429_count),
            "http403Count": int(http_403_count),
            "probePageCount": int(probe_page_count),
            "emptyExtractCount": int(empty_extract_count),
            "duplicateCount": int(duplicate_count),
            "deadLetterCount": int(dead_letter_count),
            "stageFailures": stage_failures,
        },
        "executionReadiness": {
            "queueBackend": ((frontier.get("queuePolicy") or {}).get("backend")) or "",
            "measuredThroughput": {"objectsPerHour": float(objects_per_hour)},
            "firstPassRate": first_pass_rate,
            "tokenLedgerCount": int(token_ledger_count),
            "releaseVerified": bool(release_verified),
            "importVerified": bool(import_verified),
            "searchVisible": bool(search_visible),
            "recommendationFeedbackReady": bool(recommendation_feedback_ready),
        },
        "blockers": blockers,
        "warnings": warnings,
        "createdAt": now_iso(),
    }
    return report

def write_site_rollup_report(report: Mapping[str, Any]) -> Path:
    root = site_supply_root(str(report["vertical"]), str(report["siteId"]), str(report["batchId"]))
    path = root / "_shared" / "site_rollup_report.json"
    write_json(path, dict(report))
    _write_stage_triplet(root, "site_rollup", [str(path)], _gate_report("site_rollup", list(report.get("blockers") or []), list(report.get("warnings") or [])))
    return path

def _print(payload: Mapping[str, Any]) -> None:
    print(json.dumps(dict(payload), ensure_ascii=False, indent=2))

__all__ = [name for name in globals() if not name.startswith("__")]
