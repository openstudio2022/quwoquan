"""Commercial scale readiness gate for managed content batches.

The gate is intentionally conservative: a batch that cannot prove source
sufficiency, token/cost accounting, queue backend, release, and import evidence
is a No-Go for scale even when some early lane checks passed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from _common.download_diagnostics import download_diagnostics
from _common.io import read_json, write_json
from _common.paths import batch_root, release_root


SCHEMA = "quwoquan_data.scale_readiness"
DEFAULT_DAILY_TARGET = 10_000
MIN_SOURCE_SUFFICIENCY = 0.98
MIN_FIRST_PASS_RATE = 0.70


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = read_json(path)
    except (OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _quotas(spec: Mapping[str, Any]) -> dict[str, int]:
    raw = ((spec.get("content") or {}).get("quotas") or {})
    return {
        "homepage": _safe_int(raw.get("entityHomepagesPerTarget")),
        "article": _safe_int(raw.get("entityArticlesPerTarget") or raw.get("entityArticles")),
        "image": _safe_int(raw.get("imageWorksPerTarget") or raw.get("galleryPostsPerTarget") or raw.get("galleryPosts")),
        "routeArticle": _safe_int(raw.get("routeArticles")),
    }


def _target_count(spec: Mapping[str, Any], audit: Mapping[str, Any]) -> int:
    count = _safe_int(audit.get("targetCount"))
    if count:
        return count
    targets = ((spec.get("scope") or {}).get("coverageTargets") or [])
    return len(targets) if isinstance(targets, list) else 0


def _expected_objects(spec: Mapping[str, Any], audit: Mapping[str, Any]) -> dict[str, int]:
    count = _target_count(spec, audit)
    quotas = _quotas(spec)
    return {
        "homepage": count * quotas["homepage"],
        "article": count * quotas["article"],
        "image": count * quotas["image"],
        "routeArticle": quotas["routeArticle"],
        "total": count * (quotas["homepage"] + quotas["article"] + quotas["image"]) + quotas["routeArticle"],
    }


def _lane_rates(audit: Mapping[str, Any], target_count: int) -> dict[str, dict[str, float | int]]:
    rows: dict[str, dict[str, float | int]] = {}
    passed = audit.get("lanePassed") or {}
    for lane in ("homepage", "article", "image"):
        value = _safe_int(passed.get(lane) if isinstance(passed, Mapping) else 0)
        rows[lane] = {
            "passed": value,
            "targetCount": target_count,
            "rate": round(value / target_count, 4) if target_count else 0.0,
        }
    return rows


def _token_ledger_paths(root: Path) -> list[str]:
    names = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        lowered = path.name.lower()
        if "token" in lowered and "ledger" in lowered and path.suffix == ".json":
            names.append(str(path))
    return names


def _release_exists(release_id: str | None) -> bool:
    if not release_id:
        return False
    return (release_root(release_id) / "release_manifest.json").is_file()


def _import_evidence_paths(root: Path) -> list[str]:
    candidates = []
    for path in [
        root / "_shared" / "import_report.json",
        root / "_shared" / "ship_report.json",
        root / "_shared" / "staging_import_report.json",
        root / "_shared" / "gamma_import_report.json",
    ]:
        if path.is_file():
            candidates.append(str(path))
    return candidates


def build_scale_readiness_report(
    task_id: str,
    batch_id: str,
    *,
    daily_target: int = DEFAULT_DAILY_TARGET,
    release_id: str | None = None,
    require_import: bool = True,
) -> dict[str, Any]:
    from task import store
    from task.target_selection import audit_managed_batch

    spec = store.load_spec(task_id)
    root = batch_root(task_id, batch_id)
    audit = audit_managed_batch(task_id, batch_id)
    state = _load_json_if_exists(root / "_shared" / "task_workflow_state.json")
    expected = _expected_objects(spec, audit)
    targets = _target_count(spec, audit)
    lanes = _lane_rates(audit, targets)
    token_ledgers = _token_ledger_paths(root)
    import_paths = _import_evidence_paths(root)
    download_report = download_diagnostics(root)
    content = spec.get("content") or {}
    research = content.get("research") or {}
    queue_backend = (
        (spec.get("queuePolicy") or {}).get("backend")
        or (content.get("queuePolicy") or {}).get("backend")
        or content.get("queueBackend")
        or spec.get("queueBackend")
    )
    max_concurrency = _safe_int(research.get("maxConcurrency") or spec.get("maxConcurrency"))

    blockers: list[str] = []
    warnings: list[str] = []

    status = str(state.get("status") or "")
    if status != "succeeded":
        blockers.append(f"workflow status must be succeeded for scale; got {status or 'missing'}")
    waiting = str(state.get("waitingCheckpoint") or "")
    if waiting:
        blockers.append(f"workflow still waits at checkpoint: {waiting}")
    failed_count = _safe_int(audit.get("failedLaneCount"))
    if failed_count:
        blockers.append(f"managed batch audit has failedLaneCount={failed_count}")
    for lane, row in lanes.items():
        rate = float(row["rate"])
        if targets and rate < MIN_SOURCE_SUFFICIENCY:
            blockers.append(f"{lane} lane source sufficiency {rate:.2%} < {MIN_SOURCE_SUFFICIENCY:.0%}")
    if daily_target >= 10_000 and queue_backend != "reliabletask":
        blockers.append("daily target >=10000 requires queueBackend=reliabletask")
    if daily_target >= 10_000 and max_concurrency < 10:
        blockers.append("daily target >=10000 requires measured maxConcurrency >=10 for trial admission")
    if not token_ledgers:
        blockers.append("TokenLedger evidence missing; cannot project unit token/cost or cache hit rate")
    if not release_id or not _release_exists(release_id):
        blockers.append("isolated release evidence missing; release verify cannot be proven")
    if require_import and not import_paths:
        blockers.append("staging/gamma import or ship evidence missing")
    if not state.get("throughput"):
        blockers.append("measured throughput evidence missing; cannot project daily capacity")
    if expected["total"] <= 0:
        blockers.append("expected content object count is zero")
    if expected["total"] and daily_target / max(expected["total"], 1) > 1000:
        warnings.append("trial sample is too small to extrapolate linearly to requested daily target")

    # When workflow is successful, first-pass rate should come from review/import
    # counters.  Without it, keep scale blocked above via throughput/token/release
    # and record the missing value explicitly.
    first_pass_rate = None
    quality = state.get("quality") if isinstance(state.get("quality"), Mapping) else {}
    if isinstance(quality, Mapping) and "firstPassRate" in quality:
        try:
            first_pass_rate = float(quality.get("firstPassRate"))
        except (TypeError, ValueError):
            first_pass_rate = None
    if first_pass_rate is not None and first_pass_rate < MIN_FIRST_PASS_RATE:
        blockers.append(f"firstPassRate {first_pass_rate:.2%} < {MIN_FIRST_PASS_RATE:.0%}")
    elif first_pass_rate is None:
        blockers.append("firstPassRate evidence missing")

    return {
        "schemaVersion": SCHEMA,
        "taskId": task_id,
        "batchId": batch_id,
        "dailyTarget": int(daily_target),
        "passed": not blockers,
        "decision": "go" if not blockers else "no_go",
        "expectedObjects": expected,
        "sourceSufficiency": lanes,
        "workflowState": {
            key: state.get(key)
            for key in ("status", "waitingCheckpoint", "nextAction", "retryCounts", "infrastructureRetryCounts", "failedObjects")
        },
        "executionReadiness": {
            "queueBackend": queue_backend or "",
            "maxConcurrency": max_concurrency,
            "tokenLedgerCount": len(token_ledgers),
            "tokenLedgerPaths": token_ledgers[:20],
            "releaseId": release_id or "",
            "releaseManifestExists": _release_exists(release_id),
            "importEvidencePaths": import_paths,
            "requiredThroughputPerHour": round(int(daily_target) / 24, 4),
            "requiredThroughputPerMinute": round(int(daily_target) / 1440, 4),
            "measuredThroughput": state.get("throughput") or None,
            "firstPassRate": first_pass_rate,
        },
        "downloadDiagnostics": download_report,
        "blockers": blockers,
        "warnings": warnings,
    }


def write_scale_readiness_report(path: Path, report: Mapping[str, Any]) -> None:
    write_json(path, dict(report))
