from __future__ import annotations

import json
from pathlib import Path

import yaml

from quwoquan_ops.gate import verify_prod_rollout_stackctl_contract as gate


ROOT = Path(__file__).resolve().parents[3]


def test_mainline_image_build_uses_governed_context_and_base_images() -> None:
    workflow = (ROOT / ".github/workflows/service_pipeline.yml").read_text(
        encoding="utf-8"
    )

    assert "context: quwoquan_service" in workflow
    assert "id: base_images" in workflow
    assert "GO_BASE_IMAGE: ${{ steps.base_images.outputs.go_base_image }}" in workflow
    assert "ALPINE_BASE_IMAGE: ${{ steps.base_images.outputs.alpine_base_image }}" in workflow
    assert "PYTHON_BASE_IMAGE: ${{ steps.base_images.outputs.python_base_image }}" in workflow
    assert '--build-arg "GO_BASE_IMAGE=$GO_BASE_IMAGE"' in workflow
    assert '--build-arg "ALPINE_BASE_IMAGE=$ALPINE_BASE_IMAGE"' in workflow
    assert '--build-arg "PYTHON_BASE_IMAGE=$PYTHON_BASE_IMAGE"' in workflow


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


def test_mainline_image_build_does_not_create_unbounded_actions_storage() -> None:
    workflow = (ROOT / ".github/workflows/service_pipeline.yml").read_text(
        encoding="utf-8"
    )

    assert 'DOCKER_BUILD_RECORD_UPLOAD: "false"' in workflow
    assert "cache-from: type=gha" not in workflow
    assert "cache-to: type=gha" not in workflow
    assert gate.main() == 0


def test_mainline_image_build_retries_only_transient_ghcr_oauth_eof() -> None:
    workflow = (ROOT / ".github/workflows/service_pipeline.yml").read_text(
        encoding="utf-8"
    )

    assert "登录镜像仓库（重试瞬时网络失败）" in workflow
    assert workflow.count("for attempt in 1 2 3; do") >= 2
    assert "failed to fetch oauth token:.*EOF" in workflow
    assert "https://ghcr.io/(token|v2/).*EOF" in workflow
    assert "--attest type=sbom" in workflow
    assert "--attest type=provenance,mode=max" in workflow
    assert 'docker/build-push-action@ca052bb54ab0790a636c9b5f226502c73d547a25' in workflow


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


def test_mainline_qemu_setup_uses_bounded_same_digest_retries() -> None:
    workflow = (ROOT / ".github/workflows/service_pipeline.yml").read_text(
        encoding="utf-8"
    )
    document = yaml.safe_load(workflow)
    steps = document["jobs"]["build-release-images"]["steps"]
    steps_by_id = {step.get("id"): step for step in steps if step.get("id")}
    attempts = [steps_by_id[f"qemu_attempt_{attempt}"] for attempt in (1, 2, 3)]

    assert all(
        step["uses"]
        == "docker/setup-qemu-action@c7c53464625b32c7a7e944ae62b3e17d2b600130"
        for step in attempts
    )
    assert all(step["with"] == attempts[0]["with"] for step in attempts)
    assert attempts[0]["continue-on-error"] is True
    assert attempts[1]["continue-on-error"] is True
    assert "continue-on-error" not in attempts[2]
    assert attempts[0]["with"] == {
        "image": (
            "docker.io/tonistiigi/binfmt@sha256:"
            "b4c6a09270133b3c5b4dff94f83067df4dd27eced195fc6a1dbad102999e24dd"
        ),
        "platforms": "amd64",
        "cache-image": False,
    }
    runs = [str(step.get("run") or "") for step in steps]
    assert runs.count("sleep 5") == 1
    assert runs.count("sleep 15") == 1


def test_mainline_pipeline_uses_controlled_self_hosted_amd64_builder() -> None:
    workflow = (ROOT / ".github/workflows/service_pipeline.yml").read_text(
        encoding="utf-8"
    )

    assert workflow.count("runs-on: [self-hosted, macOS, ARM64]") == 5
    assert "runs-on: ubuntu-latest" not in workflow
    assert "actions/cache@" not in workflow
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
    assert workflow.count("clean: false") == 5
    assert 'cache_root="${RUNNER_TEMP}/quwoquan-service-pipeline/${GITHUB_RUN_ID}"' in workflow
    assert 'echo "GOCACHE=${cache_root}/go-build" >> "$GITHUB_ENV"' in workflow
    assert 'echo "GOMODCACHE=${cache_root}/go-mod" >> "$GITHUB_ENV"' in workflow
    assert 'docker_config="${RUNNER_TEMP}/quwoquan-service-pipeline/${GITHUB_RUN_ID}/${{ matrix.service }}/docker-config"' in workflow
    assert workflow.count('docker_context="$(docker context show)"') == 2
    assert workflow.count('docker context inspect "$docker_context"') == 2
    assert workflow.count('DOCKER_HOST="$docker_host" docker version >/dev/null') == 2
    assert workflow.count('echo "DOCKER_HOST=${docker_host}" >> "$GITHUB_ENV"') == 2
    assert 'echo "DOCKER_CONFIG=${docker_config}" >> "$GITHUB_ENV"' in workflow
    assert "设置 release artifact 隔离 Docker 配置" in workflow
    assert "${{ runner.temp }}" not in workflow
    assert "github.workspace }}/.qwq_output/env/repo/local/ci/cache/go" not in workflow
