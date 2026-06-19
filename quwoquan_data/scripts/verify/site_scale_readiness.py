"""Site-dimensional 100k/day scale readiness gate."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from _common.io import read_json, write_json
from _common.paths import RUNTIME_ROOT


SCHEMA = "quwoquan_data.site_scale_readiness/1"
DEFAULT_DAILY_TARGET = 100_000
MIN_FIRST_PASS_RATE = 0.70
ADMISSION_CONTROLLED_TRIAL = "controlled_trial"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _count_map(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return {str(k): _safe_int(v) for k, v in value.items()}


def _merge_counts(rows: list[Mapping[str, Any]], key: str) -> dict[str, int]:
    merged: dict[str, int] = {}
    for row in rows:
        for lane, count in _count_map(row.get(key)).items():
            merged[lane] = merged.get(lane, 0) + count
    return merged


def _site_supply_batch_root(vertical: str, site_id: str, batch_id: str) -> Path:
    return RUNTIME_ROOT / "site_supply" / vertical / site_id / batch_id


def _iter_site_batch_roots(vertical: str, batch_id: str, site_id: str | None = None) -> list[Path]:
    if site_id:
        root = _site_supply_batch_root(vertical, site_id, batch_id)
        return [root] if root.exists() else []
    base = RUNTIME_ROOT / "site_supply" / vertical
    if not base.is_dir():
        return []
    return sorted(path / batch_id for path in base.iterdir() if path.is_dir() and (path / batch_id).exists())


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = read_json(path)
    return data if isinstance(data, dict) else {}


def _stage_triplet_missing(root: Path, stage: str) -> list[str]:
    missing = []
    for name in ("stage_result.json", "gate_report.json", "repair_report.json"):
        if not (root / stage / name).is_file():
            missing.append(f"{stage}/{name}")
    return missing


def _site_report(root: Path) -> dict[str, Any]:
    frontier = _load_json(root / "site_frontier" / "site_frontier_packet.json")
    rollup = _load_json(root / "_shared" / "site_rollup_report.json")
    site_id = str((frontier.get("siteId") or rollup.get("siteId") or root.parent.name))
    batch_id = str((frontier.get("batchId") or rollup.get("batchId") or root.name))
    vertical = str((frontier.get("vertical") or rollup.get("vertical") or root.parent.parent.name))
    frontier_passed = bool((frontier.get("gate") or {}).get("passed"))
    stages_to_check = ("site_frontier", "site_extract", "site_score", "site_map", "site_rollup") if frontier_passed else ("site_frontier",)
    missing = []
    for stage in stages_to_check:
        missing.extend(_stage_triplet_missing(root, stage))
    funnel = rollup.get("siteFunnel") if isinstance(rollup.get("siteFunnel"), Mapping) else {}
    execution = rollup.get("executionReadiness") if isinstance(rollup.get("executionReadiness"), Mapping) else {}
    profile = ((rollup.get("frontier") or {}).get("profile") or frontier.get("profile") or {})
    queue = ((rollup.get("frontier") or {}).get("queuePolicy") or frontier.get("queuePolicy") or {})
    admission_mode = str(((rollup.get("frontier") or {}).get("admissionMode") or frontier.get("admissionMode") or "batch_crawl"))
    first_pass = execution.get("firstPassRate")
    first_pass_rate = None if first_pass in (None, "") else _safe_float(first_pass)
    return {
        "vertical": vertical,
        "siteId": site_id,
        "batchId": batch_id,
        "root": str(root),
        "frontierPresent": bool(frontier),
        "rollupPresent": bool(rollup),
        "frontierPassed": frontier_passed,
        "frontierBlockers": list(((frontier.get("gate") or {}).get("blockers")) or []),
        "frontierWarnings": list(((frontier.get("gate") or {}).get("warnings")) or []),
        "rollupPassed": bool(rollup.get("passed")),
        "profile": profile,
        "admissionMode": admission_mode,
        "queueBackend": str(queue.get("backend") or execution.get("queueBackend") or ""),
        "siteFunnel": funnel,
        "executionReadiness": execution,
        "firstPassRate": first_pass_rate,
        "objectsPerHour": _safe_float((execution.get("measuredThroughput") or {}).get("objectsPerHour")),
        "tokenLedgerCount": _safe_int(execution.get("tokenLedgerCount")),
        "releaseVerified": bool(execution.get("releaseVerified")),
        "importVerified": bool(execution.get("importVerified")),
        "searchVisible": bool(execution.get("searchVisible")),
        "recommendationFeedbackReady": bool(execution.get("recommendationFeedbackReady")),
        "candidateCount": _safe_int(funnel.get("candidateCount")),
        "candidateLaneCounts": _count_map(funnel.get("laneCounts")),
        "productionEligibleLaneCounts": _count_map(funnel.get("productionEligibleLaneCounts")),
        "contentPlanHandoffCount": _safe_int(funnel.get("contentPlanHandoffCount")),
        "contentPlanHandoffLaneCounts": _count_map(funnel.get("contentPlanHandoffLaneCounts")),
        "deadLetterCount": _safe_int(funnel.get("deadLetterCount")),
        "http429Count": _safe_int(funnel.get("http429Count")),
        "http403Count": _safe_int(funnel.get("http403Count")),
        "probePageCount": _safe_int(funnel.get("probePageCount")),
        "emptyExtractCount": _safe_int(funnel.get("emptyExtractCount")),
        "missingStageEvidence": missing,
        "blockers": list(rollup.get("blockers") or []),
        "warnings": list(rollup.get("warnings") or []),
    }


def build_site_scale_readiness_report(
    *,
    vertical: str,
    batch_id: str,
    site_id: str | None = None,
    daily_target: int = DEFAULT_DAILY_TARGET,
    require_import: bool = True,
    mode: str = "commercial",
    min_lane_counts: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    mode = "trial" if str(mode or "").strip() == "trial" else "commercial"
    roots = _iter_site_batch_roots(vertical, batch_id, site_id=site_id)
    sites = [_site_report(root) for root in roots]
    blockers: list[str] = []
    warnings: list[str] = []
    if not sites:
        blockers.append("no site_supply rollup found for vertical/batch")

    total_throughput = sum(_safe_float(site.get("objectsPerHour")) for site in sites)
    total_candidates = sum(_safe_int(site.get("candidateCount")) for site in sites)
    total_handoff = sum(_safe_int(site.get("contentPlanHandoffCount")) for site in sites)
    total_token_ledgers = sum(_safe_int(site.get("tokenLedgerCount")) for site in sites)
    total_candidate_lane_counts = _merge_counts(sites, "candidateLaneCounts")
    total_handoff_lane_counts = _merge_counts(sites, "contentPlanHandoffLaneCounts")
    required_per_hour = int(daily_target) / 24
    frontier_passed_count = sum(1 for site in sites if site.get("frontierPassed"))

    for site in sites:
        prefix = f"{site['siteId']}: "
        if not site.get("frontierPresent"):
            blockers.append(prefix + "missing site_frontier_packet")
        if not site.get("frontierPassed"):
            blockers.append(prefix + "site_frontier gate did not pass")
            blockers.extend(prefix + str(item) for item in (site.get("frontierBlockers") or []))
            warnings.extend(prefix + str(item) for item in (site.get("frontierWarnings") or []))
            if site.get("missingStageEvidence"):
                blockers.append(prefix + "missing frontier stage evidence: " + ",".join(site["missingStageEvidence"]))
            continue
        if not site.get("rollupPresent"):
            blockers.append(prefix + "missing site_rollup_report")
        if not site.get("rollupPassed"):
            blockers.append(prefix + "site_rollup gate did not pass")
        if int(daily_target) >= DEFAULT_DAILY_TARGET and site.get("queueBackend") != "reliabletask":
            blockers.append(prefix + "daily target >=100000 requires queueBackend=reliabletask")
        profile = site.get("profile") if isinstance(site.get("profile"), Mapping) else {}
        admission_mode = str(site.get("admissionMode") or "batch_crawl")
        if admission_mode == ADMISSION_CONTROLLED_TRIAL and mode == "commercial":
            blockers.append(prefix + "controlled_trial cannot satisfy commercial source crawl readiness")
        if admission_mode != ADMISSION_CONTROLLED_TRIAL and (not profile.get("fetchable") or not profile.get("crawlAllowed")):
            blockers.append(prefix + "site profile is not fetchable+crawlAllowed")
        if site.get("missingStageEvidence"):
            blockers.append(prefix + "missing stage evidence: " + ",".join(site["missingStageEvidence"]))
        if _safe_int(site.get("deadLetterCount")):
            blockers.append(prefix + f"deadLetterCount={site['deadLetterCount']}")
        if _safe_int(site.get("candidateCount")) <= 0:
            blockers.append(prefix + "candidateCount must be > 0")
        if _safe_int(site.get("contentPlanHandoffCount")) <= 0:
            blockers.append(prefix + "contentPlanHandoffCount must be > 0")
        if _safe_int(site.get("tokenLedgerCount")) <= 0:
            blockers.append(prefix + "TokenLedger evidence missing")
        first_pass = site.get("firstPassRate")
        if first_pass is None:
            blockers.append(prefix + "firstPassRate evidence missing")
        elif _safe_float(first_pass) < MIN_FIRST_PASS_RATE:
            blockers.append(prefix + f"firstPassRate {_safe_float(first_pass):.2%} < {MIN_FIRST_PASS_RATE:.0%}")
        if mode == "commercial":
            if not bool(site.get("releaseVerified")):
                blockers.append(prefix + "release verification evidence missing")
            if require_import and not bool(site.get("importVerified")):
                blockers.append(prefix + "import evidence missing")
            if not bool(site.get("searchVisible")):
                blockers.append(prefix + "search visibility evidence missing")
            if not bool(site.get("recommendationFeedbackReady")):
                blockers.append(prefix + "recommendation feedback evidence missing")
        else:
            if not bool(site.get("releaseVerified")):
                warnings.append(prefix + "trial mode: release verification evidence missing")
            if require_import and not bool(site.get("importVerified")):
                warnings.append(prefix + "trial mode: import evidence missing")
            if not bool(site.get("searchVisible")):
                warnings.append(prefix + "trial mode: search visibility evidence missing")
            if not bool(site.get("recommendationFeedbackReady")):
                warnings.append(prefix + "trial mode: recommendation feedback evidence missing")
        warnings.extend(f"{site['siteId']}: {w}" for w in (site.get("warnings") or []))
        blockers.extend(f"{site['siteId']}: {b}" for b in (site.get("blockers") or []))

    if sites and frontier_passed_count <= 0:
        warnings.append("no site passed site_frontier; downstream scale readiness was not evaluated")
    elif sites:
        if total_throughput < required_per_hour:
            blockers.append(
                f"measured site throughput {total_throughput:.4f} objects/hour "
                f"< required {required_per_hour:.4f} objects/hour"
            )
        if total_handoff <= 0:
            blockers.append("no content_plan handoff candidates across site supply rollups")
    if frontier_passed_count and total_candidates and int(daily_target) / max(total_candidates, 1) > 1000:
        warnings.append("site trial sample is too small to extrapolate linearly to requested daily target")
    for lane, required in (min_lane_counts or {}).items():
        required_count = _safe_int(required)
        if required_count <= 0:
            continue
        actual = _safe_int(total_handoff_lane_counts.get(str(lane)))
        if actual < required_count:
            blockers.append(f"contentPlanHandoffLaneCounts.{lane} {actual} < required {required_count}")

    return {
        "schemaVersion": SCHEMA,
        "vertical": vertical,
        "batchId": batch_id,
        "siteId": site_id or "",
        "mode": mode,
        "dailyTarget": int(daily_target),
        "passed": not blockers,
        "decision": "go" if not blockers else "no_go",
        "requiredThroughputPerHour": round(required_per_hour, 4),
        "aggregate": {
            "siteCount": len(sites),
            "candidateCount": total_candidates,
            "contentPlanHandoffCount": total_handoff,
            "candidateLaneCounts": total_candidate_lane_counts,
            "contentPlanHandoffLaneCounts": total_handoff_lane_counts,
            "tokenLedgerCount": total_token_ledgers,
            "measuredThroughputObjectsPerHour": round(total_throughput, 4),
        },
        "sites": sites,
        "blockers": blockers,
        "warnings": warnings,
    }


def write_site_scale_readiness_report(path: Path, report: Mapping[str, Any]) -> None:
    write_json(path, dict(report))
