"""Execution-owned source qualification never mutates static coverage inputs."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.execution import qualification  # noqa: E402


EXECUTION_ID = "20260713--travel-homepage-coverage--test-region-a--pilot-901"


def _spec() -> dict:
    return {
        "scope": {
            "coverageTargets": [
                {
                    "name": "测试实体甲",
                    "entityType": "地点/景区",
                    "geoTagRef": "Topic/地理/行政区/中国/test-region-a/舟山市/普陀区",
                    "aliases": ["测试实体甲风景名胜区"],
                }
            ]
        }
    }


def _install_execution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / EXECUTION_ID
    root.mkdir(parents=True)
    monkeypatch.setattr(qualification, "execution_root", lambda _execution_id: root)
    monkeypatch.setattr(qualification.store, "load_spec", lambda _execution_id: _spec())
    return root


def _write_source_catalog(root: Path, *, source_kind: str = "wikipedia") -> None:
    object_root = root / "entities" / "地点" / "景区" / "测试实体甲"
    evidence_ref = "evidence/sources/测试实体甲__wikipedia__abc/meta.json"
    evidence = object_root / evidence_ref
    evidence.parent.mkdir(parents=True)
    evidence.write_text("{}\n", encoding="utf-8")
    catalog = {
        "schema": "quwoquan_data.object_source_catalog",
        "policyRevision": "encyclopedia-primary",
        "primaryEvidenceRef": evidence_ref,
        "primarySource": {
            "sourceUnitId": "测试实体甲__wikipedia__abc",
            "entityName": "测试实体甲",
            "sourceKind": source_kind,
            "extractor": "wikipedia_api" if source_kind == "wikipedia" else "generic_html",
            "canonicalUrl": "https://zh.wikipedia.org/wiki/%E6%99%AE%E9%99%80%E5%B1%B1",
            "sourceUrl": "https://zh.wikipedia.org/wiki/%E6%99%AE%E9%99%80%E5%B1%B1",
            "title": "测试实体甲",
            "fetchedAt": "2026-07-13T00:00:00Z",
            "snapshotHash": "sha256:" + "a" * 64,
            "policyRevision": "encyclopedia-primary",
            "sourceUseMode": "licensed_adaptation",
            "evidenceRef": evidence_ref,
        },
        "sources": [],
    }
    catalog_path = object_root / "evidence" / "source_catalog.json"
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")


def test_request_contains_only_static_target_identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = _install_execution(monkeypatch, tmp_path)

    path = qualification.prepare_execution_qualification(EXECUTION_ID)

    assert path == root / "sources" / "qualification" / "request.json"
    request = json.loads(path.read_text(encoding="utf-8"))
    target = request["targets"][0]
    assert target == {
        "name": "测试实体甲",
        "entityType": "地点/景区",
        "geoTagRef": "Topic/地理/行政区/中国/test-region-a/舟山市/普陀区",
        "aliases": ["测试实体甲风景名胜区"],
    }


def test_catalog_with_runtime_evidence_confirms_target(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = _install_execution(monkeypatch, tmp_path)
    qualification.prepare_execution_qualification(EXECUTION_ID)
    _write_source_catalog(root)

    result = qualification.finalize_execution_qualification(
        EXECUTION_ID, publishable_names={"测试实体甲"}
    )

    assert result.passed
    payload = json.loads(result.path.read_text(encoding="utf-8"))
    assert payload["targets"][0]["status"] == "confirmed"
    assert payload["issues"] == []


def test_unqualified_catalog_blocks_target_with_typed_issue(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = _install_execution(monkeypatch, tmp_path)
    qualification.prepare_execution_qualification(EXECUTION_ID)
    _write_source_catalog(root, source_kind="untrusted")

    result = qualification.finalize_execution_qualification(
        EXECUTION_ID, publishable_names={"测试实体甲"}
    )

    assert not result.passed
    assert result.issues[0].code.value == "DATA.SOURCE.PRIMARY_AUTHORITY_MISSING"
    payload = json.loads(result.path.read_text(encoding="utf-8"))
    assert payload["targets"][0]["status"] == "blocked"
    assert payload["issues"][0]["stage"] == "source_gate"


def _install_oversampled_execution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """候选池含两个实体，只有测试实体甲拿到来源目录。"""
    spec = _spec()
    spec["scope"]["coverageTargets"].append(
        {
            "name": "测试实体乙",
            "entityType": "地点/景区",
            "geoTagRef": "Topic/地理/行政区/中国/test-region-a/舟山市/定海区",
            "aliases": [],
        }
    )
    root = tmp_path / EXECUTION_ID
    root.mkdir(parents=True)
    monkeypatch.setattr(qualification, "execution_root", lambda _execution_id: root)
    monkeypatch.setattr(qualification.store, "load_spec", lambda _execution_id: spec)
    return root


def test_discarded_candidate_source_gap_does_not_block_publish(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """过采丢弃对象缺来源属于预期事实：留档但不阻断准出集合发布。"""
    root = _install_oversampled_execution(monkeypatch, tmp_path)
    qualification.prepare_execution_qualification(EXECUTION_ID)
    _write_source_catalog(root)

    result = qualification.finalize_execution_qualification(
        EXECUTION_ID, publishable_names={"测试实体甲"}
    )

    assert result.passed
    assert result.issues == ()
    payload = json.loads(result.path.read_text(encoding="utf-8"))
    statuses = {row["name"]: row["status"] for row in payload["targets"]}
    assert statuses == {"测试实体甲": "confirmed", "测试实体乙": "blocked"}
    assert [issue["ref"] for issue in payload["issues"]] == ["测试实体乙"], (
        "丢弃对象的来源缺口必须留在报告里供审计，只是不参与准出判定"
    )


def test_publishable_object_source_gap_still_blocks_publish(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _install_oversampled_execution(monkeypatch, tmp_path)
    qualification.prepare_execution_qualification(EXECUTION_ID)
    _write_source_catalog(root)

    result = qualification.finalize_execution_qualification(
        EXECUTION_ID, publishable_names={"测试实体甲", "测试实体乙"}
    )

    assert not result.passed
    assert [issue.ref for issue in result.issues] == ["测试实体乙"]


def test_empty_publish_set_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """空准出集合不得静默通过，否则 publish 会发布出零对象的 release。"""
    root = _install_execution(monkeypatch, tmp_path)
    qualification.prepare_execution_qualification(EXECUTION_ID)
    _write_source_catalog(root)

    with pytest.raises(ValueError, match="at least one publishable object"):
        qualification.finalize_execution_qualification(EXECUTION_ID, publishable_names=set())


def test_publish_set_outside_frozen_targets_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _install_execution(monkeypatch, tmp_path)
    qualification.prepare_execution_qualification(EXECUTION_ID)
    _write_source_catalog(root)

    with pytest.raises(ValueError, match="outside the immutable execution targets"):
        qualification.finalize_execution_qualification(
            EXECUTION_ID, publishable_names={"测试实体丙"}
        )
