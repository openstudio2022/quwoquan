"""Rejected source units must leave the consumable source reference set."""
from __future__ import annotations

import sys
import shutil
from pathlib import Path


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.source.handler_images import _move_rejected_source_unit  # noqa: E402
from content.source.source_unit import resolve_entity_object_dir, write_source_unit  # noqa: E402
from core.paths import execution_root  # noqa: E402
from core.io import read_json, write_json  # noqa: E402


def test_rejected_source_unit_removes_consumable_object_ref(tmp_path: Path) -> None:
    object_dir = tmp_path / "entities" / "地点" / "景区" / "测试景区"
    unit_dir = tmp_path / "sources" / "source-unit-1"
    unit_dir.mkdir(parents=True)
    (unit_dir / "source.md").write_text("不合格来源", encoding="utf-8")
    write_json(
        unit_dir / "meta.json",
        {
            "sourceUnitId": "source-unit-1",
            "sourceRef": "sources/source-unit-1/source.md",
        },
    )
    write_json(
        object_dir / "1.download" / "source_refs.json",
        {
            "schema": "quwoquan_data.object_source_refs",
            "objectRef": "entities/地点/景区/测试景区",
            "sources": [
                {
                    "sourceUnitId": "source-unit-1",
                    "sourceRef": "sources/source-unit-1/source.md",
                    "metaRef": "sources/source-unit-1/meta.json",
                }
            ],
        },
    )

    rejected = _move_rejected_source_unit(
        object_dir,
        unit_dir,
        quality={"quality": "Reject", "score": 0, "reasons": ["thin_source"]},
    )

    assert rejected == object_dir / "1.download" / "rejected_sources" / "source-unit-1"
    assert read_json(object_dir / "1.download" / "source_refs.json")["sources"] == []
    assert read_json(rejected / "meta.json")["rejection"]["decision"] == "reject"


def test_source_unit_without_images_keeps_empty_asset_index() -> None:
    execution_id = "20260715--travel-homepage-empty-asset-index--cn-zhejiang--canary-001"
    root = execution_root(execution_id)
    shutil.rmtree(root, ignore_errors=True)
    try:
        object_dir = resolve_entity_object_dir(
            execution_id,
            "无图来源景区",
            etype_hint="地点/景区",
        )
        write_source_unit(
            object_dir,
            ordinal=1,
            source_id="text_only",
            source_md="只有文本的已接纳来源。",
            clean_md="只有文本的已接纳来源。",
            execution_id=execution_id,
        )

        index_paths = list((root / "sources").glob("*/assets/index.json"))
        assert len(index_paths) == 1
        assert read_json(index_paths[0]) == {"assets": []}
    finally:
        shutil.rmtree(root, ignore_errors=True)
