"""Staged scale audit controller for data-engineering release trials.

The controller deliberately aggregates existing gates instead of introducing a
second readiness truth source.  It reads scale-readiness/site-scale-readiness
reports, checks the staged rollout policy, and writes JSON + Markdown review
artifacts for hundred/thousand trial decisions.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from _common.io import read_json, write_json
from _common.paths import batch_root, now_iso


SCHEMA = "quwoquan_data.staged_scale_audit/1"
MIN_FIRST_PASS_RATE = 0.70
THOUSAND_STAGE_MIN_TARGET = 1_000


ROLE_LABELS = {
    "audit_controller": "运行审计总控",
    "source_rights_qa": "来源与权利 QA",
    "fact_entity_qa": "事实与实体 QA",
    "content_quality_qa": "内容质量 QA",
    "release_loop_qa": "发布闭环 QA",
    "concurrency_ops": "并发稳定与恢复 QA",
}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = read_json(path)
    return data if isinstance(data, dict) else {}


def _load_reports(paths: list[str | Path]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for raw in paths:
        path = Path(raw)
        data = _load_json_if_exists(path)
        if data:
            data.setdefault("reportPath", str(path))
            reports.append(data)
    return reports


def _issue_rows(reports: list[Mapping[str, Any]]) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    for report in reports:
        prefix = ""
        if report.get("taskId") and report.get("batchId"):
            prefix = f"{report.get('taskId')}/{report.get('batchId')}: "
        elif report.get("siteId") or report.get("vertical"):
            site = str(report.get("siteId") or "*")
            prefix = f"{report.get('vertical')}/{site}/{report.get('batchId')}: "
        for blocker in report.get("blockers") or []:
            blockers.append(prefix + str(blocker))
        for warning in report.get("warnings") or []:
            warnings.append(prefix + str(warning))
    return blockers, warnings


def _stage_triplet_summary(root: Path) -> dict[str, Any]:
    names = ("stage_result.json", "gate_report.json", "repair_report.json")
    if not root.exists():
        return {
            "root": str(root),
            "exists": False,
            "completeCount": 0,
            "partialCount": 0,
            "missing": [str(root)],
            "stageResults": [],
        }
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("stage_result.json")):
        stage_dir = path.parent
        present = [name for name in names if (stage_dir / name).is_file()]
        missing = [name for name in names if name not in present]
        stage_data = _load_json_if_exists(path)
        gate_data = _load_json_if_exists(stage_dir / "gate_report.json")
        repair_data = _load_json_if_exists(stage_dir / "repair_report.json")
        rows.append(
            {
                "stage": str(stage_data.get("stage") or stage_dir.name),
                "path": str(stage_dir),
                "status": str(stage_data.get("status") or ""),
                "gatePassed": bool(gate_data.get("passed")),
                "repairRequired": bool(repair_data.get("required")),
                "missing": missing,
            }
        )
    return {
        "root": str(root),
        "exists": True,
        "completeCount": sum(1 for row in rows if not row["missing"]),
        "partialCount": sum(1 for row in rows if row["missing"]),
        "missing": [
            f"{row['path']}/{name}"
            for row in rows
            for name in row["missing"]
        ],
        "stageResults": rows[:100],
    }


def _site_roots_from_reports(reports: list[Mapping[str, Any]]) -> list[Path]:
    roots: list[Path] = []
    for report in reports:
        for site in report.get("sites") or []:
            if isinstance(site, Mapping) and str(site.get("root") or "").strip():
                roots.append(Path(str(site["root"])))
    return roots


def _queue_backend_evidence(
    *,
    daily_target: int,
    stage: str,
    scale_reports: list[Mapping[str, Any]],
    site_reports: list[Mapping[str, Any]],
) -> dict[str, Any]:
    queue_backends: list[str] = []
    max_concurrency_values: list[int] = []
    first_pass_rates: list[float] = []
    token_ledger_count = 0
    token_ledger_paths: list[str] = []

    for report in scale_reports:
        execution = report.get("executionReadiness") if isinstance(report.get("executionReadiness"), Mapping) else {}
        queue_backends.append(str(execution.get("queueBackend") or ""))
        max_concurrency_values.append(_safe_int(execution.get("maxConcurrency")))
        token_ledger_count += _safe_int(execution.get("tokenLedgerCount"))
        token_ledger_paths.extend(str(path) for path in (execution.get("tokenLedgerPaths") or []) if str(path))
        first_pass = execution.get("firstPassRate")
        if first_pass not in (None, ""):
            first_pass_rates.append(_safe_float(first_pass))

    for report in site_reports:
        aggregate = report.get("aggregate") if isinstance(report.get("aggregate"), Mapping) else {}
        token_ledger_count += _safe_int(aggregate.get("tokenLedgerCount"))
        for site in report.get("sites") or []:
            if not isinstance(site, Mapping):
                continue
            queue_backends.append(str(site.get("queueBackend") or ""))
            first_pass = site.get("firstPassRate")
            if first_pass not in (None, ""):
                first_pass_rates.append(_safe_float(first_pass))

    requires_reliabletask = daily_target >= THOUSAND_STAGE_MIN_TARGET or str(stage) == "thousand"
    return {
        "requiresReliableTask": requires_reliabletask,
        "queueBackends": sorted({backend for backend in queue_backends if backend}),
        "maxConcurrency": max(max_concurrency_values) if max_concurrency_values else 0,
        "firstPassRates": first_pass_rates,
        "minFirstPassRate": min(first_pass_rates) if first_pass_rates else None,
        "tokenLedgerCount": token_ledger_count,
        "tokenLedgerPaths": token_ledger_paths[:50],
    }


def _downstream_evidence(
    *,
    mode: str,
    scale_reports: list[Mapping[str, Any]],
    site_reports: list[Mapping[str, Any]],
) -> dict[str, Any]:
    release_verified = False
    import_verified = False
    search_visible = False
    recommendation_ready = False
    import_paths: list[str] = []

    for report in scale_reports:
        execution = report.get("executionReadiness") if isinstance(report.get("executionReadiness"), Mapping) else {}
        release_verified = release_verified or bool(execution.get("releaseManifestExists"))
        paths = [str(path) for path in (execution.get("importEvidencePaths") or []) if str(path)]
        import_paths.extend(paths)
        import_verified = import_verified or bool(paths)
    for report in site_reports:
        for site in report.get("sites") or []:
            if not isinstance(site, Mapping):
                continue
            release_verified = release_verified or bool(site.get("releaseVerified"))
            import_verified = import_verified or bool(site.get("importVerified"))
            search_visible = search_visible or bool(site.get("searchVisible"))
            recommendation_ready = recommendation_ready or bool(site.get("recommendationFeedbackReady"))

    return {
        "commercialRequired": mode == "commercial",
        "releaseVerified": release_verified,
        "importVerified": import_verified,
        "searchVisible": search_visible,
        "recommendationFeedbackReady": recommendation_ready,
        "importEvidencePaths": import_paths[:50],
    }


def _content_quality_evidence(scale_reports: list[Mapping[str, Any]]) -> dict[str, Any]:
    non_work_materialized = 0
    article_coverage_values: list[float] = []
    for report in scale_reports:
        coverage = report.get("contentQualityCoverage") if isinstance(report.get("contentQualityCoverage"), Mapping) else {}
        non_work_materialized += _safe_int(coverage.get("nonWorkMaterializedCount"))
        if "articleMentionCoverage" in coverage:
            article_coverage_values.append(_safe_float(coverage.get("articleMentionCoverage"), 1.0))
    return {
        "nonWorkMaterializedCount": non_work_materialized,
        "minArticleMentionCoverage": min(article_coverage_values) if article_coverage_values else None,
    }


def _source_sufficiency_evidence(scale_reports: list[Mapping[str, Any]]) -> dict[str, Any]:
    min_rate: float | None = None
    rows: dict[str, Any] = {}
    for report in scale_reports:
        suff = report.get("sourceSufficiency") if isinstance(report.get("sourceSufficiency"), Mapping) else {}
        for lane, row in suff.items():
            if not isinstance(row, Mapping):
                continue
            rate = _safe_float(row.get("rate"))
            min_rate = rate if min_rate is None else min(min_rate, rate)
            rows[str(lane)] = row
    return {"minRate": min_rate, "lanes": rows}


def _role(role: str, issues: list[str], evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "role": role,
        "label": ROLE_LABELS[role],
        "verdict": "pass" if not issues else "fail",
        "issues": issues,
        "evidence": dict(evidence),
    }


def _stage_decision(stage: str, blockers: list[str]) -> str:
    normalized = str(stage or "").strip()
    if not blockers and normalized == "thousand":
        return "GO_TO_10000_PLAN"
    if blockers and normalized == "thousand":
        return "REPAIR_AND_RETRY_1000"
    if not blockers and normalized == "hundred":
        return "GO_TO_1000"
    if blockers and normalized == "hundred":
        return "REPAIR_THEN_RETRY_100"
    return "GO" if not blockers else "NO_GO"


def build_staged_scale_audit_report(
    *,
    stage: str,
    mode: str,
    daily_target: int,
    scale_reports: list[Mapping[str, Any]] | None = None,
    site_reports: list[Mapping[str, Any]] | None = None,
    task_batches: list[tuple[str, str]] | None = None,
    extra_roots: list[str | Path] | None = None,
) -> dict[str, Any]:
    mode = "trial" if str(mode or "").strip() == "trial" else "commercial"
    scale_reports = [dict(report) for report in (scale_reports or [])]
    site_reports = [dict(report) for report in (site_reports or [])]
    task_batches = task_batches or []

    report_blockers, report_warnings = _issue_rows([*scale_reports, *site_reports])
    missing_reports: list[str] = []
    if not scale_reports and not site_reports:
        missing_reports.append("no scale-readiness or site-scale-readiness report supplied")

    evidence_roots: list[Path] = []
    evidence_roots.extend(batch_root(task, batch) for task, batch in task_batches)
    evidence_roots.extend(_site_roots_from_reports(site_reports))
    evidence_roots.extend(Path(root) for root in (extra_roots or []))
    root_summaries = [_stage_triplet_summary(root) for root in evidence_roots]
    missing_triplets = [
        missing
        for summary in root_summaries
        for missing in (summary.get("missing") or [])
    ]

    queue = _queue_backend_evidence(
        daily_target=daily_target,
        stage=stage,
        scale_reports=scale_reports,
        site_reports=site_reports,
    )
    downstream = _downstream_evidence(mode=mode, scale_reports=scale_reports, site_reports=site_reports)
    quality = _content_quality_evidence(scale_reports)
    sufficiency = _source_sufficiency_evidence(scale_reports)

    roles = [
        _role(
            "audit_controller",
            [
                *missing_reports,
                *([f"stage triplet evidence incomplete: {len(missing_triplets)} missing file(s)"] if missing_triplets else []),
            ],
            {
                "scaleReportCount": len(scale_reports),
                "siteReportCount": len(site_reports),
                "stageEvidenceRootCount": len(root_summaries),
                "completeStageTripletCount": sum(_safe_int(row.get("completeCount")) for row in root_summaries),
            },
        ),
        _role(
            "source_rights_qa",
            [
                issue for issue in report_blockers
                if any(token in issue.lower() for token in ("license", "rights", "copyright", "model release"))
            ],
            {"mode": mode, "releasePolicy": "third-party discovery is trial-only; commercial needs open/license/authorization evidence"},
        ),
        _role(
            "fact_entity_qa",
            [
                "source sufficiency evidence missing" if sufficiency["minRate"] is None and scale_reports else "",
                "source sufficiency below 95%" if sufficiency["minRate"] is not None and float(sufficiency["minRate"]) < 0.95 else "",
            ],
            sufficiency,
        ),
        _role(
            "content_quality_qa",
            [
                "non-work materialized objects present" if _safe_int(quality.get("nonWorkMaterializedCount")) else "",
                "firstPassRate evidence missing" if not queue["firstPassRates"] else "",
                (
                    f"firstPassRate below {MIN_FIRST_PASS_RATE:.0%}"
                    if queue["firstPassRates"] and float(queue["minFirstPassRate"]) < MIN_FIRST_PASS_RATE
                    else ""
                ),
            ],
            {**quality, "firstPassRates": queue["firstPassRates"]},
        ),
        _role(
            "release_loop_qa",
            [
                "commercial release evidence missing" if mode == "commercial" and not downstream["releaseVerified"] else "",
                "commercial import evidence missing" if mode == "commercial" and not downstream["importVerified"] else "",
                "commercial search visibility evidence missing" if mode == "commercial" and not downstream["searchVisible"] else "",
                (
                    "commercial recommendation feedback evidence missing"
                    if mode == "commercial" and not downstream["recommendationFeedbackReady"]
                    else ""
                ),
            ],
            downstream,
        ),
        _role(
            "concurrency_ops",
            [
                (
                    "daily target >=1000 requires queueBackend=reliabletask evidence"
                    if queue["requiresReliableTask"] and "reliabletask" not in queue["queueBackends"]
                    else ""
                ),
                (
                    "daily target >=1000 requires maxConcurrency>=10 evidence"
                    if queue["requiresReliableTask"] and _safe_int(queue.get("maxConcurrency")) < 10
                    else ""
                ),
                "TokenLedger evidence missing" if _safe_int(queue.get("tokenLedgerCount")) <= 0 else "",
            ],
            queue,
        ),
    ]
    for row in roles:
        row["issues"] = [issue for issue in row["issues"] if str(issue).strip()]

    role_blockers = [
        f"{row['label']}: {issue}"
        for row in roles
        if row["verdict"] != "pass"
        for issue in row["issues"]
    ]
    blockers = [*missing_reports, *report_blockers, *role_blockers]
    decision = _stage_decision(stage, blockers)
    repair_actions = [
        "repair readiness report blockers and rerun the same scale tier",
        "rerun failed stage from the nearest checkpoint and preserve repair_report evidence",
    ] if blockers else []
    if stage == "thousand" and blockers:
        repair_actions.append("do not enter 10000 tier before a new thousand_stability_review is green")

    return {
        "schemaVersion": SCHEMA,
        "stage": str(stage),
        "mode": mode,
        "dailyTarget": int(daily_target),
        "passed": not blockers,
        "decision": decision,
        "createdAt": now_iso(),
        "inputs": {
            "scaleReadinessReports": [str(report.get("reportPath") or "") for report in scale_reports],
            "siteScaleReadinessReports": [str(report.get("reportPath") or "") for report in site_reports],
            "taskBatches": [{"taskId": task, "batchId": batch} for task, batch in task_batches],
            "evidenceRoots": [str(root) for root in evidence_roots],
        },
        "stageEvidence": {
            "roots": root_summaries,
            "missingTripletCount": len(missing_triplets),
            "missingTriplets": missing_triplets[:100],
        },
        "qualityQa": {
            "sourceSufficiency": sufficiency,
            "contentQuality": quality,
            "downstream": downstream,
        },
        "concurrency": queue,
        "roles": roles,
        "repair": {
            "required": bool(blockers),
            "actions": repair_actions,
            "blockerCount": len(blockers),
        },
        "blockers": blockers,
        "warnings": report_warnings,
    }


def render_staged_scale_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        f"# {report.get('stage')} stability review",
        "",
        f"- decision: `{report.get('decision')}`",
        f"- mode: `{report.get('mode')}`",
        f"- dailyTarget: `{report.get('dailyTarget')}`",
        f"- passed: `{str(bool(report.get('passed'))).lower()}`",
        "",
        "## Role Verdicts",
        "",
        "| role | verdict | issues |",
        "| --- | --- | --- |",
    ]
    for row in report.get("roles") or []:
        issues = "; ".join(str(issue) for issue in (row.get("issues") or [])) or "-"
        lines.append(f"| {row.get('label')} | `{row.get('verdict')}` | {issues} |")
    lines.extend(["", "## Blockers", ""])
    blockers = [str(item) for item in (report.get("blockers") or [])]
    if blockers:
        lines.extend(f"- {item}" for item in blockers[:200])
    else:
        lines.append("- none")
    lines.extend(["", "## Warnings", ""])
    warnings = [str(item) for item in (report.get("warnings") or [])]
    if warnings:
        lines.extend(f"- {item}" for item in warnings[:200])
    else:
        lines.append("- none")
    lines.extend(["", "## Evidence", ""])
    inputs = report.get("inputs") if isinstance(report.get("inputs"), Mapping) else {}
    for key in ("scaleReadinessReports", "siteScaleReadinessReports", "evidenceRoots"):
        values = [str(value) for value in (inputs.get(key) or []) if str(value)]
        lines.append(f"- {key}: {len(values)}")
        for value in values[:20]:
            lines.append(f"  - `{value}`")
    lines.append("")
    return "\n".join(lines)


def write_staged_scale_artifacts(out_dir: Path, report: Mapping[str, Any], *, basename: str | None = None) -> dict[str, str]:
    base = basename or f"{report.get('stage')}_stability_review"
    json_path = out_dir / f"{base}.json"
    md_path = out_dir / f"{base}.md"
    write_json(json_path, dict(report))
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_staged_scale_markdown(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def build_report_from_paths(
    *,
    stage: str,
    mode: str,
    daily_target: int,
    scale_report_paths: list[str | Path],
    site_report_paths: list[str | Path],
    task_batches: list[tuple[str, str]] | None = None,
    extra_roots: list[str | Path] | None = None,
) -> dict[str, Any]:
    return build_staged_scale_audit_report(
        stage=stage,
        mode=mode,
        daily_target=daily_target,
        scale_reports=_load_reports(scale_report_paths),
        site_reports=_load_reports(site_report_paths),
        task_batches=task_batches or [],
        extra_roots=extra_roots or [],
    )
