from __future__ import annotations

import json
from pathlib import Path

from content.release.canonical.object_transaction_audit import validate_publish_invariants
from content.release.canonical.object_transaction_contract import refresh_canonical_tag_snapshots


TAG_REF = "Topic/旅行"


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _definition(label: str) -> dict[str, str]:
    return {
        "label": label,
        "labelEn": "travel",
        "createdAt": "2026-07-15T00:00:00Z",
        "updatedAt": "2026-07-15T00:00:00Z",
    }


def test_tag_snapshot_closure__publish_release__contract__local_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    taxonomy = tmp_path / "taxonomy"
    canonical = tmp_path / "publish"
    _write(taxonomy / TAG_REF / "_definition.json", _definition("旅行"))
    _write(canonical / "entities/地点/景区/甲/tag.refs.json", {"tagRefs": [TAG_REF]})
    monkeypatch.setenv("QWQ_TAGS_ROOT", str(taxonomy))

    assert refresh_canonical_tag_snapshots(canonical) == [TAG_REF]
    assert validate_publish_invariants(canonical)["status"] == "passed"

    _write(canonical / "tags/Topic/孤儿/_definition.json", _definition("孤儿"))
    assert any(
        issue["code"] == "orphan_tag_snapshot"
        for issue in validate_publish_invariants(canonical)["issues"]
    )

    assert refresh_canonical_tag_snapshots(canonical) == [TAG_REF]
    assert not (canonical / "tags/Topic/孤儿").exists()
    assert validate_publish_invariants(canonical)["status"] == "passed"


def test_tag_snapshot_closure_rejects_unmaterialized_consumer_ref(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "publish"
    _write(canonical / "entities/地点/景区/甲/tag.refs.json", {"tagRefs": [TAG_REF]})

    report = validate_publish_invariants(canonical)

    assert report["status"] == "failed"
    assert {issue["code"] for issue in report["issues"]} == {"dangling_tag_ref"}


def test_entity_creator_profile_must_belong_to_creator_reference_closure(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "publish"
    entity = canonical / "entities/地点/景区/甲"
    _write(entity / "_entity.json", {"creatorProfileId": "creator_a"})
    _write(entity / "creator.refs.json", {"creatorRefs": []})
    _write(
        canonical / "creators/creator_a/_creator.json",
        {"creatorId": "creator_a"},
    )

    report = validate_publish_invariants(canonical)

    assert report["status"] == "failed"
    assert any(
        issue["code"] == "entity_creator_closure_missing"
        for issue in report["issues"]
    )

    _write(entity / "creator.refs.json", {"creatorRefs": ["creator_a"]})
    assert validate_publish_invariants(canonical)["status"] == "passed"
