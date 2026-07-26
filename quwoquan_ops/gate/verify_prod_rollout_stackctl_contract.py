#!/usr/bin/env python3
from __future__ import annotations

import runpy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = [
    ROOT / ".github" / "workflows" / "deploy-prod-gray.yml",
    ROOT / ".github" / "workflows" / "deploy-prod-auto.yml",
]
SERVICE_PIPELINE = ROOT / ".github" / "workflows" / "service_pipeline.yml"
ACCESS_MANIFEST = ROOT / "quwoquan_ops" / "environments" / "prod" / "access-isolation.yaml"
RELEASE_GENERATOR = (
    ROOT / "quwoquan_ops" / "cli" / "prod" / "generate_mainline_release_artifact.py"
)


def main() -> int:
    issues: list[str] = []
    for path in WORKFLOWS:
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT)
        if "quwoquan_ops/cli/stackctl.py deploy" not in text:
            issues.append(f"{rel} must call stackctl.py deploy")
        if "--target prod-hosted" not in text:
            issues.append(f"{rel} must deploy prod-hosted through stackctl")
        for token in (
            "--release-manifest",
            "fetch_mainline_release_artifact.py",
            "release_artifact_ref",
            "PROD_PROMETHEUS_URL",
            "PROD_RELEASE_STATE_DIR",
            "PROD_BACKUP_RECOVERY_RECEIPT",
            "--backup-recovery-receipt",
            "group: prod-hosted-release",
        ):
            if token not in text:
                issues.append(f"{rel} missing governed rollout token: {token}")
        for token in (
            "--error-rate",
            "--p95-ms",
            "--redis-error-rate",
            "inputs.error_rate",
            "inputs.p95_ms",
            "inputs.redis_error_rate",
        ):
            if token in text:
                issues.append(
                    f"{rel} permits caller-supplied SLO evidence instead of Prometheus readback: {token}"
                )
        for forbidden in (
            "name: mainline-release-artifact",
            "name: resolved-mainline-release-artifact",
            "name: governed-mainline-release-artifact",
            "make config-gray-rollout",
            "make config-slo-gate",
            "make config-rollback",
            "bash quwoquan_ops/cli/prod/deploy_to_prod.sh",
        ):
            if forbidden in text:
                issues.append(f"{rel} still contains legacy rollout entry: {forbidden}")

    access = yaml.safe_load(ACCESS_MANIFEST.read_text(encoding="utf-8")) or {}
    expected_images = {
        str(service)
        for plane in access.get("planes") or []
        for service in plane.get("rootlessGovernedComposeServices") or []
    }
    generator_globals = runpy.run_path(str(RELEASE_GENERATOR))
    declared_images = set(generator_globals.get("DEPLOYED_SERVICES") or ())
    if declared_images != expected_images:
        issues.append(
            "mainline release image set must equal prod governed compose services: "
            f"missing={sorted(expected_images - declared_images)} "
            f"extra={sorted(declared_images - expected_images)}"
        )

    pipeline_text = SERVICE_PIPELINE.read_text(encoding="utf-8")
    for service in sorted(expected_images):
        if f"service: {service}" not in pipeline_text:
            issues.append(f"{SERVICE_PIPELINE.relative_to(ROOT)} does not build {service}")
    for token in (
        "sbom: true",
        "provenance: mode=max",
        "finalize_mainline_release_artifact.py",
        "collect_mainline_image_descriptors.py",
        "/release-artifact:sha-${{ github.sha }}",
        'DOCKER_BUILD_RECORD_UPLOAD: "false"',
        "id: base_images",
        "GO_BASE_IMAGE=${{ steps.base_images.outputs.go_base_image }}",
        "ALPINE_BASE_IMAGE=${{ steps.base_images.outputs.alpine_base_image }}",
        "PYTHON_BASE_IMAGE=${{ steps.base_images.outputs.python_base_image }}",
    ):
        if token not in pipeline_text:
            issues.append(
                f"{SERVICE_PIPELINE.relative_to(ROOT)} missing release provenance token: {token}"
            )
    for forbidden in (
        "actions/upload-artifact@",
        "name: mainline-release-input",
        "name: mainline-release-artifact",
        "pattern: mainline-image-*",
        "cache-from: type=gha",
        "cache-to: type=gha",
    ):
        if forbidden in pipeline_text:
            issues.append(
                f"{SERVICE_PIPELINE.relative_to(ROOT)} still permits ungoverned Actions storage: {forbidden}"
            )
    if "recommendation-service\n            image_name: recommendation-service\n            context: quwoquan_service" not in pipeline_text:
        issues.append(
            f"{SERVICE_PIPELINE.relative_to(ROOT)} must build recommendation-service from quwoquan_service context"
        )

    if issues:
        print("[verify_prod_rollout_stackctl_contract] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("[verify_prod_rollout_stackctl_contract] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
