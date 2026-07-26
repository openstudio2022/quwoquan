from __future__ import annotations

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


def test_mainline_image_build_does_not_create_unbounded_actions_storage() -> None:
    workflow = (ROOT / ".github/workflows/service_pipeline.yml").read_text(
        encoding="utf-8"
    )

    assert 'DOCKER_BUILD_RECORD_UPLOAD: "false"' in workflow
    assert "cache-from: type=gha" not in workflow
    assert "cache-to: type=gha" not in workflow
    assert gate.main() == 0
