#!/usr/bin/env python3
"""Block regressions from the single canonical runtime-log contract."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml

from quwoquan_ops.cli.lib import external_provider_governance as provider_governance
from quwoquan_ops.cli.lib.deployment_candidate_manifest import (
    local_elasticsearch_image_digest,
)

CATALOG = ROOT / "quwoquan_service/contracts/metadata/_shared/runtime_observability.yaml"
STORAGE = ROOT / "quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/storage.yaml"
ROLLUPS = ROOT / "quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/rollups.yaml"
PRODUCT_OPS_ROOT = ROOT / "quwoquan_service/services/product-ops-service"
PRODUCT_OPS_ROUTES = PRODUCT_OPS_ROOT / "cmd/api/product_routes.go"
EVENT_RECORD_OPERATIONS = (
    PRODUCT_OPS_ROOT / "contracts/product_ops/event_record/operations.yaml"
)
EVENT_RECORD_HTTP_HANDLER = (
    PRODUCT_OPS_ROOT
    / "internal/product_ops/event_record/adapters/inbound/http/operations_handler.go"
)
RUNTIME_LOG_ROUTES = {
    "GetRuntimeLogSummary": ("GET", "/ops/runtime-logs/summary"),
    "GetRuntimeLogDrilldown": ("GET", "/ops/runtime-logs/drilldown"),
    "ReportRuntimeLogBatch": ("POST", "/ops/runtime-logs"),
}
PRODUCT_OPS_COMPOSE = PRODUCT_OPS_ROOT / "deploy/compose.yaml"
LOCAL_COMPOSE = PRODUCT_OPS_ROOT / "deploy/local-elasticsearch.compose.yaml"
PRODUCT_OPS_ENVIRONMENT_CONFIGS = {
    environment: PRODUCT_OPS_ROOT / f"environments/{environment}/config.yaml"
    for environment in ("alpha", "beta", "gamma", "prod")
}
OPS_LOCAL_COMPOSE = ROOT / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
RETIRED_MANUAL_COMPOSE = ROOT / "quwoquan_ops/observability/es/docker-compose.yml"
LOCAL_STARTUP = ROOT / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
LOG_SINK_RESOLVER = ROOT / "quwoquan_ops/cli/lib/product_telemetry_log_sink.py"
CANDIDATE_MANIFEST = ROOT / "quwoquan_ops/cli/lib/deployment_candidate_manifest.py"
STACKCTL = ROOT / "quwoquan_ops/cli/stackctl.py"
SLS_TOKEN = re.compile(r"(?<![A-Za-z0-9])SLS(?![A-Za-z0-9])", re.IGNORECASE)


def main() -> int:
    issues: list[str] = []
    catalog = _load(CATALOG, issues)
    storage = _load(STORAGE, issues)
    rollups = _load(ROLLUPS, issues)
    _verify_catalog(catalog, issues)
    _verify_elasticsearch(storage, rollups, issues)
    _verify_environment_bindings(issues)
    _verify_candidate_owned_environment_elasticsearch_config(issues)
    _verify_local_elasticsearch_workload(issues)
    _verify_candidate_owned_local_elasticsearch_runtime(issues)
    _verify_sls_is_inactive(issues)
    _verify_runtime_log_http_registration(issues)
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
        ROOT / "quwoquan_app/lib/runtime/di/cloud_http_client_provider.dart",
        ("RuntimeApiLatencyDispatcher",),
        issues,
    )
    _forbid_text(
        ROOT / "quwoquan_app/lib/runtime/di/cloud_http_client_provider.dart",
        ("AppLogService", "AppTraceContextStore"),
        issues,
    )
    _require_text(
        STACKCTL,
        ("_runtime_log_evidence_report", "runtimeDiagnostics"),
        issues,
    )
    _require_text(
        ROOT / "quwoquan_data/scripts/content/execution/controller/orchestrator.py",
        ('"repo" / "observability"', "write_data_run_manifest"),
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
            ROOT / "quwoquan_app/lib/runtime/observability/runtime_logger.dart",
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


def _verify_runtime_log_http_registration(
    issues: list[str],
    *,
    product_routes_text: str | None = None,
    adapter_text: str | None = None,
    operation_documents: dict[str, dict[str, object]] | None = None,
) -> None:
    """Require one typed composition-to-object-adapter route chain.

    Public runtime-log paths are authored by the ``ops.event_record`` object
    contract and resolved by the generated operation descriptor.  The service
    composition root may register that typed handler, but must not duplicate
    the route literals.
    """

    product_routes = (
        _read(PRODUCT_OPS_ROUTES, issues)
        if product_routes_text is None
        else product_routes_text
    )
    adapter = (
        _read(EVENT_RECORD_HTTP_HANDLER, issues)
        if adapter_text is None
        else adapter_text
    )

    typed_registration = re.compile(
        r"eventrecordhttp\.NewOperationsHandler\s*\(\s*"
        r"eventrecordhttp\.OperationsDependencies\s*\{.*?\}\s*,?\s*\)"
        r"\.Register\s*\(\s*mux\s*\)",
        re.DOTALL,
    )
    if not typed_registration.search(product_routes):
        issues.append(
            f"{_rel(PRODUCT_OPS_ROUTES)} must register the typed "
            "event_record OperationsHandler"
        )

    expected_paths = {path for _, path in RUNTIME_LOG_ROUTES.values()}
    for path in sorted(expected_paths):
        literal = f'"{path}"'
        if literal in product_routes:
            issues.append(
                f"{_rel(PRODUCT_OPS_ROUTES)} must not duplicate canonical "
                f"runtime-log path {path}; register the object adapter instead"
            )
        if literal in adapter:
            issues.append(
                f"{_rel(EVENT_RECORD_HTTP_HANDLER)} must resolve {path} from the "
                "generated operation descriptor, not a path literal"
            )

    required_adapter_fragments = (
        "func (s *OperationsHandler) Register(mux *http.ServeMux)",
        'canonicalID := "ops.event_record." + operationID',
        'operationsecurity.ForDomain("ops")',
        "return descriptor.Method, descriptor.PathTemplate",
    )
    for fragment in required_adapter_fragments:
        if fragment not in adapter:
            issues.append(
                f"{_rel(EVENT_RECORD_HTTP_HANDLER)} must preserve typed generated "
                f"route resolution fragment {fragment!r}"
            )
    for operation in RUNTIME_LOG_ROUTES:
        expected_handler = {
            "GetRuntimeLogSummary": "handleGetRuntimeLogSummary",
            "GetRuntimeLogDrilldown": "handleGetRuntimeLogDrilldown",
            "ReportRuntimeLogBatch": "handleReportRuntimeLogBatch",
        }[operation]
        registration = re.compile(
            rf'register\s*\(\s*"{re.escape(operation)}"\s*,\s*'
            rf"s\.{re.escape(expected_handler)}\s*\)"
        )
        if not registration.search(adapter):
            issues.append(
                f"{_rel(EVENT_RECORD_HTTP_HANDLER)} must register {operation} "
                f"with {expected_handler}"
            )

    documents = operation_documents
    if documents is None:
        documents = {}
        contracts_root = ROOT / "quwoquan_service/services"
        for path in sorted(contracts_root.rglob("operations.yaml")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                issues.append(f"{_rel(path)} cannot be read: {exc}")
                continue
            if not any(route_path in text for route_path in expected_paths):
                continue
            try:
                payload = yaml.safe_load(text)
            except yaml.YAMLError as exc:
                issues.append(f"{_rel(path)} cannot be read: {exc}")
                continue
            if not isinstance(payload, dict):
                issues.append(f"{_rel(path)} must contain a mapping")
                continue
            documents[_rel(path)] = payload

    owners: dict[str, list[tuple[str, str, str]]] = {
        path: [] for path in expected_paths
    }
    for source, document in documents.items():
        routes = document.get("api_routes")
        if not isinstance(routes, list):
            continue
        for route in routes:
            if not isinstance(route, dict):
                continue
            path = str(route.get("path") or "")
            if path not in owners:
                continue
            owners[path].append(
                (
                    source,
                    str(route.get("operation") or ""),
                    str(route.get("method") or "").upper(),
                )
            )

    canonical_source = _rel(EVENT_RECORD_OPERATIONS)
    for operation, (method, path) in RUNTIME_LOG_ROUTES.items():
        expected_owner = (canonical_source, operation, method)
        actual_owners = owners[path]
        if actual_owners != [expected_owner]:
            rendered = ", ".join(
                f"{source}:{owner_operation}:{owner_method}"
                for source, owner_operation, owner_method in actual_owners
            ) or "none"
            issues.append(
                f"runtime-log route {method} {path} must have exactly one canonical "
                f"owner {canonical_source}:{operation}; found {rendered}"
            )


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
    try:
        compiled, compilation_issues = provider_governance.load_and_compile()
    except (OSError, RuntimeError, ValueError, yaml.YAMLError) as exc:
        issues.append(f"compiled Provider Binding cannot be loaded: {exc}")
        return
    if compilation_issues:
        issues.extend(
            "compiled Provider Binding: " + issue.render()
            for issue in compilation_issues
        )
        return
    selected_bindings = compiled.get("selectedBindings")
    if not isinstance(selected_bindings, dict):
        issues.append("compiled Provider Binding misses selectedBindings")
        return
    for environment in ("alpha", "beta", "gamma", "prod"):
        environment_bindings = selected_bindings.get(environment)
        binding = (
            environment_bindings.get("runtime.log.sink")
            if isinstance(environment_bindings, dict)
            else None
        )
        if not isinstance(binding, dict):
            issues.append(f"compiled {environment} Binding must select runtime.log.sink")
            continue
        if (
            binding.get("state") != "enabled"
            or binding.get("adapter_id") != "ext.obs.elasticsearch"
        ):
            issues.append(
                f"compiled {environment} Binding must enable only ext.obs.elasticsearch"
            )
        endpoint_ref = str(binding.get("endpoint_ref") or "")
        secret_refs = binding.get("secret_refs")
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


def _verify_candidate_owned_environment_elasticsearch_config(
    issues: list[str],
    *,
    configs: dict[str, dict[str, object]] | None = None,
) -> None:
    """Forbid environment config from becoming a second ES endpoint owner.

    The Provider Binding owns endpoint identity and the immutable candidate
    projects it to ``PRODUCT_OPS_ELASTICSEARCH_ENDPOINT``.  Service environment
    config may select the Binding, but must not persist the resolved endpoint.
    """

    resolved_configs = configs or {
        environment: _load(path, issues)
        for environment, path in PRODUCT_OPS_ENVIRONMENT_CONFIGS.items()
    }
    endpoint_key = "sys.product-ops-service.elasticsearch.endpoint"
    for environment in ("alpha", "beta", "gamma", "prod"):
        payload = resolved_configs.get(environment)
        if not isinstance(payload, dict):
            issues.append(f"Product Ops {environment} environment config is missing")
            continue
        overrides = payload.get("overrides")
        if isinstance(overrides, dict) and endpoint_key in overrides:
            issues.append(
                f"Product Ops {environment} environment config must not own "
                f"{endpoint_key}; consume the candidate-owned Provider Binding endpoint"
            )


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
    try:
        local_elasticsearch_image_digest(image)
    except ValueError as exc:
        issues.append(str(exc))
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
        LOCAL_STARTUP,
        (
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


def _verify_candidate_owned_local_elasticsearch_runtime(
    issues: list[str],
    *,
    startup_text: str | None = None,
    resolver_text: str | None = None,
    candidate_manifest_text: str | None = None,
    stackctl_text: str | None = None,
) -> None:
    """Require local ES startup to consume only the immutable candidate artifact."""

    startup = (
        _read(LOCAL_STARTUP, issues)
        if startup_text is None
        else startup_text
    )
    resolver = (
        _read(LOG_SINK_RESOLVER, issues)
        if resolver_text is None
        else resolver_text
    )
    candidate = (
        _read(CANDIDATE_MANIFEST, issues)
        if candidate_manifest_text is None
        else candidate_manifest_text
    )
    stackctl = _read(STACKCTL, issues) if stackctl_text is None else stackctl_text

    required_startup = (
        "QWQ_OBSERVABILITY_LOG_SINK_COMPOSE_FILE",
    )
    for fragment in required_startup:
        if fragment not in startup:
            issues.append(
                "local Elasticsearch startup must consume candidate-owned "
                f"{fragment}"
            )

    workspace_compose = (
        "$ROOT/"
        + "quwoquan_service/services/product-ops-service/deploy/"
        + "local-elasticsearch.compose.yaml"
    )
    hardcoded_endpoint = (
        'PRODUCT_OPS_ELASTICSEARCH_ENDPOINT="${'
        + "PRODUCT_OPS_ELASTICSEARCH_ENDPOINT:-http://elasticsearch:9200}"
        + '"'
    )
    forbidden_startup = (
        workspace_compose,
        hardcoded_endpoint,
        "LOCAL_GAMMA_ELASTICSEARCH_IMAGE=",
        "QWQ_COMPOSE_ELASTICSEARCH_IMAGE",
    )
    for fragment in forbidden_startup:
        if fragment in startup:
            issues.append(
                "local Elasticsearch startup must not resolve workspace Compose, "
                f"endpoint, or image outside the candidate: {fragment!r}"
            )

    if "http://elasticsearch:9200" in resolver:
        issues.append(
            "product telemetry log-sink resolver must not synthesize an Elasticsearch "
            "endpoint outside the candidate"
        )
    if "QWQ_OBSERVABILITY_LOG_SINK_COMPOSE_FILE" not in stackctl:
        issues.append(
            "stackctl must pass the candidate-owned Elasticsearch Compose artifact "
            "to the local launcher"
        )
    for fragment in (
        "packages/runtime-shared/observability-log-sink/",
        '"composeRef"',
        '"composeDigest"',
    ):
        if fragment not in candidate:
            issues.append(
                "deployment candidate must materialize the Elasticsearch Compose "
                f"artifact and bind {fragment!r}"
            )


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
        ROOT / "quwoquan_ops/portal/src",
        ROOT / "quwoquan_ops/tests",
        ROOT / ".github/workflows",
    )
    matches = _find_sls_matches(roots, allowed_history=allowed_history)
    if matches:
        issues.append("active SLS dependency is forbidden: " + ", ".join(matches))


def _find_sls_matches(
    roots: tuple[Path, ...],
    *,
    allowed_history: set[Path] | None = None,
) -> list[str]:
    """Return bounded source locations that still carry active SLS semantics."""

    allowed = allowed_history or set()
    suffixes = {
        ".dart",
        ".go",
        ".json",
        ".md",
        ".mjs",
        ".py",
        ".ts",
        ".tsx",
        ".yaml",
        ".yml",
    }
    matches: list[str] = []
    for root in roots:
        candidates = (root,) if root.is_file() else root.rglob("*")
        for path in candidates:
            if not path.is_file() or path.suffix.lower() not in suffixes or path in allowed:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if SLS_TOKEN.search(line) and "assertNotIn" not in line:
                    matches.append(f"{_rel(path)}:{line_number}")
                    if len(matches) >= 30:
                        break
            if len(matches) >= 30:
                break
        if len(matches) >= 30:
            break
    return matches


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
        ROOT / "quwoquan_app/lib/runtime/observability",
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
