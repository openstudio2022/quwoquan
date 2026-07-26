#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import (
    load_environment_topology,
    validate_environment_topology,
)
from quwoquan_ops.cli.lib.content_release_readiness import (
    load_content_release_readiness_policy,
)


def validate_service_build_image_contract() -> list[str]:
    """Require every local service build to consume topology-injected images."""
    service_root = ROOT / "quwoquan_service"
    compose_files = sorted(service_root.glob("services/*/deploy/compose.yaml"))
    compose_files.append(
        service_root / "control-plane/platform-ops/deploy/compose.yaml"
    )
    issues: list[str] = []
    for compose_file in compose_files:
        compose = compose_file.read_text(encoding="utf-8")
        if "GO_BASE_IMAGE:" not in compose:
            continue
        if "QWQ_COMPOSE_GO_BASE_IMAGE:?" not in compose:
            issues.append(f"{compose_file.relative_to(ROOT)} must require QWQ_COMPOSE_GO_BASE_IMAGE")
        if "QWQ_COMPOSE_ALPINE_BASE_IMAGE:?" not in compose:
            issues.append(
                f"{compose_file.relative_to(ROOT)} must require QWQ_COMPOSE_ALPINE_BASE_IMAGE"
            )
        if "GO_ALPINE_BASE_IMAGE" in compose:
            issues.append(f"{compose_file.relative_to(ROOT)} contains retired Go image input")

        dockerfile_ref = compose.split("dockerfile: ", 1)[1].splitlines()[0]
        dockerfile = next(
            (
                candidate
                for candidate in (ROOT / dockerfile_ref, service_root / dockerfile_ref)
                if candidate.is_file()
            ),
            None,
        )
        if dockerfile is None:
            issues.append(f"{compose_file.relative_to(ROOT)} references a missing Dockerfile")
            continue
        dockerfile_text = dockerfile.read_text(encoding="utf-8")
        if "ARG GO_BASE_IMAGE\n" not in dockerfile_text:
            issues.append(f"{dockerfile.relative_to(ROOT)} must not default GO_BASE_IMAGE")
        if "ARG ALPINE_BASE_IMAGE\n" not in dockerfile_text:
            issues.append(f"{dockerfile.relative_to(ROOT)} must not default ALPINE_BASE_IMAGE")
    return issues


def main() -> int:
    manifest = load_environment_topology()
    issues = validate_environment_topology(manifest)
    issues.extend(validate_service_build_image_contract())
    try:
        content_readiness = load_content_release_readiness_policy()
    except ValueError as exc:
        issues.append(f"content release readiness policy invalid: {exc}")
        content_readiness = None
    if issues:
        print("[verify-environment-assembly] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    summary = {
        "environments": sorted((manifest.get("environments") or {}).keys()),
        "targets": sorted((manifest.get("targets") or {}).keys()),
        "contentReleaseReadiness": (
            {
                "policyId": content_readiness.policy_id,
                "requirements": [
                    f"{requirement.phase.value}/{requirement.environment}:{requirement.target}"
                    for requirement in content_readiness.requirements
                ],
            }
            if content_readiness is not None
            else None
        ),
    }
    print("[verify-environment-assembly] OK")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
