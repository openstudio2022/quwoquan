#!/usr/bin/env python3
"""Block regressions from the single canonical runtime-log contract."""

from __future__ import annotations

import sys
from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "quwoquan_service/contracts/metadata/_shared/runtime_observability.yaml"
STORAGE = ROOT / "quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/storage.yaml"
ROLLUPS = ROOT / "quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/rollups.yaml"
PRODUCT_OPS_ROOT = ROOT / "quwoquan_service/services/product-ops-service"
PRODUCT_OPS_COMPOSE = PRODUCT_OPS_ROOT / "deploy/compose.yaml"
LOCAL_COMPOSE = PRODUCT_OPS_ROOT / "deploy/local-elasticsearch.compose.yaml"
OPS_LOCAL_COMPOSE = ROOT / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
RETIRED_MANUAL_COMPOSE = ROOT / "quwoquan_ops/observability/es/docker-compose.yml"
SLS_TOKEN = re.compile(r"\bSLS\b", re.IGNORECASE)


def main() -> int:
    issues: list[str] = []
    catalog = _load(CATALOG, issues)
    storage = _load(STORAGE, issues)
    rollups = _load(ROLLUPS, issues)
    _verify_catalog(catalog, issues)
    _verify_elasticsearch(storage, rollups, issues)
    _verify_environment_bindings(issues)
    _verify_local_elasticsearch_workload(issues)
    _verify_sls_is_inactive(issues)
    _require_text(
        ROOT / "quwoquan_service/services/product-ops-service/cmd/api/product_routes.go",
        ('"/ops/runtime-logs"', '"/ops/runtime-logs/summary"', '"/ops/runtime-logs/drilldown"'),
        issues,
    )
    _require_text(
        ROOT / "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application/runtime_log_service.go",
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
        ("NewRuntimeLogExportWriter", "NewProcessTraceLogger"),
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
        if str(item.get("backend") or "") != "elasticsearch":
            issues.append(f"signal {signal} must use elasticsearch backend")
        if int(item.get("retention_days") or 0) != 3:
            issues.append(f"signal {signal} must retain raw records for three days")
    missing_sources = sorted(set(expected) - seen)
    if missing_sources:
        issues.append(f"runtime signal registry misses sources {missing_sources}")


def _verify_elasticsearch(
    storage: dict[str, object],
    rollups: dict[str, object],
    issues: list[str],
) -> None:
    backends = storage.get("environment_backends")
    if not isinstance(backends, dict) or set(backends) != {"alpha", "beta", "gamma", "prod"}:
        issues.append("Elasticsearch environment_backends must cover four environments")
        return
    if any(
        not isinstance(binding, dict)
        or binding.get("adapter") != "ext.obs.elasticsearch"
        for binding in backends.values()
    ):
        issues.append("all runtime log environments must select ext.obs.elasticsearch")
    logstores = storage.get("logstores")
    if not isinstance(logstores, dict):
        issues.append("Elasticsearch logstores are missing")
        return
    runtime_store = logstores.get("runtime_diagnostic")
    if not isinstance(runtime_store, dict):
        issues.append("Elasticsearch runtime diagnostic index is missing")
        return
    if runtime_store.get("ttl_days") != 3:
        issues.append("runtime-diagnostics-raw retention must be three days")
    forbidden = {str(value) for value in runtime_store.get("forbidden_fields") or []}
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
    jobs = rollups.get("jobs") or []
    if not any(
        isinstance(item, dict)
        and item.get("row_kind") == "runtime_diagnostics"
        for item in jobs
    ):
        issues.append("runtime diagnostic hourly fingerprint aggregation is missing")


def _verify_environment_bindings(issues: list[str]) -> None:
    for environment in ("alpha", "beta", "gamma", "prod"):
        path = PRODUCT_OPS_ROOT / "environments" / environment / "config.yaml"
        document = _load(path, issues)
        bindings = document.get("externalBindings")
        binding = bindings.get("runtime.log.sink") if isinstance(bindings, dict) else None
        if not isinstance(binding, dict):
            issues.append(f"{_rel(path)} must select runtime.log.sink")
            continue
        if binding.get("state") != "enabled" or binding.get("adapter") != "ext.obs.elasticsearch":
            issues.append(f"{_rel(path)} must enable only ext.obs.elasticsearch")
        endpoint_ref = str(binding.get("endpointRef") or "")
        secret_refs = binding.get("secretRefs")
        if environment == "prod":
            if endpoint_ref != "environment_binding:product_ops.elasticsearch":
                issues.append("Prod runtime.log.sink must use the managed ES environment binding")
            if secret_refs != ["PRODUCT_OPS_ELASTICSEARCH_API_KEY"]:
                issues.append("Prod runtime.log.sink must use only the managed ES API key reference")
        else:
            expected_ref = f"local_topology:{environment}.elasticsearch"
            if endpoint_ref != expected_ref:
                issues.append(f"{environment} runtime.log.sink must use {expected_ref}")
            if secret_refs != []:
                issues.append(f"{environment} local ES binding must not require a Provider secret")


def _verify_local_elasticsearch_workload(issues: list[str]) -> None:
    compose = _load(LOCAL_COMPOSE, issues)
    services = compose.get("services")
    elasticsearch = services.get("elasticsearch") if isinstance(services, dict) else None
    product_ops = services.get("product-ops-service") if isinstance(services, dict) else None
    if not isinstance(elasticsearch, dict):
        issues.append(
            "Product Ops deploy/local-elasticsearch.compose.yaml must own the local Elasticsearch workload"
        )
        return
    image = str(elasticsearch.get("image") or "")
    if not image.startswith("docker.elastic.co/elasticsearch/elasticsearch@sha256:"):
        issues.append("local Elasticsearch image must be pinned by immutable sha256 digest")
    environment = elasticsearch.get("environment")
    if not isinstance(environment, dict) or "QWQ_LOCAL_RELEASE_TARGET" not in str(
        environment.get("cluster.name") or ""
    ):
        issues.append("local Elasticsearch cluster identity must be target-scoped")
    volumes = elasticsearch.get("volumes")
    if volumes != ["product-ops-elasticsearch-data:/usr/share/elasticsearch/data"]:
        issues.append("local Elasticsearch must use the Product Ops project-scoped data volume")
    depends_on = product_ops.get("depends_on") if isinstance(product_ops, dict) else None
    if not isinstance(depends_on, dict) or "elasticsearch" not in depends_on:
        issues.append("Product Ops readiness must fail closed on Elasticsearch readiness")

    product_ops_compose = _load(PRODUCT_OPS_COMPOSE, issues)
    product_services = product_ops_compose.get("services")
    if isinstance(product_services, dict) and "elasticsearch" in product_services:
        issues.append("Prod-visible Product Ops base Compose must not package local Elasticsearch")
    _require_text(
        ROOT / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh",
        (
            "product-ops-service/deploy/local-elasticsearch.compose.yaml",
            '[[ "$WORKLOAD" == "full" || "$WORKLOAD" == "content-commercial" ]]',
        ),
        issues,
    )

    ops_compose = _load(OPS_LOCAL_COMPOSE, issues)
    ops_services = ops_compose.get("services")
    if isinstance(ops_services, dict) and "elasticsearch" in ops_services:
        issues.append("Ops environment Compose must not own a second Elasticsearch workload")
    if RETIRED_MANUAL_COMPOSE.exists():
        issues.append("standalone observability Elasticsearch Compose entrypoint must be retired")


def _verify_sls_is_inactive(issues: list[str]) -> None:
    """Forbid active SLS dependencies while preserving explicit rejected history."""

    allowed_history = {
        ROOT / "specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/design.md",
        ROOT / "quwoquan_ops/runbooks/product_telemetry_elasticsearch.md",
    }
    roots = (
        ROOT / "specs/feature-tree",
        ROOT / "quwoquan_app/lib",
        ROOT / "quwoquan_app/test",
        ROOT / "quwoquan_service/contracts",
        ROOT / "quwoquan_service/services",
        ROOT / "quwoquan_service/generated/contract_graph.json",
        ROOT / "quwoquan_ops/environments",
        ROOT / "quwoquan_ops/cli",
        ROOT / "quwoquan_ops/tests",
        ROOT / ".github/workflows",
    )
    suffixes = {".dart", ".go", ".json", ".md", ".py", ".yaml", ".yml"}
    matches: list[str] = []
    for root in roots:
        candidates = (root,) if root.is_file() else root.rglob("*")
        for path in candidates:
            if not path.is_file() or path.suffix.lower() not in suffixes or path in allowed_history:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if SLS_TOKEN.search(line):
                    matches.append(f"{_rel(path)}:{line_number}")
                    if len(matches) >= 30:
                        break
            if len(matches) >= 30:
                break
        if len(matches) >= 30:
            break
    if matches:
        issues.append("active SLS dependency is forbidden: " + ", ".join(matches))


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
