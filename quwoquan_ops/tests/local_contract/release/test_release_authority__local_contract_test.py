# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-003.t1
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from quwoquan_ops.ci.promotion_evidence import PromotionEvidenceError, digest
from quwoquan_ops.ci.release_authority import (
    create_initial_release_authority,
    create_release_candidate_selection,
)
from quwoquan_ops.ci.release_tag_admission import (
    ReleaseTagAdmissionError,
    validate_product_version_manifest,
)

ROOT = Path(__file__).resolve().parents[4]
READBACK = {"login": "openstudio2022", "id": 12345}


def _activated_manifest(tmp_path: Path, authority_ref: dict[str, str] | None) -> Path:
    manifest = yaml.safe_load((ROOT / "quwoquan_ops/policies/product_version.yaml").read_text(encoding="utf-8"))
    manifest["releaseTrain"] = {
        "state": "active", "targetVersion": "1.1.0", "bump": "initial",
        "bumpReason": "first product release train", "compatibilityBoundary": "initial",
    }
    manifest["initialReleaseAuthority"] = {"status": "approved", "authorityFact": authority_ref}
    manifest["activation"] = {"decision": "active", "basis": "initial_release_authority_approved", "reasonCode": None}
    path = tmp_path / "product_version.yaml"
    path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def test_initial_release_authority_activates_train_only_with_exact_binding(tmp_path: Path) -> None:
    store = tmp_path / "store"
    path = create_initial_release_authority(
        store_root=store, repository="openstudio2022/quwoquan", target_version="1.1.0",
        approver_login="openstudio2022", approved_at="2026-09-06T12:00:00Z",
        basis="首个产品发布 train，对齐 pubspec 1.1.0", readback=READBACK,
    )
    fact = json.loads(path.read_text())
    assert fact["status"] == "approved" and fact["purpose"] == "activate_initial_product_release_train"
    ref = {"ref": path.relative_to(store).as_posix(), "digest": digest(path)}
    manifest = _activated_manifest(tmp_path, ref)
    _, _, state = validate_product_version_manifest(manifest_path=manifest, initial_release_authority=ref, evidence_root=store)
    assert state == "active"
    # 缺 authority 读回时 active train 不成立
    with pytest.raises(ReleaseTagAdmissionError, match="VERSION_AUTHORITY_INVALID"):
        validate_product_version_manifest(manifest_path=manifest, initial_release_authority=None, evidence_root=store)
    # authority 与 manifest 引用不一致时阻断
    other = create_initial_release_authority(
        store_root=store, repository="openstudio2022/quwoquan", target_version="1.1.0",
        approver_login="openstudio2022", approved_at="2026-09-06T12:30:00Z", basis="other", readback=READBACK,
    )
    other_ref = {"ref": other.relative_to(store).as_posix(), "digest": digest(other)}
    with pytest.raises(ReleaseTagAdmissionError, match="VERSION_AUTHORITY_INVALID"):
        validate_product_version_manifest(manifest_path=manifest, initial_release_authority=other_ref, evidence_root=store)
    # 审批人读回不匹配（冒名）拒绝
    with pytest.raises(PromotionEvidenceError, match="does not bind the approver"):
        create_initial_release_authority(
            store_root=store, repository="openstudio2022/quwoquan", target_version="1.1.0",
            approver_login="someone-else", approved_at="2026-09-06T12:00:00Z", basis="x", readback=READBACK,
        )


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()


def test_rc_selection_binds_main_reachable_commit_tree_and_manifest(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "user.email", "t@example.com")
    (repo / "a.txt").write_text("x\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "main")
    main = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-ref", "refs/remotes/origin/main", main)
    _git(repo, "checkout", "-q", "-b", "dev1.0")
    (repo / "b.txt").write_text("y\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "dev only")
    dev_only = _git(repo, "rev-parse", "HEAD")
    manifest = _activated_manifest(tmp_path, {"ref": "x.json", "digest": "sha256:" + "0" * 64})
    store = tmp_path / "store"
    path = create_release_candidate_selection(
        store_root=store, repository_root=repo, repository="openstudio2022/quwoquan", tag_name="v1.1.0-rc.1",
        source_git_sha=main, product_version_manifest=manifest, selector_login="openstudio2022",
        selected_at="2026-09-06T12:00:00Z", readback=READBACK,
    )
    fact = json.loads(path.read_text())
    assert fact["schema"] == "quwoquan_ops.release_candidate_selection_fact.v1" and fact["status"] == "approved"
    assert fact["sourceGitSha"] == main and fact["sourceTree"] == _git(repo, "show", "-s", "--format=%T", main)
    assert fact["productVersionManifestDigest"] == digest(manifest)
    with pytest.raises(PromotionEvidenceError, match="SOURCE_NOT_MAIN_REACHABLE"):
        create_release_candidate_selection(
            store_root=store, repository_root=repo, repository="openstudio2022/quwoquan", tag_name="v1.1.0-rc.2",
            source_git_sha=dev_only, product_version_manifest=manifest, selector_login="openstudio2022",
            selected_at="2026-09-06T12:00:00Z", readback=READBACK,
        )
    with pytest.raises(PromotionEvidenceError, match="rc.N"):
        create_release_candidate_selection(
            store_root=store, repository_root=repo, repository="openstudio2022/quwoquan", tag_name="v1.1.0",
            source_git_sha=main, product_version_manifest=manifest, selector_login="openstudio2022",
            selected_at="2026-09-06T12:00:00Z", readback=READBACK,
        )
