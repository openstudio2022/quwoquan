#!/usr/bin/env python3
"""Verify cloud images bind one environment during build, never at runtime.

Trigger: runtime image Dockerfiles, package image builder, or top-level service entrypoints.
Block: a runtime image lacks immutable artifact identity, a service skips startup validation,
or platform-ops packages all environments/nonprod external sources into one image.
Repair: restore build-time QWQ_ARTIFACT_* args, artifactidentity validation, and current-env-only
runtime facts, then rerun this gate and its local contract.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RUNTIME_DOCKERFILES = (
    "quwoquan_service/cmd/service-core/Dockerfile",
    "quwoquan_service/services/recommendation-service/build/Dockerfile",
    "quwoquan_service/services/realtime-gateway/build/Dockerfile",
    "quwoquan_service/services/rtc-service/build/Dockerfile",
    "quwoquan_service/services/product-ops-service/build/Dockerfile",
    "quwoquan_service/control-plane/platform-ops/build/Dockerfile",
)
GO_ENTRYPOINTS = (
    "quwoquan_service/cmd/service-core/main.go",
    "quwoquan_service/services/realtime-gateway/cmd/api/main.go",
    "quwoquan_service/services/rtc-service/cmd/api/main.go",
    "quwoquan_service/services/product-ops-service/cmd/api/main.go",
    "quwoquan_service/control-plane/platform-ops/cmd/api/main.go",
)
PYTHON_ENTRYPOINT = "quwoquan_service/services/recommendation-service/cmd/api/main.py"
BUILDER = "quwoquan_ops/cli/commands/runtime_image_composition.py"
PLATFORM_DOCKERFILE = (
    "quwoquan_service/control-plane/platform-ops/build/Dockerfile"
)


def collect_issues(root: Path = ROOT) -> list[str]:
    issues: list[str] = []
    for relative in RUNTIME_DOCKERFILES:
        source = (root / relative).read_text(encoding="utf-8")
        for marker in (
            "ARG QWQ_ARTIFACT_ENVIRONMENT",
            "ARG QWQ_ARTIFACT_CONFIG_DIGEST",
            "qwq.environment-artifact-identity",
            "artifact-identity.json",
        ):
            if marker not in source:
                issues.append(f"{relative}: missing {marker}")
    builder = (root / BUILDER).read_text(encoding="utf-8")
    for marker in (
        '"QWQ_ARTIFACT_ENVIRONMENT"',
        '"QWQ_ARTIFACT_CONFIG_DIGEST"',
        "_artifact_identity_build_args",
    ):
        if marker not in builder:
            issues.append(f"{BUILDER}: package builder missing {marker}")
    for relative in GO_ENTRYPOINTS:
        source = (root / relative).read_text(encoding="utf-8")
        if "artifactidentity.LoadAndValidate(" not in source:
            issues.append(f"{relative}: startup does not validate embedded identity")
    python_source = (root / PYTHON_ENTRYPOINT).read_text(encoding="utf-8")
    if "verify_embedded_artifact_identity()" not in python_source:
        issues.append(f"{PYTHON_ENTRYPOINT}: startup does not validate embedded identity")
    service_root = root / "quwoquan_service" / "services"
    for path in sorted(service_root.rglob("*.go")):
        if "generated" in path.parts or "tests" in path.parts or path.name.endswith("_test.go"):
            continue
        if "ExternalProviderBindingFor(" in path.read_text(encoding="utf-8"):
            issues.append(
                f"{path.relative_to(root)}: production source selects Provider binding by environment"
            )
    generated_bindings = tuple(service_root.glob("*/generated/**/external_provider_bindings.g.go"))
    if not generated_bindings:
        issues.append("generated Provider binding governance views are missing")
    for path in generated_bindings:
        source = path.read_text(encoding="utf-8")
        if "func CompiledBindingFor(capabilityID string)" not in source:
            issues.append(
                f"{path.relative_to(root)}: generated governance view lacks fail-closed production API"
            )
    platform = (root / PLATFORM_DOCKERFILE).read_text(encoding="utf-8")
    for forbidden in (
        "COPY quwoquan_ops/external/",
        "cp -R /build/quwoquan_ops/environments /build/quwoquan_ops/external",
        'cp -R "$service_root/config" "$service_root/environments"',
    ):
        if forbidden in platform:
            issues.append(
                f"{PLATFORM_DOCKERFILE}: cross-environment runtime facts remain: {forbidden}"
            )
    if "${QWQ_ARTIFACT_ENVIRONMENT}" not in platform:
        issues.append(f"{PLATFORM_DOCKERFILE}: runtime facts are not environment-scoped")
    return issues


def main() -> int:
    issues = collect_issues()
    if issues:
        print("[verify_cloud_environment_artifact_binding] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_cloud_environment_artifact_binding] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
