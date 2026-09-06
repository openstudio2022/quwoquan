"""Tag consumer verification consumes the stage-only `verified` import report.

# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-035
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from content.release.environment.tag_consumer_verification import (
    write_tag_consumer_verification,
)
from content.release.model import ReleaseKind

RELEASE_ID = "release-tag-consumer-a"
ENVIRONMENT = "alpha"
MANIFEST_DIGEST = "sha256:" + "1" * 64
TAG_REFS = ["Topic/旅行", "Entity/地点/景区", "Format/内容载体/文章/游记"]


def _tag_import_report(**overrides: object) -> dict[str, object]:
    report: dict[str, object] = {
        "schema": "quwoquan.tag_import_report",
        "status": "verified",
        "environment": ENVIRONMENT,
        "releaseId": RELEASE_ID,
        "sourceOwner": "qwq_data",
        "manifestDigest": MANIFEST_DIGEST,
        "activationMode": "stage-only",
        "canonicalDigest": "2" * 64,
        "releaseKind": "content",
        "nodeCount": len(TAG_REFS),
        "tagRefs": sorted(TAG_REFS),
        "generatedAt": "2026-09-06T16:03:49.916782Z",
    }
    report.update(overrides)
    return report


def _write(tmp_path: Path, report: dict[str, object]) -> Path:
    path = tmp_path / "apply" / "tag-import.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    return path


def _verify(tmp_path: Path, report_path: Path, *, desired_tags: list[str]) -> Path:
    return write_tag_consumer_verification(
        output_root=tmp_path,
        environment=ENVIRONMENT,
        release_id=RELEASE_ID,
        release_kind=ReleaseKind.CONTENT,
        run_id="verify-001",
        release_contract={"desiredRefs": {"tags": desired_tags}},
        import_report_path=report_path,
        output_path=tmp_path / "verify" / "tag-consumer-verification.json",
    )


def test_stage_only_verified_report_matching_desired_refs_passes(tmp_path: Path) -> None:
    report_path = _write(tmp_path, _tag_import_report())

    output = _verify(tmp_path, report_path, desired_tags=list(reversed(TAG_REFS)))

    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["schema"] == "quwoquan_data.tag_consumer_verification"
    assert document["passed"] is True
    assert document["nodeCount"] == len(TAG_REFS)
    assert document["tagRefs"] == sorted(TAG_REFS)
    assert document["sourceImportReportRef"] == "apply/tag-import.json"


def test_dry_run_report_is_not_consumer_proof(tmp_path: Path) -> None:
    report_path = _write(tmp_path, _tag_import_report(status="dry-run"))

    with pytest.raises(ValueError, match="differs from immutable release authority"):
        _verify(tmp_path, report_path, desired_tags=TAG_REFS)


def test_legacy_active_status_is_rejected_by_schema(tmp_path: Path) -> None:
    report_path = _write(tmp_path, _tag_import_report(status="active"))

    with pytest.raises(ValueError, match=r"'active' 不在枚举"):
        _verify(tmp_path, report_path, desired_tags=TAG_REFS)


def test_tag_refs_or_node_count_drift_fails_closed(tmp_path: Path) -> None:
    drifted_refs = _write(tmp_path / "refs", _tag_import_report())
    with pytest.raises(ValueError, match="differs from immutable release authority"):
        _verify(tmp_path / "refs", drifted_refs, desired_tags=TAG_REFS[:-1])

    drifted_count = _write(
        tmp_path / "count", _tag_import_report(nodeCount=len(TAG_REFS) + 1)
    )
    with pytest.raises(ValueError, match="differs from immutable release authority"):
        _verify(tmp_path / "count", drifted_count, desired_tags=TAG_REFS)


def test_release_id_or_environment_drift_fails_closed(tmp_path: Path) -> None:
    other_release = _write(tmp_path / "release", _tag_import_report(releaseId="release-other"))
    with pytest.raises(RuntimeError, match="releaseId 不一致"):
        _verify(tmp_path / "release", other_release, desired_tags=TAG_REFS)

    other_environment = _write(tmp_path / "env", _tag_import_report(environment="beta"))
    with pytest.raises(ValueError, match="differs from immutable release authority"):
        _verify(tmp_path / "env", other_environment, desired_tags=TAG_REFS)
