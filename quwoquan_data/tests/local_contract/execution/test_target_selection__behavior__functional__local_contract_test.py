"""Canonical execution target-selection contracts."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from content.execution.selection import build_multimodal_spec, select_targets, write_selected_task


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
EXECUTION_ID = "20260711--travel-homepage-coverage--cn-zhejiang--canary-001"


def _coverage_file(path: Path) -> Path:
    path.write_text(
        yaml.safe_dump(
            {
                "districts": [
                    {
                        "district": "普陀区",
                        "leaves": [
                            {
                                "name": "普陀山",
                                "canonicalName": "普陀山",
                                "entityType": "地点/景区",
                                "geoTagRef": "Topic/地理/行政区/中国/浙江省/舟山市/普陀区",
                                "typeTagRefs": ["Entity/地点/景区/5A景区"],
                                "selectionPriority": 1,
                            }
                        ],
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def _spec() -> dict:
    return build_multimodal_spec(
        execution_id=EXECUTION_ID,
        name="浙江省实体主页金丝雀",
        title="浙江省实体主页金丝雀",
        region="中国/浙江省",
        category="景区",
        targets=[
            {
                "name": "普陀山",
                "entityType": "地点/景区",
                "geoTagRef": "Topic/地理/行政区/中国/浙江省/舟山市/普陀区",
                "typeTagRefs": ["Entity/地点/景区/5A景区"],
            }
        ],
        created_by="test",
        intent_label="zhejiang-homepage-canary",
        entity_articles_per_target=0,
        entity_homepages_per_target=1,
        image_works_per_target=0,
        target_entity_count=1,
    )


def test_select_targets_uses_static_coverage_identity_only(tmp_path: Path):
    targets, report = select_targets(
        discovery_path=_coverage_file(tmp_path / "舟山市.yaml"),
        limit=1,
        mandatory=["普陀山"],
        excluded=set(),
    )
    assert [item["name"] for item in targets] == ["普陀山"]
    assert targets[0]["geoTagRef"].endswith("/普陀区")
    assert {"name", "entityType", "geoTagRef", "typeTagRefs", "region", "sourceName"}.issubset(targets[0])
    assert all("readiness" not in key.lower() and "primarysource" not in key.lower() for key in targets[0])
    assert report["selectedCount"] == 1


def test_execution_spec_has_one_identity_and_readable_intent():
    spec = _spec()
    assert spec["schemaVersion"] == "quwoquan.content.execution_spec"
    assert spec["executionId"] == EXECUTION_ID
    assert spec["intentLabel"] == "zhejiang-homepage-canary"
    assert "taskId" not in spec
    assert "batchId" not in spec


def test_execution_spec_derives_entity_types_from_selected_targets():
    spec = build_multimodal_spec(
        execution_id="20260712--travel-homepage-coverage--cn-zhejiang--m1-001",
        name="浙江省实体主页M1百级放量",
        title="浙江省实体主页M1百级放量",
        region="中国/浙江省",
        category="景区",
        targets=[
            {"name": "普陀山", "entityType": "地点/景区"},
            {"name": "良渚博物院", "entityType": "地点/博物馆"},
            {"name": "前童古镇", "entityType": "地点/古镇"},
        ],
        created_by="test",
        entity_articles_per_target=0,
        entity_homepages_per_target=1,
        image_works_per_target=0,
        target_entity_count=3,
    )

    assert spec["scope"]["entityTypes"] == [
        "地点/博物馆",
        "地点/古镇",
        "地点/景区",
    ]


def test_execution_spec_supports_strict_full_delivery():
    spec = build_multimodal_spec(
        execution_id="20260712--travel-homepage-coverage--cn-zhejiang--m1-002",
        name="浙江省实体主页M1严格放量",
        title="浙江省实体主页M1严格放量",
        region="中国/浙江省",
        category="景区",
        targets=[{"name": "普陀山", "entityType": "地点/景区"}],
        created_by="test",
        entity_articles_per_target=0,
        entity_homepages_per_target=1,
        image_works_per_target=0,
        target_entity_count=1,
    )

    assert spec["workflowPolicy"]["selectionPolicy"] == "frozen"
    assert spec["workflowPolicy"]["targetEntityCount"] == 1
    assert spec["workflowPolicy"]["targetObjectCount"] == 1
    assert not {
        "allowPartialContent",
        "allowQuotaShortfall",
        "deliveryMode",
        "minCompletionMode",
        "replacementPolicy",
    } & set(spec["workflowPolicy"])


def test_write_selected_execution_creates_only_canonical_plan_and_shared_evidence():
    spec = _spec()
    path = write_selected_task(
        spec,
        {
            "executionId": EXECUTION_ID,
            "selectedCount": 1,
            "discoveryPath": str(DATA_ROOT / "verticals/travel/coverage/中国/浙江省"),
        },
        force=True,
    )
    root = path.parent.parent
    assert path == root / "0.plan" / "execution_spec.yaml"
    assert (root / "_shared/execution_progress.json").is_file()
    assert (root / "_shared/target_selection.json").is_file()
    assert (root / "_shared/catalog.ndjson").is_file()
    assert (root / "0.plan/target_set.json").is_file()
    assert all(
        (root / "entities/地点/景区/普陀山" / stage).is_dir()
        for stage in ("1.download", "2.quality", "3.compose", "4.draft", "5.review")
    )

    for artifact in root.rglob("*"):
        if not artifact.is_file() or artifact.suffix not in {".json", ".yaml", ".ndjson"}:
            continue
        text = artifact.read_text(encoding="utf-8")
        assert "taskId" not in text, artifact
        assert "batchId" not in text, artifact

    progress = json.loads((root / "_shared/execution_progress.json").read_text(encoding="utf-8"))
    assert progress["schemaVersion"] == "quwoquan.content.execution_progress"
    assert progress["executionId"] == EXECUTION_ID


def test_execution_spec_requires_readable_execution_id():
    try:
        build_multimodal_spec(
            execution_id="old-task-id",
            name="bad",
            title="bad",
            region="中国/浙江省",
            category="景区",
            targets=[],
            created_by="test",
        )
    except ValueError as exc:
        assert "executionId" in str(exc)
    else:
        raise AssertionError("retired task identity must be rejected")
