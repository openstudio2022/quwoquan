"""Main tree seal contract.

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001
"""
from __future__ import annotations

from pathlib import Path
import pytest
from quwoquan_ops.ci.main_tree_seal import build_main_tree_seal, write_create_once

D = "sha256:" + "a" * 64
TREE = "sha1:" + "b" * 40
SHA = "c" * 40


def manifest(status: str = "qualified") -> dict:
    return {"status": status, "releaseCompositionId": D, "evidenceSetDigest": D,
            "artifactDigest": D, "source": {"treeDigest": TREE}}


def test_seal_binds_same_synthetic_and_main_tree(tmp_path: Path) -> None:
    value = build_main_tree_seal(manifest=manifest(), synthetic_tree_digest=TREE,
        main_merge_sha=SHA, main_tree_digest=TREE, promotion_receipt={"ref": "promotion.json", "digest": D})
    assert value["releaseCompositionId"] == D
    assert value["sealDigest"].startswith("sha256:")
    output = tmp_path / "seal.json"
    write_create_once(output.resolve(), value)
    with pytest.raises(ValueError, match="CREATE_ONCE_CONFLICT"):
        write_create_once(output.resolve(), value)


def test_unqualified_or_tree_drift_is_blocked() -> None:
    with pytest.raises(ValueError, match="CANDIDATE_NOT_QUALIFIED"):
        build_main_tree_seal(manifest=manifest("artifact-complete"), synthetic_tree_digest=TREE,
            main_merge_sha=SHA, main_tree_digest=TREE, promotion_receipt={"ref": "p", "digest": D})
    with pytest.raises(ValueError, match="FINAL_TREE_DRIFT"):
        build_main_tree_seal(manifest=manifest(), synthetic_tree_digest=TREE,
            main_merge_sha=SHA, main_tree_digest="sha1:" + "d" * 40,
            promotion_receipt={"ref": "p", "digest": D})
