#!/usr/bin/env python3
"""Verify cloud image bytes stay environment-agnostic and identity mounts exist.

Trigger: runtime image Dockerfiles, package image builder, Compose fragments, or
top-level service entrypoints.
Block: a runtime image bakes environment identity or an environment config tree
into its bytes, the deploy plane stops materializing the identity mount, a
service skips startup validation, or production source selects Provider
bindings by environment at runtime.
Repair: keep Dockerfiles free of QWQ_ARTIFACT_* args, keep the deploy-side
identity mount materializer and Compose mounts, restore artifactidentity
validation, then rerun this gate and its local contract.
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
# 消费单环境 CompiledBindingFor 的 Go 镜像必须在构建期套用 overlay。缺 overlay 时
# 镜像仍能构建成功，但编译进去的是 fail-closed 空视图，服务只能在 listener 前退出。
# DEC-005 信任域裁决保留该编译期固化：镜像按 nonprod/prod 两档分叉，不按环境分叉。
PROVIDER_BINDING_OVERLAY_DOCKERFILES = (
    "quwoquan_service/cmd/service-core/Dockerfile",
    "quwoquan_service/services/realtime-gateway/build/Dockerfile",
    "quwoquan_service/services/rtc-service/build/Dockerfile",
    "quwoquan_service/services/product-ops-service/build/Dockerfile",
)
BUILDER = "quwoquan_ops/cli/commands/runtime_image_composition.py"
PLATFORM_DOCKERFILE = (
    "quwoquan_service/control-plane/platform-ops/build/Dockerfile"
)
COMPOSE_FRAGMENTS_GLOBS = (
    "quwoquan_service/services/*/deploy/compose.yaml",
    "quwoquan_service/control-plane/platform-ops/deploy/compose.yaml",
)
IDENTITY_MOUNT_MARKER = (
    ":/etc/quwoquan/artifact-identity.json:ro"
)


def collect_issues(root: Path = ROOT) -> list[str]:
    issues: list[str] = []
    # 镜像字节必须环境无关：禁止环境身份与环境配置树进入任何 runtime image。
    for relative in RUNTIME_DOCKERFILES:
        source = (root / relative).read_text(encoding="utf-8")
        for forbidden in (
            "ARG QWQ_ARTIFACT_ENVIRONMENT",
            "ARG QWQ_ARTIFACT_CONFIG_DIGEST",
            "> /etc/quwoquan/artifact-identity.json",
        ):
            if forbidden in source:
                issues.append(
                    f"{relative}: image bytes bake environment identity: {forbidden}"
                )
    for relative in PROVIDER_BINDING_OVERLAY_DOCKERFILES:
        source = (root / relative).read_text(encoding="utf-8")
        for marker in (
            "ARG QWQ_PROVIDER_BINDING_MANIFEST_DIGEST",
            "from=qwq_provider_bindings",
            "-overlay=/run/qwq-provider-bindings/go.overlay.json",
        ):
            if marker not in source:
                issues.append(
                    f"{relative}: build does not compile the trust-domain "
                    f"Provider binding: missing {marker}"
                )
    builder = (root / BUILDER).read_text(encoding="utf-8")
    for forbidden in (
        '"QWQ_ARTIFACT_ENVIRONMENT"',
        '"QWQ_ARTIFACT_CONFIG_DIGEST"',
    ):
        if forbidden in builder:
            issues.append(
                f"{BUILDER}: package builder injects environment identity "
                f"build args: {forbidden}"
            )
    if "_bind_artifact_identity_mount_material" not in builder:
        issues.append(
            f"{BUILDER}: deploy plane does not materialize the artifact "
            "identity mount"
        )
    # 启动校验保留：identity 文件来自部署面挂载，服务仍必须 fail-closed 校验。
    for relative in GO_ENTRYPOINTS:
        source = (root / relative).read_text(encoding="utf-8")
        if "artifactidentity.LoadAndValidate(" not in source:
            issues.append(f"{relative}: startup does not validate mounted identity")
    python_source = (root / PYTHON_ENTRYPOINT).read_text(encoding="utf-8")
    if "verify_embedded_artifact_identity()" not in python_source:
        issues.append(f"{PYTHON_ENTRYPOINT}: startup does not validate mounted identity")
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
        "COPY quwoquan_ops/environments/",
        "COPY quwoquan_ops/external/",
        "/runtime-facts",
        "${QWQ_ARTIFACT_ENVIRONMENT}",
    ):
        if forbidden in platform:
            issues.append(
                f"{PLATFORM_DOCKERFILE}: environment runtime facts are baked "
                f"into image bytes: {forbidden}"
            )
    # 部署面挂载：所有一方 Compose fragment 必须挂载 artifact-identity.json。
    fragments: list[Path] = []
    for pattern in COMPOSE_FRAGMENTS_GLOBS:
        fragments.extend(sorted(root.glob(pattern)))
    if not fragments:
        issues.append("first-party Compose fragments are missing")
    for path in fragments:
        source = path.read_text(encoding="utf-8")
        if IDENTITY_MOUNT_MARKER not in source:
            issues.append(
                f"{path.relative_to(root)}: fragment does not mount the "
                "artifact identity file"
            )
    if ":/app:ro" not in (
        root / "quwoquan_service/control-plane/platform-ops/deploy/compose.yaml"
    ).read_text(encoding="utf-8"):
        issues.append(
            "platform-ops fragment does not mount the runtime facts tree"
        )
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
