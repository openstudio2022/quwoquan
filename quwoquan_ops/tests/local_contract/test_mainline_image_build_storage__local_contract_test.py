from __future__ import annotations

import json
from pathlib import Path

from quwoquan_ops.gate import verify_prod_rollout_stackctl_contract as gate


ROOT = Path(__file__).resolve().parents[3]


def test_mainline_image_build_uses_governed_context_and_base_images() -> None:
    workflow = (ROOT / ".github/workflows/service_pipeline.yml").read_text(
        encoding="utf-8"
    )

    assert "context: quwoquan_service" in workflow
    assert "id: base_images" in workflow
    assert "GO_BASE_IMAGE=${{ steps.base_images.outputs.go_base_image }}" in workflow
    assert "ALPINE_BASE_IMAGE=${{ steps.base_images.outputs.alpine_base_image }}" in workflow
    assert "PYTHON_BASE_IMAGE=${{ steps.base_images.outputs.python_base_image }}" in workflow


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
    assert build_images["pythonBaseImage"].startswith("docker.io/library/python:")

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
    assert "${{ runner.temp }}" not in workflow
    assert "github.workspace }}/.qwq_output/env/repo/local/ci/cache/go" not in workflow
