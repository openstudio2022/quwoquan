from __future__ import annotations

import json
import tempfile
from pathlib import Path

import yaml

from quwoquan_ops.gate import verify_prod_rollout_stackctl_contract as gate


ROOT = Path(__file__).resolve().parents[4]


def _write_prod_environment_workflow(path: Path, jobs: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump({"jobs": jobs}), encoding="utf-8")


def test_prod_environment_binding_distinguishes_dry_run_from_real_apply() -> None:
    assert gate.prod_environment_job_issues(
        ROOT / ".github/workflows/deploy-prod-auto.yml"
    ) == []


def test_prod_environment_binding_rejects_unprotected_or_unauthorized_jobs() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        workflow = Path(temporary) / "deploy-prod-auto.yml"
        _write_prod_environment_workflow(
            workflow,
            {
                "prod_rollout": {"environment": "release-validation"},
                "prod_soak_acceptance": {"environment": "production"},
                "unreviewed": {
                    "environment": {"name": "${{ true && 'production' || 'dev' }}"}
                },
            },
        )

        issues = gate.prod_environment_job_issues(workflow)

    assert any("unreviewed" in issue for issue in issues)
    assert any("exact dry-run release-validation" in issue for issue in issues)


def test_mainline_image_build_uses_governed_context_and_base_images() -> None:
    workflow = (ROOT / ".github/workflows/service_pipeline.yml").read_text(
        encoding="utf-8"
    )

    assert '"${{ matrix.context }}"' in workflow
    assert "matrix.environment" in workflow
    assert "matrix.runtime_image_owner" in workflow
    assert "matrix.image_name" in workflow
    assert "QWQ_ARTIFACT_ENVIRONMENT=${{ matrix.environment }}" in workflow
    assert "QWQ_ARTIFACT_CONFIG_DIGEST=$ARTIFACT_CONFIG_DIGEST" in workflow
    assert "release-image-sbom/${{ matrix.environment }}--${{ matrix.runtime_image_owner }}.spdx.json" in workflow
    assert "id: base_images" in workflow
    assert "GO_BASE_IMAGE: ${{ steps.base_images.outputs.go_base_image }}" in workflow
    assert "ALPINE_BASE_IMAGE: ${{ steps.base_images.outputs.alpine_base_image }}" in workflow
    assert "PYTHON_BASE_IMAGE: ${{ steps.base_images.outputs.python_base_image }}" in workflow
    assert '--build-arg "GO_BASE_IMAGE=$GO_BASE_IMAGE"' in workflow
    assert '--build-arg "ALPINE_BASE_IMAGE=$ALPINE_BASE_IMAGE"' in workflow
    assert '--build-arg "PYTHON_BASE_IMAGE=$PYTHON_BASE_IMAGE"' in workflow
    assert '--cache-from "type=registry,ref=' in workflow
    assert '--cache-to "type=registry,ref=' in workflow


def test_prod_hosted_build_images_match_their_governed_repositories() -> None:
    runtime = json.loads(
        (ROOT / "quwoquan_ops/environments/prod/runtime.yaml").read_text(
            encoding="utf-8"
        )
    )
    build_images = runtime["targets"]["prod-hosted"]["buildImages"]

    assert build_images["goBaseImage"] == (
        "docker.io/library/golang:1.24-bookworm@sha256:"
        "1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac"
    )
    assert (
        build_images["alpineBaseImage"]
        == "docker.io/library/alpine:3.22@sha256:14358309a308569c32bdc37e2e0e9694be33a9d99e68afb0f5ff33cc1f695dce"
    )
    assert build_images["pythonBaseImage"] == (
        "docker.io/library/python:3.11-slim-bookworm@sha256:"
        "b18992999dbe963a45a8a4da40ac2b1975be1a776d939d098c647482bcad5cba"
    )

    dockerfiles = sorted(
        (ROOT / "quwoquan_service/services").glob("*/build/Dockerfile")
    )
    dockerfiles.append(
        ROOT / "quwoquan_service/control-plane/platform-ops/build/Dockerfile"
    )
    for dockerfile in dockerfiles:
        text = dockerfile.read_text(encoding="utf-8")
        if "ARG GO_BASE_IMAGE\n" in text:
            assert (
                "FROM --platform=${BUILDPLATFORM} ${GO_BASE_IMAGE} AS builder"
                in text
            ), dockerfile
            assert "ARG TARGETOS\n" in text, dockerfile
            assert "ARG TARGETARCH\n" in text, dockerfile
            assert (
                "CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH}" in text
            ), dockerfile
        assert "--allow-untrusted" not in text, dockerfile


def test_runtime_image_owners_embed_environment_artifact_identity() -> None:
    dockerfiles = [
        ROOT / "quwoquan_service/cmd/service-core/Dockerfile",
        ROOT / "quwoquan_service/services/recommendation-service/build/Dockerfile",
        ROOT / "quwoquan_service/services/realtime-gateway/build/Dockerfile",
        ROOT / "quwoquan_service/services/rtc-service/build/Dockerfile",
        ROOT / "quwoquan_service/services/product-ops-service/build/Dockerfile",
        ROOT / "quwoquan_service/control-plane/platform-ops/build/Dockerfile",
    ]
    for dockerfile in dockerfiles:
        text = dockerfile.read_text(encoding="utf-8")
        assert "ARG QWQ_ARTIFACT_ENVIRONMENT" in text, dockerfile
        assert "ARG QWQ_ARTIFACT_CONFIG_DIGEST" in text, dockerfile
        assert "qwq.environment-artifact-identity" in text, dockerfile
        assert "artifact-identity.json" in text, dockerfile

    platform = dockerfiles[-1].read_text(encoding="utf-8")
    assert "COPY quwoquan_ops/external/" not in platform
    assert "cp -R /build/quwoquan_ops/environments /build/quwoquan_ops/external" not in platform
    assert "${QWQ_ARTIFACT_ENVIRONMENT}" in platform
    assert 'cp -R "$service_root/config" "$service_root/environments"' not in platform


