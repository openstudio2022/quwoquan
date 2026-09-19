"""仓身份只绑定 handoff，不令离线消费者依赖作者工作树或 Git 提交。"""
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-041
from __future__ import annotations

import json
from pathlib import Path

import pytest

from content.release.canonical import producer_release_handoff as handoff
from core.publish_repository import require_publish_repository
from core.schema import assert_valid


def _repository(path: Path, repository_id: str) -> None:
    (path / ".git").mkdir(parents=True)
    (path / "repository.json").write_text(json.dumps({
        "schema": "quwoquan_data.publish_repository.v2", "repositoryId": repository_id,
        "layoutVersion": 2,
    }), encoding="utf-8")


def test_repository_marker_has_no_duplicate_producer_contract_digest(tmp_path):
    _repository(tmp_path / "publish", "content-a")
    document = require_publish_repository(tmp_path / "publish")
    assert set(document) == {"schema", "repositoryId", "layoutVersion"}
    with pytest.raises(ValueError):
        assert_valid({**document, "producerContractDigest": "sha256:" + "a" * 64}, "publish", "repository")


def _release(root: Path, revision: str):
    from local_contract.release.test_producer_release_detachment__contract__local_contract_test import _sealed_handoff_fixture
    from core.release_layout import objects_merkle, payload_digest
    logical_ref = "entities/地点/景区/p0001/entity-a/1"
    sealed, row, _, _, _ = _sealed_handoff_fixture(
        root, logical_ref=logical_ref, review_ref=logical_ref,
    )
    counts = {"homepage": 1, "article": 0, "image": 0, "video": 0, "total": 1}
    targets = {key: value for key, value in counts.items() if key != "total"}
    cohort = {"schema": "quwoquan_data.release_cohort", "objectRefs": [logical_ref],
              "milestone": "M1", "producerBaselineRevision": revision, "expectedCarrierCounts": targets}
    desired_refs = {"creators": [], "entities": [logical_ref.removeprefix("entities/")], "posts": [], "tags": []}
    header = {"schema": "quwoquan_data.release", "releaseId": root.name, "sourceOwner": "qwq_data", "releaseKind": "content",
              "containsUnverifiedAssets": False, "rightsStatusCounts": {key: 0 for key in ("verified", "unverified", "restricted", "unknown")},
              "authorizationRequiredAssetIds": [], "acceptedCount": 0, "canonicalMerkle": objects_merkle(root),
              "executionIds": [], "sourceDigests": [{"algorithm": "sha256", "digest": "sha256:" + "a" * 64, "inputs": ["fixture-source"]}],
              "sourceRevision": "sha256:" + "b" * 64, "sourceDigest": "sha256:" + "a" * 64,
              "entityCatalogDigest": "sha256:" + "c" * 64,
              "counts": counts, "milestone": "M1", "milestoneTargets": targets}
    documents = {
        "cohort.json": cohort,
        "payload/release.json": header,
        "payload/desired_state.json": {"schema": "quwoquan_data.release_desired_state", "releaseId": root.name, "desiredRefs": desired_refs},
        "payload/index/objects.json": {"schema": "quwoquan_data.release_object_index", **desired_refs},
        "payload/sample_bundle.json": {"schema": "quwoquan_data.release_sample_bundle", **desired_refs},
    }
    for name, document in documents.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(handoff._canonical_bytes(document))
    return cohort, row, header, counts, handoff._digest((root / "payload/release.json").read_bytes()), payload_digest(root)


def test_writer_binds_identity_and_rejects_replay_from_another_repository(tmp_path, monkeypatch, capsys):
    """新建只隔离实时选池/里程碑检查；schema、落盘与所有离线重放校验均真实执行。"""
    publish = tmp_path / "publish"
    _repository(publish, "content-a")
    output = tmp_path / "output"
    releases = output / "data/releases"
    root = releases / "release-a"
    revision = "a" * 40
    cohort, query, header, counts, header_digest, release_digest = _release(root, revision)
    monkeypatch.setattr(handoff, "_validate_producer_baseline_revision", lambda value, **kwargs: value)
    real_release_check = handoff._validate_release_facts

    def release_check(**kwargs):
        # 本测试只构造一个真实 homepage，M1 的四载体数量门由既有 milestone 测试覆盖。
        if kwargs.get("policy_targets") is not None:
            return header, counts, header_digest, release_digest
        return real_release_check(**kwargs)

    monkeypatch.setattr(handoff, "_validate_release_facts", release_check)
    monkeypatch.setattr(handoff, "_project_live_pool_rows", lambda **kwargs: [query])
    kwargs = dict(release_id="release-a", cohort_file=root / "cohort.json", milestone="M1",
                  producer_baseline_revision=revision, repo_root=tmp_path,
                  output_root=output, publish_root=publish, release_root=releases)
    document, path, replayed = handoff.write_producer_release_handoff(**kwargs)
    assert_valid(document, "release", "producer_release_handoff")
    assert document["repositoryId"] == "content-a"
    assert not {"contentRevision", "layoutVersion", "objectPaths"} & document.keys()
    original = path.read_bytes()
    assert not replayed
    assert handoff.write_producer_release_handoff(**kwargs)[2] is True
    handoff.validate_producer_release_handoff(document, repo_root=tmp_path, output_root=output, release_root=releases, expected_repository_id="content-a")
    with pytest.raises(handoff.ProducerReleaseHandoffError, match="REPOSITORY_IDENTITY_MISMATCH"):
        handoff.validate_producer_release_handoff(document, repo_root=tmp_path, output_root=output, release_root=releases, expected_repository_id="content-b")
    other = tmp_path / "another-publish"
    _repository(other, "content-b")
    with pytest.raises(
        handoff.ProducerReleaseHandoffError, match="CREATE_ONCE_CONFLICT",
    ) as cross_repository:
        handoff.write_producer_release_handoff(**{**kwargs, "publish_root": other})
    assert "REPOSITORY_IDENTITY_MISMATCH" in str(cross_repository.value.__cause__)
    assert path.read_bytes() == original
    import argparse
    from content.release.canonical.handler_cli import register_parser
    parser = argparse.ArgumentParser()
    register_parser(parser.add_subparsers(dest="command", required=True))
    args = parser.parse_args(["release", "handoff-verify", "--release-id", "release-a", "--release-root", str(releases), "--expected-repository-id", "content-a"])
    args.handler(args)
    result = json.loads(capsys.readouterr().out)
    assert result["passed"] and result["repositoryId"] == "content-a"
    args.expected_repository_id = "content-b"
    with pytest.raises(SystemExit, match="REPOSITORY_IDENTITY_MISMATCH"):
        args.handler(args)
    (publish / "repository.json").unlink()
    assert handoff.read_producer_release_handoff(path, repo_root=tmp_path, output_root=output, release_root=releases, expected_repository_id="content-a")["repositoryId"] == "content-a"
    # 新 reader 不兼容补缺身份，不改历史原件以使旧 handoff 被接纳。
    without_identity = {key: value for key, value in document.items() if key != "repositoryId"}
    with pytest.raises(handoff.ProducerReleaseHandoffError, match="SCHEMA_INVALID"):
        handoff.validate_producer_release_handoff(without_identity, repo_root=tmp_path, output_root=output, release_root=releases)
