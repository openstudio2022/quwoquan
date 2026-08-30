#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

sys.dont_write_bytecode = True

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
from quwoquan_ops.cli.lib.immutable_image_composition import (
    compose_image_environment_key,
    first_party_service_names,
)


def _first_party_compose_files() -> dict[str, Path]:
    active_services = set(first_party_service_names(ROOT))
    files = {
        path.parents[1].name: path
        for path in (
            ROOT / "quwoquan_service" / "services"
        ).glob("*/deploy/compose.yaml")
        if path.parents[1].name in active_services
    }
    if "platform-ops-service" in active_services:
        files["platform-ops-service"] = (
            ROOT
            / "quwoquan_service"
            / "control-plane"
            / "platform-ops"
            / "deploy"
            / "compose.yaml"
        )
    return dict(sorted(files.items()))


def validate_first_party_image_composition_contract() -> list[str]:
    """Every first-party workload must consume one explicit immutable identity."""

    compose_files = _first_party_compose_files()
    discovered = set(first_party_service_names(ROOT))
    issues: list[str] = []
    if set(compose_files) != discovered:
        issues.append(
            "first-party compose/config owners differ: "
            f"compose={sorted(compose_files)} config={sorted(discovered)}"
        )
    for owner, compose_file in compose_files.items():
        relative = compose_file.relative_to(ROOT)
        if not compose_file.is_file():
            issues.append(f"{relative} is missing")
            continue
        raw = compose_file.read_text(encoding="utf-8")
        if ":latest" in raw:
            issues.append(f"{relative} contains mutable :latest")
        if "QWQ_COMPOSE_IMAGE_VERSION:-" in raw:
            issues.append(f"{relative} contains a fallback IMAGE_VERSION")
        try:
            document = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            issues.append(f"{relative} is invalid YAML: {exc}")
            continue
        services = document.get("services") if isinstance(document, dict) else None
        if not isinstance(services, dict) or not services:
            issues.append(f"{relative} has no services")
            continue
        expected_image_key = compose_image_environment_key(owner)
        first_party_workloads = 0
        for workload, spec in services.items():
            if not isinstance(spec, dict) or "build" not in spec:
                continue
            first_party_workloads += 1
            image = str(spec.get("image") or "")
            if not image.startswith(f"${{{expected_image_key}:?") or not image.endswith(
                "}"
            ):
                issues.append(
                    f"{relative} workload {workload} must require {expected_image_key}"
                )
            environment = spec.get("environment")
            image_version = (
                environment.get("IMAGE_VERSION")
                if isinstance(environment, dict)
                else None
            )
            if (
                not isinstance(image_version, str)
                or not image_version.startswith("${QWQ_COMPOSE_IMAGE_VERSION:?")
                or not image_version.endswith("}")
            ):
                issues.append(
                    f"{relative} workload {workload} must require "
                    "QWQ_COMPOSE_IMAGE_VERSION"
                )
        if first_party_workloads == 0:
            issues.append(f"{relative} has no first-party build workload")
    return issues


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
        if "FROM --platform=${BUILDPLATFORM} ${GO_BASE_IMAGE} AS builder" not in dockerfile_text:
            issues.append(
                f"{dockerfile.relative_to(ROOT)} must build Go on BUILDPLATFORM"
            )
        if "ARG TARGETOS\n" not in dockerfile_text or "ARG TARGETARCH\n" not in dockerfile_text:
            issues.append(
                f"{dockerfile.relative_to(ROOT)} must declare target OS and architecture"
            )
        if "CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH}" not in dockerfile_text:
            issues.append(
                f"{dockerfile.relative_to(ROOT)} must cross-compile Go for the image target"
            )
        if "ARG ALPINE_BASE_IMAGE\n" not in dockerfile_text:
            issues.append(f"{dockerfile.relative_to(ROOT)} must not default ALPINE_BASE_IMAGE")
        if "--allow-untrusted" in dockerfile_text:
            issues.append(
                f"{dockerfile.relative_to(ROOT)} must not bypass package signature checks"
            )

    service_pipeline = (
        ROOT / ".github/workflows/service_pipeline.yml"
    ).read_text(encoding="utf-8")
    # 收敛的是「从受治理的 prod runtime.yaml 取 prod-hosted 构建镜像」这件事本身，
    # 而不是取值表达式换行在哪里，所以先折叠空白再比对下标链。
    collapsed_pipeline = re.sub(r"\s+", "", service_pipeline)
    if (
        "quwoquan_ops/environments/prod/runtime.yaml" not in service_pipeline
        or '["targets"]["prod-hosted"]["buildImages"]' not in collapsed_pipeline
    ):
        issues.append("service pipeline must read prod-hosted governed build images")
    for image_variable, output in (
        ("GO_BASE_IMAGE", "go_base_image"),
        ("ALPINE_BASE_IMAGE", "alpine_base_image"),
        ("PYTHON_BASE_IMAGE", "python_base_image"),
    ):
        governed_output = (
            f"{image_variable}: "
            f"${{{{ steps.base_images.outputs.{output} }}}}"
        )
        shell_build_arg = f'--build-arg "{image_variable}=${image_variable}"'
        action_build_arg = (
            f"{image_variable}="
            f"${{{{ steps.base_images.outputs.{output} }}}}"
        )
        if (
            governed_output not in service_pipeline
            or (
                shell_build_arg not in service_pipeline
                and action_build_arg not in service_pipeline
            )
        ):
            issues.append(
                f"service pipeline must pass {image_variable} to release image builds"
            )
    return issues


def main() -> int:
    manifest = load_environment_topology()
    issues = validate_environment_topology(manifest)
    issues.extend(validate_first_party_image_composition_contract())
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
