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

    assert build_images["goBaseImage"].startswith("docker.io/library/golang:")
    assert build_images["alpineBaseImage"].startswith("docker.io/library/alpine:")
    assert build_images["pythonBaseImage"].startswith("docker.io/library/python:")


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
    assert "恢复自托管 Go 缓存可清理权限" in workflow
    assert 'chmod -R u+w "$cache_dir"' in workflow
