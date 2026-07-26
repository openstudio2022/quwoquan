#!/usr/bin/env python3
"""Block drift between external Capability, Adapter, Binding and conformance truth."""
from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.external_provider_governance import (
    composition_issues,
    load_and_compile,
    load_registry,
)


MESSAGE_TRANSPORT_CAPABILITY = "runtime.message.transport"
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
        f"({compiled['capabilityCount']} capabilities, {compiled['adapterCount']} adapters)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
