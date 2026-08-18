"""Pool Research Release may close author-only Tags from control-plane truth."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.canonical.aggregate_release_closure import (
    copy_release_tag_snapshot,
    creator_tag_refs,
    reference_closure,
    resolve_tag_snapshot,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
)
from core.release_layout import objects_merkle, payload_file


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _tag_definition(root: Path, ref: str, *, source: str) -> Path:
    target = root / ref / "_definition.json"
    _write_json(
        target,
        {
            "schema": "quwoquan_data.tag_definition",
            "ref": ref,
            "source": source,
        },
    )
    return target


def test_resolve_tag_snapshot__publish_snapshot_has_priority__local_contract(
    tmp_path: Path,
) -> None:
    publish_root = tmp_path / "publish"
    control_root = tmp_path / "control_plane/taxonomy"
    tag_ref = "Topic/旅行/玩法/观光游览"
    publish_definition = _tag_definition(
        publish_root / "tags", tag_ref, source="publish"
    )
    _tag_definition(control_root, tag_ref, source="control-plane")

    resolved = resolve_tag_snapshot(
        publish_root,
        tag_ref=tag_ref,
        control_plane_taxonomy_root=control_root,
    )

    assert resolved == publish_definition.parent


def test_creator_tag_refs__ten_authors_close_sixteen_control_plane_tags(
    tmp_path: Path,
) -> None:
    publish_root = tmp_path / "publish"
    control_root = tmp_path / "control_plane/taxonomy"
    tag_refs = [f"Topic/测试/作者标签/{index:02d}" for index in range(16)]
    creator_refs = [f"qwq_creator_test_{index:03d}" for index in range(10)]
    for index, creator_ref in enumerate(creator_refs):
        assigned = tag_refs[index : index + 1]
        if index == len(creator_refs) - 1:
            assigned = tag_refs[index:]
        _write_json(
            publish_root / "creators" / creator_ref / "_creator.json",
            {"creatorId": creator_ref, "tagRefs": assigned},
        )
    for tag_ref in tag_refs:
        _tag_definition(control_root, tag_ref, source="control-plane")

    resolved = creator_tag_refs(
        publish_root,
        creator_refs=creator_refs,
        control_plane_taxonomy_root=control_root,
    )

    assert resolved == tag_refs
    assert not (publish_root / "tags").exists()


def test_reference_closure__ordinary_release_does_not_use_control_plane_fallback(
    tmp_path: Path,
) -> None:
    publish_root = tmp_path / "publish"
    control_root = tmp_path / "control_plane/taxonomy"
    entity_ref = "地点/景区/测试实体"
    creator_ref = "qwq_creator_test_001"
    tag_ref = "Topic/测试/仅控制面"
    entity_root = publish_root / "entities" / entity_ref
    _write_json(entity_root / "manifest.json", {"entityId": entity_ref})
    _write_json(entity_root / "creator.refs.json", {"creatorRefs": [creator_ref]})
    _write_json(entity_root / "tag.refs.json", {"tagRefs": [tag_ref]})
    _write_json(
        publish_root / "creators" / creator_ref / "_creator.json",
        {"creatorId": creator_ref, "tagRefs": []},
    )
    _tag_definition(control_root, tag_ref, source="control-plane")

    with pytest.raises(
        ObjectTransactionError,
        match=r"DATA\.RELEASE\.TAG_SNAPSHOT_MISSING",
    ):
        reference_closure(
            publish_root,
            entity_refs={entity_ref},
            post_refs=set(),
        )

    assert reference_closure(
        publish_root,
        entity_refs={entity_ref},
        post_refs=set(),
        control_plane_taxonomy_root=control_root,
    ) == ([creator_ref], [tag_ref])


def test_copy_release_tag_snapshot__fallback_is_exact_and_in_merkle(
    tmp_path: Path,
) -> None:
    publish_root = tmp_path / "publish"
    control_root = tmp_path / "control_plane/taxonomy"
    release_root = tmp_path / "release"
    tag_ref = "Format/内容角度/攻略/新生攻略"
    source_definition = _tag_definition(control_root, tag_ref, source="control-plane")
    _tag_definition(
        control_root,
        f"{tag_ref}/不应复制的子标签",
        source="control-plane-child",
    )
    target = payload_file(release_root, f"objects/tags/{tag_ref}")

    copy_release_tag_snapshot(
        publish_root,
        tag_ref=tag_ref,
        target=target,
        control_plane_taxonomy_root=control_root,
    )
    first_merkle = objects_merkle(release_root)
    source_definition.write_text('{"changed":true}\n', encoding="utf-8")

    assert (target / "_definition.json").is_file()
    assert not (target / "不应复制的子标签").exists()
    assert objects_merkle(release_root) == first_merkle


def test_resolve_tag_snapshot__missing_control_plane_definition_is_typed_block(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ObjectTransactionError,
        match=(
            r"DATA\.RELEASE\.TAG_SNAPSHOT_MISSING: "
            r"Topic/测试/不存在"
        ),
    ):
        resolve_tag_snapshot(
            tmp_path / "publish",
            tag_ref="Topic/测试/不存在",
            control_plane_taxonomy_root=tmp_path / "control_plane/taxonomy",
        )
