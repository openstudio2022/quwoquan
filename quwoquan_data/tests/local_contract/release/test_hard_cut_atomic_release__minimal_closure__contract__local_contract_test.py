# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020.t6
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020.t7
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020.t9
from __future__ import annotations

import json
from pathlib import Path

import pytest

from content.release.canonical.publish_object import _target_object
from core.schema import assert_valid
from core.stage_artifact_contract import required_stage_artifacts
from verify import stage_artifacts

EXECUTION_ID = "20260903--travel-video-hard-cut--test-region-a--pilot-001"


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _target_set(refs: list[str]) -> dict[str, object]:
    return {
        "schema": "quwoquan_data.target_set",
        "executionId": EXECUTION_ID,
        "carrier": "video",
        "selectionPolicy": "frozen",
        "entityCatalogDigest": "sha256:" + "a" * 64,
        "candidateBinding": {
            "scope": "output", "ref": "data/local/candidates.json",
            "digest": "sha256:" + "b" * 64, "candidateCount": len(refs),
        },
        "targetCount": len(refs),
        "targetRefs": refs,
        "targets": [
            {
                "name": f"target-{index}", "entityType": "地点/景区",
                "publishAngle": "angle", "publishTitle": "title",
                "publishSeq": index + 1,
            }
            for index, _ in enumerate(refs)
        ],
    }


def test_stage_contract_uses_ai_written_target_artifacts() -> None:
    assert required_stage_artifacts("video")["4.draft"] == ("video_script.json",)
    assert required_stage_artifacts("image")["4.draft"] == ("image_work.json",)
    assert required_stage_artifacts("article")["5.review"] == ("content_review.json",)


def test_stage_verifier_schema_map_matches_minimal_stage_contract() -> None:
    retired = {
        "4.draft/author_job_packet.json",
        "4.draft/prompt_snapshot.json",
        "5.review/deterministic_gate.json",
        "5.review/finalization_report.json",
        "5.review/evidence_index.json",
    }
    assert retired.isdisjoint(stage_artifacts._SCHEMA_FILES)


def test_content_review_schema_rejects_old_review_mirrors() -> None:
    document = {
        "schema": "quwoquan_data.content_review",
        "stage": "5.review",
        "executionId": EXECUTION_ID,
        "objectRef": "posts/video/angle/title/1",
        "decision": "approved",
        "draft": {"ref": "4.draft/video_script.json", "digest": "sha256:" + "d" * 64},
        "dimensions": [{"name": "content", "decision": "approved", "issues": []}],
        "blockingIssues": [],
        "assetRights": [],
    }
    assert_valid(document, "content", "content_review")
    for old_field in ("actor", "score", "repair", "verdict", "mediaRefReview"):
        with pytest.raises(ValueError):
            assert_valid({**document, old_field: {}}, "content", "content_review")



def test_writing_pack_schema_declares_host_ai_producer() -> None:
    from core.schema import load_schema

    description = load_schema("content", "writing_pack")["description"]
    assert "宿主 AI" in description
    assert "CLI prepare" not in description


def test_content_review_is_the_only_review_stage_artifact() -> None:
    schema_files = set(stage_artifacts._SCHEMA_FILES)
    assert "5.review/content_review.json" in schema_files
    for retired in (
        "5.review/rubric_review.json", "5.review/reviewer_result.json",
        "5.review/media_ref_review.json", "5.review/attestation.json",
    ):
        assert retired not in schema_files



def test_stage_gate_fails_when_declared_target_directory_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / EXECUTION_ID
    _write(root / "0.plan/target_set.json", _target_set(["posts/video/angle/title/1"]))
    monkeypatch.setattr(stage_artifacts, "execution_root", lambda _execution_id: root)
    report = stage_artifacts.verify_stage_artifacts(
        execution_id=EXECUTION_ID,
        publish_root=tmp_path / "publish",
        release_root=tmp_path / "release",
        commercial=False,
        through="1.download",
    )
    assert not report["passed"]
    assert report["objectCount"] == 1
    assert any("declared target object directory missing" in issue for issue in report["issues"])


def test_release_cohort_schema_requires_exact_four_carrier_counts() -> None:
    cohort = {
        "schema": "quwoquan_data.release_cohort",
        "releaseClass": "research",
        "milestone": "M1",
        "producerBaselineRevision": "a" * 40,
        "objectRefs": ["entities/地点/景区/西湖", "posts/article/攻略/西湖/1"],
        "expectedCarrierCounts": {"homepage": 1, "article": 1, "image": 0, "video": 0},
    }
    assert_valid(cohort, "release", "release_cohort")
    cohort["expectedCarrierCounts"].pop("video")
    with pytest.raises(ValueError, match="video"):
        assert_valid(cohort, "release", "release_cohort")



def test_publish_object_rejects_target_outside_target_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / EXECUTION_ID
    _write(root / "0.plan/target_set.json", _target_set(["posts/video/angle/title/1"]))
    monkeypatch.setattr("content.release.canonical.publish_object.execution_root", lambda _execution_id: root)
    with pytest.raises(Exception, match="not declared"):
        _target_object(EXECUTION_ID, "posts/video/angle/other/1")


def test_pool_build_cli_requires_cohort_file() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "quwoquan_data/scripts/cli.py", "release", "pool-build", "--help"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert "--cohort-file" in result.stdout
    assert "--all-publishable" not in result.stdout
    assert "--milestone" not in result.stdout


def test_publish_object_cli_is_single_target_only() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "quwoquan_data/scripts/cli.py", "release", "publish-object", "--help"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert "--execution-id" in result.stdout
    assert "--target-ref" in result.stdout
    assert "publish-execution" not in result.stdout
