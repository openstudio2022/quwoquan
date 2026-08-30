"""Workflow scans distinguish stackctl verify from deploy command blocks.

spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-003
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WORKFLOWS = (
    ROOT / ".github/workflows/app-env-device-matrix-self-hosted.yml",
    ROOT / ".github/workflows/deploy-prod-auto.yml",
)


def _stackctl_blocks(text: str, command: str) -> list[str]:
    lines = text.splitlines()
    blocks: list[str] = []
    marker = f"python3 quwoquan_ops/cli/stackctl.py {command} \\"
    for index, line in enumerate(lines):
        if marker not in line:
            continue
        block = [line]
        cursor = index + 1
        while cursor < len(lines):
            continuation = lines[cursor]
            block.append(continuation)
            if not continuation.rstrip().endswith("\\"):
                break
            cursor += 1
        blocks.append("\n".join(block))
    return blocks


def test_verify_blocks_never_use_retired_reuse_package() -> None:
    verify_blocks = [
        block
        for workflow in WORKFLOWS
        for block in _stackctl_blocks(workflow.read_text(encoding="utf-8"), "verify")
    ]
    assert verify_blocks, "workflow scan must discover stackctl verify command blocks"
    assert all("--reuse-package" not in block for block in verify_blocks)


def test_deploy_blocks_keep_legitimate_reuse_package() -> None:
    workflow = WORKFLOWS[1].read_text(encoding="utf-8")
    deploy_blocks = _stackctl_blocks(workflow, "deploy")
    reuse_blocks = [block for block in deploy_blocks if "--reuse-package" in block]
    assert len(reuse_blocks) == 5
    assert all("--target prod-hosted" in block for block in reuse_blocks)
