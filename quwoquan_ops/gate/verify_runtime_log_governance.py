#!/usr/bin/env python3
"""Block regressions from the single canonical runtime-log contract."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "quwoquan_service/contracts/metadata/_shared/runtime_observability.yaml"
SLS = ROOT / "quwoquan_ops/environments/cloud-providers/aliyun/sls/product_telemetry.yaml"


def main() -> int:
    issues: list[str] = []
    catalog = _load(CATALOG, issues)
    sls = _load(SLS, issues)
    _verify_catalog(catalog, issues)
    _verify_sls(sls, issues)
    _require_text(
        ROOT / "quwoquan_service/services/product-ops-service/cmd/api/product_routes.go",
        ('"/ops/runtime-logs"', '"/ops/runtime-logs/summary"', '"/ops/runtime-logs/drilldown"'),
        issues,
    )
    _require_text(
        ROOT / "quwoquan_service/services/product-ops-service/internal/application/runtime_log_service.go",
        ("CanonicalRuntimeLogFields", "GetRuntimeLogSummary", "GetRuntimeLogDrilldown"),
        issues,
    )
    _require_text(
        ROOT / "quwoquan_service/runtime/observability/runtime_log_exporter.go",
        ("NewRuntimeLogExportWriter", "CanonicalRuntimeLogFields"),
        issues,
    )
    _require_text(
        ROOT / "quwoquan_service/services/product-ops-service/cmd/api/main.go",
        ("NewRuntimeLogExportWriter", "exportServiceRuntimeLogs"),
        issues,
    )
    _require_text(
        ROOT / "quwoquan_app/lib/core/di/cloud_http_client_provider.dart",
        ("RuntimeApiLatencyDispatcher",),
        issues,
    )
    _forbid_text(
        ROOT / "quwoquan_app/lib/core/di/cloud_http_client_provider.dart",
        ("AppLogService", "AppTraceContextStore"),
        issues,
    )
    _require_text(
        ROOT / "quwoquan_ops/cli/stackctl.py",
        ("_runtime_log_evidence_report", "runtimeDiagnostics"),
        issues,
    )
    _require_text(
        ROOT / "quwoquan_data/scripts/content/execution/controller/orchestrator.py",
        ('"repo" / "observability"', "write_run_manifest"),
        issues,
    )
    _require_text(
        ROOT / "quwoquan_ops/cli/lib/runtime_log_process.py",
        ('"managed process emitted a non-info line"',),
        issues,
    )
    _forbid_text(
        ROOT / "quwoquan_ops/cli/lib/runtime_log_process.py",
        ('"msg": message',),
        issues,
    )
    for path, fragment in (
        (
            ROOT / "quwoquan_app/lib/core/observability/runtime_logger.dart",
            "RuntimeLogCatalog",
        ),
        (
            ROOT / "quwoquan_service/runtime/observability/runtime_log_record.go",
            "ObservabilitySchema",
        ),
        (
            ROOT / "quwoquan_data/scripts/core/runtime_observability.py",
            "OBSERVABILITY_SCHEMA",
        ),
        (
            ROOT / "quwoquan_ops/cli/lib/observability.py",
            "OBSERVABILITY_SCHEMA",
        ),
        (
            ROOT / "quwoquan_ops/portal/src/shared/observability/runtimeLogger.ts",
            "runtimeLogCatalog.schema",
        ),
    ):
        _require_text(path, (fragment,), issues)
    versioned = _versioned_schema_paths()
    if versioned:
        issues.append(
            "runtime log schema must not carry a version suffix: "
            + ", ".join(_rel(path) for path in versioned[:20])
        )
    if issues:
        print("[verify_runtime_log_governance] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_runtime_log_governance] OK")
    return 0


def _load(path: Path, issues: list[str]) -> dict[str, object]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        issues.append(f"{_rel(path)} cannot be read: {exc}")
        return {}
    if not isinstance(payload, dict):
        issues.append(f"{_rel(path)} must contain a mapping")
        return {}
    return payload


def _verify_catalog(catalog: dict[str, object], issues: list[str]) -> None:
    if catalog.get("schema") != "observability.slim":
        issues.append("runtime observability schema must equal observability.slim")
    forbidden = {str(value) for value in catalog.get("forbidden_fields") or []}
    required_forbidden = {
        "schemaVersion",
        "eventVersion",
        "contractVersion",
        "protocolVersion",
        "releaseVersion",
        "releaseId",
        "dataReleaseId",
    }
    missing_forbidden = sorted(required_forbidden - forbidden)
    if missing_forbidden:
        issues.append(f"runtime log forbidden fields missing {missing_forbidden}")
    expected = {
        "app": "dart",
        "service": "go",
        "data": "python",
        "ops": "python",
        "portal": "typescript",
    }
    signals = catalog.get("signals")
    if not isinstance(signals, list):
        issues.append("runtime log signals must be a list")
        return
    seen: set[str] = set()
    for item in signals:
        if not isinstance(item, dict):
            continue
        signal = str(item.get("id") or "")
        prefix = signal.split(".", 1)[0]
        producers = {str(value) for value in (item.get("producers") or [])}
        if prefix in expected:
            seen.add(prefix)
            if expected[prefix] not in producers:
                issues.append(
                    f"signal {signal} must declare {expected[prefix]} producer"
                )
        if str(item.get("backend") or "") != "runtime-sls":
            issues.append(f"signal {signal} must use runtime-sls backend")
        if int(item.get("retention_days") or 0) != 3:
            issues.append(f"signal {signal} must retain raw records for three days")
    missing_sources = sorted(set(expected) - seen)
    if missing_sources:
        issues.append(f"runtime signal registry misses sources {missing_sources}")


def _verify_sls(sls: dict[str, object], issues: list[str]) -> None:
    spec = sls.get("spec")
    if not isinstance(spec, dict):
        issues.append("SLS specification is missing")
        return
    logstores = spec.get("logstores")
    if not isinstance(logstores, list):
        issues.append("SLS logstores are missing")
        return
    runtime_store = next(
        (
            item
            for item in logstores
            if isinstance(item, dict)
            and item.get("name") == "runtime-diagnostics-raw"
        ),
        None,
    )
    if not isinstance(runtime_store, dict):
        issues.append("SLS runtime-diagnostics-raw logstore is missing")
        return
    if runtime_store.get("retentionDays") != 3:
        issues.append("runtime-diagnostics-raw retention must be three days")
    forbidden = {str(value) for value in runtime_store.get("forbiddenFields") or []}
    required_forbidden = {
        "schemaVersion",
        "eventVersion",
        "contractVersion",
        "protocolVersion",
        "releaseVersion",
        "releaseId",
        "dataReleaseId",
    }
    if missing := sorted(required_forbidden - forbidden):
        issues.append(
            "runtime-diagnostics-raw must reject schema, protocol, and release branches "
            f"missing {missing}"
        )
    jobs = ((spec.get("scheduledSql") or {}).get("jobs") or [])
    if not any(
        isinstance(item, dict)
        and item.get("name") == "runtime-diagnostics-fingerprint-hourly"
        for item in jobs
    ):
        issues.append("runtime diagnostic hourly fingerprint aggregation is missing")


def _require_text(path: Path, fragments: tuple[str, ...], issues: list[str]) -> None:
    text = _read(path, issues)
    for fragment in fragments:
        if fragment not in text:
            issues.append(f"{_rel(path)} missing required runtime-log fragment {fragment!r}")


def _forbid_text(path: Path, fragments: tuple[str, ...], issues: list[str]) -> None:
    text = _read(path, issues)
    for fragment in fragments:
        if fragment in text:
            issues.append(f"{_rel(path)} contains forbidden runtime-log fragment {fragment!r}")


def _read(path: Path, issues: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        issues.append(f"{_rel(path)} cannot be read: {exc}")
        return ""


def _versioned_schema_paths() -> list[Path]:
    paths: list[Path] = []
    roots = (
        ROOT / "quwoquan_app/lib/core/observability",
        ROOT / "quwoquan_service/runtime/observability",
        ROOT / "quwoquan_data/scripts/core",
        ROOT / "quwoquan_ops/cli/lib",
        ROOT / "quwoquan_ops/portal/src/shared/observability",
        ROOT / "quwoquan_service/contracts/metadata/_shared",
    )
    suffixes = {".go", ".dart", ".py", ".ts", ".tsx", ".yaml", ".yml", ".json", ".mjs"}
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in suffixes:
                continue
            try:
                if "observability.slim.v" in path.read_text(encoding="utf-8"):
                    paths.append(path)
            except UnicodeDecodeError:
                continue
    return paths


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
