#!/usr/bin/env python3
"""Prove non-production Provider substitute code is outside Prod artifacts."""

from __future__ import annotations

from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.external_provider_governance import (
    is_prod_forbidden_adapter,
    load_and_compile,
)


FORBIDDEN = ("provider-protocol-substitute", "sms-provider-substitute")


def main() -> int:
    issues: list[str] = []
    compiled, governance_issues = load_and_compile()
    issues.extend(issue.render() for issue in governance_issues)
    for capability_id, binding in (
        compiled.get("selectedBindings", {}).get("prod", {}).items()
    ):
        adapter_id = str(binding.get("adapter_id") or "")
        if is_prod_forbidden_adapter(adapter_id):
            issues.append(
                f"prod binding reaches substitute: {capability_id}={adapter_id}"
            )

    for config in (
        ROOT / "quwoquan_service" / "services"
    ).glob("*/environments/prod/config.yaml"):
        source = config.read_text(encoding="utf-8")
        for token in FORBIDDEN:
            if token in source:
                issues.append(f"{config.relative_to(ROOT)} contains {token}")

    prod_renderer = (
        ROOT / "quwoquan_ops" / "cli" / "prod" / "render_prod_plane_stack.py"
    ).read_text(encoding="utf-8")
    for token in FORBIDDEN:
        if token in prod_renderer:
            issues.append(f"Prod renderer reaches {token}")

    service_go_mod = (
        ROOT / "quwoquan_service" / "go.mod"
    ).read_text(encoding="utf-8")
    if "quwoquan_provider_protocol_substitute" in service_go_mod:
        issues.append("first-party service module depends on protocol substitute module")
    app_pubspec = (ROOT / "quwoquan_app" / "pubspec.yaml").read_text(
        encoding="utf-8"
    )
    if any(token in app_pubspec for token in FORBIDDEN):
        issues.append("App package depends on Provider substitute")

    for compose in (
        ROOT / "quwoquan_service" / "services"
    ).glob("*/deploy/compose.yaml"):
        source = compose.read_text(encoding="utf-8")
        if "provider-protocol-substitute/ca.crt" in source:
            issues.append(
                f"first-party Compose embeds substitute CA: {compose.relative_to(ROOT)}"
            )

    for token in FORBIDDEN:
        workload = ROOT / "quwoquan_ops" / "external" / token
        compose_path = workload / "deploy" / "compose.yaml"
        compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
        services = compose.get("services") if isinstance(compose, dict) else None
        service = services.get(token) if isinstance(services, dict) else None
        profiles = service.get("profiles") if isinstance(service, dict) else None
        expected_profile = f"nonprod-{token}"
        if profiles != [expected_profile]:
            issues.append(
                f"{token} must remain isolated behind profile {expected_profile}"
            )
        if (workload / "environments" / "prod").exists():
            issues.append(f"{token} must not have a Prod environment")

    if issues:
        print("[verify_provider_substitute_prod_purity] FAIL")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("[verify_provider_substitute_prod_purity] OK")
    print(
        "Prod selected bindings, renderer, first-party module graphs and "
        "Compose roots exclude substitute implementation/TLS material."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