def test_mainline_image_build_does_not_create_unbounded_actions_storage() -> None:
    workflow = (ROOT / ".github/workflows/service_pipeline.yml").read_text(
        encoding="utf-8"
    )

    assert 'DOCKER_BUILD_RECORD_UPLOAD: "false"' in workflow
    assert "cache-from: type=gha" not in workflow
    assert "cache-to: type=gha" not in workflow
    assert gate.main() == 0


def test_mainline_image_build_fails_closed_with_signed_attestations() -> None:
    workflow = (ROOT / ".github/workflows/service_pipeline.yml").read_text(
        encoding="utf-8"
    )

    assert "--sbom=true" in workflow
    assert "--provenance=mode=max" in workflow
    assert "actions/attest@f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6" in workflow
    assert "Verify signed provenance, SBOM, signer and issuer" in workflow
    assert "continue-on-error" not in workflow.split("  build-release-images:", 1)[1].split(
        "  validate-deploy:", 1
    )[0]


def test_mainline_release_delivery_uses_bounded_same_input_retries() -> None:
    workflow = (ROOT / ".github/workflows/service_pipeline.yml").read_text(
        encoding="utf-8"
    )
    document = yaml.safe_load(workflow)
    jobs = document["jobs"]
    image_job = jobs["build-release-images"]
    release_steps = {
        step.get("id"): step
        for step in jobs["validate-deploy"]["steps"]
        if step.get("id")
    }
    release_runs = [
        str(step.get("run") or "") for step in jobs["validate-deploy"]["steps"]
    ]

    assert image_job["strategy"]["fail-fast"] is False
    for attempt in (1, 2, 3):
        release_login = release_steps[f"release_registry_login_attempt_{attempt}"]
        assert release_login["uses"].startswith("docker/login-action@")
        release = release_steps[f"release_bundle_attempt_{attempt}"]
        assert release["uses"].startswith("docker/build-push-action@")
        assert release["with"] == release_steps["release_bundle_attempt_1"]["with"]

    assert release_steps["release_registry_login_attempt_1"]["continue-on-error"] is True
    assert release_steps["release_registry_login_attempt_2"]["continue-on-error"] is True
    assert release_steps["release_bundle_attempt_1"]["continue-on-error"] is True
    assert release_steps["release_bundle_attempt_2"]["continue-on-error"] is True
    assert release_runs.count("sleep 5") == 2
    assert release_runs.count("sleep 15") == 2
    assert "release artifact push failed after 3 bounded attempts" in workflow
    assert ":latest" not in workflow


def test_mainline_qemu_setup_is_digest_pinned() -> None:
    workflow = (ROOT / ".github/workflows/service_pipeline.yml").read_text(
        encoding="utf-8"
    )
    document = yaml.safe_load(workflow)
    steps = document["jobs"]["build-release-images"]["steps"]
    qemu = next(step for step in steps if str(step.get("uses") or "").startswith("docker/setup-qemu-action@"))
    assert qemu["uses"] == "docker/setup-qemu-action@c7c53464625b32c7a7e944ae62b3e17d2b600130"
    assert qemu["with"] == {
        "image": (
            "docker.io/tonistiigi/binfmt@sha256:"
            "b4c6a09270133b3c5b4dff94f83067df4dd27eced195fc6a1dbad102999e24dd"
        ),
        "platforms": "amd64",
        "cache-image": False,
    }


def test_mainline_pipeline_uses_controlled_self_hosted_amd64_builder() -> None:
    workflow = (ROOT / ".github/workflows/service_pipeline.yml").read_text(
        encoding="utf-8"
    )

    assert workflow.count("runs-on: [self-hosted, macOS, ARM64]") == 5
    assert "runs-on: ubuntu-latest" not in workflow
    assert "actions/cache@0057852bfaa89a56745cba8c7296529d2fc39830" in workflow
    assert (
        "docker/setup-qemu-action@c7c53464625b32c7a7e944ae62b3e17d2b600130"
        in workflow
    )
    assert (
        "image: docker.io/tonistiigi/binfmt@sha256:"
        "b4c6a09270133b3c5b4dff94f83067df4dd27eced195fc6a1dbad102999e24dd"
        in workflow
    )
    assert "platforms: amd64" in workflow
    assert "cache-image: false" in workflow
    assert workflow.count("version: v0.35.0") == 2
    assert workflow.count("cache-binary: false") == 2
    assert workflow.count("clean: false") == 2
    assert 'cache_root="${RUNNER_TEMP}/quwoquan-service-pipeline/go-${RUNNER_ARCH}"' in workflow
    assert 'echo "GOCACHE=${cache_root}/go-build" >> "$GITHUB_ENV"' in workflow
    assert 'echo "GOMODCACHE=${cache_root}/go-mod" >> "$GITHUB_ENV"' in workflow
    assert "type=registry" in workflow
    assert "github.workspace }}/.qwq_output/env/repo/local/ci/cache/go" not in workflow
