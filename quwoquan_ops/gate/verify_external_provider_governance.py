#!/usr/bin/env python3
"""Block drift between external Capability, Adapter, Binding and conformance truth."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.external_provider_governance import (
    composition_issues,
    load_and_compile,
    load_registry,
)


MESSAGE_TRANSPORT_CAPABILITY = "runtime.message.transport"
MESSAGE_TRANSPORT_REQUIRED_METRICS = (
    "pending_lag",
    "dead_letter",
    "publish_p95",
    "consume_p95",
)
MESSAGE_TRANSPORT_RUNTIME_METRICS = {
    "pending_lag": "Gauge",
    "dead_letter": "Counter",
    "publish_duration_seconds": "Histogram",
    "consume_duration_seconds": "Histogram",
}
MESSAGE_TRANSPORT_P95_RECORDINGS = {
    "qwq_message_transport_publish_p95": (
        "qwq_message_transport_publish_duration_seconds_bucket"
    ),
    "qwq_message_transport_consume_p95": (
        "qwq_message_transport_consume_duration_seconds_bucket"
    ),
}
PROMETHEUS_VEC_RE = re.compile(
    r"promauto\.New(?P<constructor>Gauge|Counter|Histogram)Vec\(\s*"
    r"prometheus\.(?P<opts>Gauge|Counter|Histogram)Opts\{"
    r"(?P<body>.*?)\}\s*,",
    re.DOTALL,
)
REDIS_CONSTRUCTOR_RE = re.compile(
    r"\b(?:redis|rtredis)\.New(?:Client|ClusterClient|MemoryClient)\("
)
SERVICE_PRIVATE_IMPORT_RE = re.compile(
    r'"quwoquan_service/services/([^/]+)/(?:generated|internal)/'
)


def _function_body(source: str, function_name: str) -> str:
    marker = f"func (t *RedisMessageTransport) {function_name}("
    start = source.find(marker)
    if start < 0:
        return ""
    next_function = source.find("\nfunc ", start + len(marker))
    return source[start:] if next_function < 0 else source[start:next_function]


def message_transport_observability_issues(
    runtime_source: str,
    *,
    rules_document: dict[object, object] | None = None,
    dashboard_source: dict[object, object] | None = None,
) -> list[str]:
    """Require honest histogram samples and canonical PromQL p95 recordings."""
    issues: list[str] = []
    declared_types: dict[str, str] = {}
    for match in PROMETHEUS_VEC_RE.finditer(runtime_source):
        name_match = re.search(r'Name:\s*"([^"]+)"', match.group("body"))
        if name_match is not None:
            declared_types[name_match.group(1)] = match.group("constructor")
    for metric_name, expected_type in MESSAGE_TRANSPORT_RUNTIME_METRICS.items():
        actual_type = declared_types.get(metric_name)
        if actual_type != expected_type:
            issues.append(
                "quwoquan_service/runtime/messaging/redis_message_transport_binding.go: "
                f"{metric_name} must use {expected_type}Vec, got {actual_type or 'missing'}"
            )
    for dishonest_name in ("publish_p95", "consume_p95"):
        if dishonest_name in declared_types:
            issues.append(
                "quwoquan_service/runtime/messaging/redis_message_transport_binding.go: "
                f"{dishonest_name} must be a PromQL recording, not a raw runtime metric"
            )

    rules_path = (
        ROOT
        / "quwoquan_ops"
        / "observability"
        / "monitoring"
        / "alerts"
        / "quwoquan_alerts.yaml"
    )
    if rules_document is None:
        rules_document = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    recording_rules = {
        rule.get("record"): str(rule.get("expr") or "")
        for group in rules_document.get("groups", [])
        if isinstance(group, dict)
        for rule in group.get("rules", [])
        if isinstance(rule, dict) and rule.get("record")
    }
    for recording, source_bucket in MESSAGE_TRANSPORT_P95_RECORDINGS.items():
        expression = recording_rules.get(recording, "")
        normalized = " ".join(expression.split())
        if not re.search(r"histogram_quantile\s*\(\s*0\.95\s*,", expression):
            issues.append(
                f"{rules_path.relative_to(ROOT)}: {recording} must calculate "
                "histogram_quantile(0.95, ...)"
            )
        if source_bucket not in expression:
            issues.append(
                f"{rules_path.relative_to(ROOT)}: {recording} must consume {source_bucket}"
            )
        if "sum by (le, root, adapter)" not in normalized:
            issues.append(
                f"{rules_path.relative_to(ROOT)}: {recording} must preserve "
                "le/root/adapter while aggregating operation series"
            )

    dashboard_path = (
        ROOT
        / "quwoquan_ops"
        / "observability"
        / "monitoring"
        / "dashboards"
        / "l2_business_journey.json"
    )
    if dashboard_source is None:
        dashboard_source = json.loads(dashboard_path.read_text(encoding="utf-8"))
    dashboard_expressions = {
        target.get("expr")
        for row in dashboard_source.get("dashboard", {}).get("panels", [])
        if isinstance(row, dict)
        for target in row.get("targets", [])
        if isinstance(target, dict)
    }
    for recording in MESSAGE_TRANSPORT_P95_RECORDINGS:
        if not any(
            isinstance(expression, str) and recording in expression
            for expression in dashboard_expressions
        ):
            issues.append(
                f"{dashboard_path.relative_to(ROOT)}: dashboard must consume {recording}"
            )
    return issues


def message_transport_static_issues(registry: dict[object, object]) -> list[str]:
    """Keep static composition roots on generated binding + typed transport."""
    issues: list[str] = []
    capabilities = registry.get("capabilities")
    if not isinstance(capabilities, list):
        return ["metadata: derived capabilities are unavailable for transport scan"]
    capability = next(
        (
            item
            for item in capabilities
            if isinstance(item, dict)
            and item.get("capability_id") == MESSAGE_TRANSPORT_CAPABILITY
        ),
        None,
    )
    if not isinstance(capability, dict):
        return [
            "metadata: runtime.message.transport must declare one owner and local capability-use roots"
        ]

    helpers_by_service: dict[str, list[Path]] = {}
    services_root = ROOT / "quwoquan_service" / "services"
    for helper in services_root.glob("*/cmd/**/message_transport.go"):
        if helper.name.endswith("_test.go"):
            continue
        service_id = helper.relative_to(services_root).parts[0]
        helpers_by_service.setdefault(service_id, []).append(helper)
        source = helper.read_text(encoding="utf-8")
        relative = helper.relative_to(ROOT).as_posix()
        if "ExternalProviderBindingFor(" not in source:
            issues.append(f"{relative}: message root must consume its generated binding")
        if "RequireConfiguredRedisMessageTransport(" not in source:
            issues.append(f"{relative}: message root must run generated-binding preflight")
        if REDIS_CONSTRUCTOR_RE.search(source):
            issues.append(f"{relative}: bare Redis client initialization bypasses typed transport")

    for root in capability.get("binding_roots") or []:
        if not isinstance(root, dict):
            continue
        service_id = str(root.get("descriptor_owner") or "")
        output = str(root.get("descriptor_output") or "")
        if not service_id or not output:
            issues.append("metadata: message transport root is missing descriptor ownership")
            continue
        generated_import = "quwoquan_service/" + str(
            Path(output).relative_to("quwoquan_service").parent
        )
        helpers = helpers_by_service.get(service_id, [])
        if not helpers or not any(
            generated_import in helper.read_text(encoding="utf-8") for helper in helpers
        ):
            issues.append(
                f"{output}: no {service_id} message root consumes its local generated descriptor"
            )

    for source_path in services_root.glob("*/cmd/**/*.go"):
        if source_path.name.endswith("_test.go"):
            continue
        source = source_path.read_text(encoding="utf-8")
        relative = source_path.relative_to(ROOT).as_posix()
        if "NewRedisMessageTransportForRoot(" in source or "NewRedisMessageTransport(" in source:
            if source_path.name != "message_transport.go":
                issues.append(
                    f"{relative}: direct transport construction must stay behind generated preflight"
                )
            elif (
                "ExternalProviderBindingFor(" not in source
                or "RequireConfiguredRedisMessageTransport(" not in source
            ):
                issues.append(
                    f"{relative}: direct transport construction lacks generated preflight"
                )
        if REDIS_CONSTRUCTOR_RE.search(source):
            issues.append(f"{relative}: bare Redis client initialization bypasses typed transport")

    runtime_binding = (
        ROOT
        / "quwoquan_service"
        / "runtime"
        / "messaging"
        / "redis_message_transport_binding.go"
    )
    runtime_source = runtime_binding.read_text(encoding="utf-8")
    for function_name in ("AppendDurable", "ReadDurable", "EnsureDurableConsumerGroup"):
        body = _function_body(runtime_source, function_name)
        if not body:
            issues.append(f"{runtime_binding.relative_to(ROOT)}: {function_name} is missing")
        elif ".Publish(" in body or ".Subscribe(" in body:
            issues.append(
                f"{runtime_binding.relative_to(ROOT)}: {function_name} must not use Pub/Sub for durable delivery"
            )
    issues.extend(message_transport_observability_issues(runtime_source))
    declared_metrics = capability.get("observability_metrics") or []
    if tuple(declared_metrics) != MESSAGE_TRANSPORT_REQUIRED_METRICS:
        issues.append(
            "metadata: runtime.message.transport owner must declare fixed "
            "pending_lag/dead_letter/publish_p95/consume_p95 observability metrics"
        )

    for source_path in services_root.glob("**/*.go"):
        if source_path.name.endswith("_test.go"):
            continue
        service_id = source_path.relative_to(services_root).parts[0]
        source = source_path.read_text(encoding="utf-8")
        for target_service in SERVICE_PRIVATE_IMPORT_RE.findall(source):
            if target_service != service_id:
                issues.append(
                    f"{source_path.relative_to(ROOT)}: cross-service generated/internal import "
                    f"from {target_service} is forbidden"
                )
    return issues


def main() -> int:
    try:
        compiled, issues = load_and_compile()
        issues = [
            *issues,
            *composition_issues(load_registry(), compiled),
        ]
        static_issues = message_transport_static_issues(load_registry())
    except (OSError, ValueError) as exc:
        print(f"[verify_external_provider_governance] FAIL\n  - cannot compile registry: {exc}")
        return 1
    if static_issues:
        print("[verify_external_provider_governance] FAIL")
        for issue in static_issues:
            print(f"  - {issue}")
        return 1
    if issues:
        print("[verify_external_provider_governance] FAIL")
        for issue in issues:
            print(f"  - {issue.render()}")
        return 1
    print(
        "[verify_external_provider_governance] OK "
        f"({compiled['capabilityCount']} bindings, "
        f"{compiled['providerConformanceCapabilityCount']} provider capabilities, "
        f"{compiled['adapterCount']} adapters)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
