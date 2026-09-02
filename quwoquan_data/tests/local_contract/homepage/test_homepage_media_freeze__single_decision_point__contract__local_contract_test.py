"""homepage 逐图处置只在 `1.download` 成型一次（DEC-029）。

历史失败形态：同一张图的版面归属被算了三次——`homepage_prepare` 一次、
`homepage_release` 一次，`place_homepage_assets_in_markdown` 还会依据 Agent 成稿正文
把 `related` 提升回 `inline`。三处输入不同步时，下发给创作方的占位符与最终落盘版面
就会分叉，而分叉恰恰发生在「兑现对账」之后，没有任何判据拦得住。

本用例把冻结点钉死：处置文档 create-once，重跑写不同结论必须失败；渲染函数只按冻结
role 落版面，不再读正文反推；冻结说要内嵌而成稿没带回锚点时 fail closed，交给 repair
通道补，而不是静默降级成相关图片。
"""

from pathlib import Path

import pytest

from content.homepage.homepage_assets import write_homepage_media_dispositions
from content.homepage import homepage_media_freeze
from content.homepage.homepage_media_freeze import (
    frozen_disposition_by_source_asset,
    publish_disposition,
)
from content.homepage.homepage_media_freeze_cli import _frozen_execution_plan
from core.asset_placement import place_homepage_assets_in_markdown
from core.io import read_json, write_json
from core.page_media import HomepageAssetDisposition, HomepageMediaDisposition

_OBJECT_REF = "地点/景区/测试实体甲"
_EXECUTION_ID = "20260713--travel-homepage-coverage--test-region-a--pilot-001"


def _record(
    ref: str,
    disposition: HomepageAssetDisposition,
    asset_id: str = "",
) -> HomepageMediaDisposition:
    return HomepageMediaDisposition(
        source_asset_ref=f"sources/测试实体甲__wikipedia__fixture/assets/{ref}",
        source_asset_id="001_001",
        asset_id=asset_id,
        disposition=disposition,
        reason="published" if asset_id else "duplicate_visual_subject",
    )


def _freeze(entity_dir: Path, records: list[HomepageMediaDisposition]) -> dict:
    return write_homepage_media_dispositions(
        entity_dir=entity_dir,
        execution_id=_EXECUTION_ID,
        object_ref=_OBJECT_REF,
        records=records,
    )


def test_disposition_is_decided_without_reading_any_draft_body() -> None:
    """决策输入只有来源页事实：位置、章节锚点、原图注。"""

    inline = {
        "placementType": "inline",
        "sectionAnchor": "历史沿革",
        "caption": "测试实体甲的清代山门",
        "fileName": "gate.jpg",
    }

    assert publish_disposition(0, inline) is HomepageAssetDisposition.COVER
    assert publish_disposition(1, inline) is HomepageAssetDisposition.INLINE


@pytest.mark.parametrize(
    "image",
    [
        pytest.param(
            {"placementType": "groupMember", "sectionAnchor": "概况", "caption": "山门"},
            id="not_anchored_in_body_by_the_source_page",
        ),
        pytest.param(
            {"placementType": "inline", "sectionAnchor": "", "caption": "山门"},
            id="no_reliable_section_anchor",
        ),
        pytest.param(
            {
                "placementType": "inline",
                "sectionAnchor": "概况",
                "caption": "gate.jpg",
                "fileName": "gate.jpg",
            },
            id="degraded_caption_would_need_a_fabricated_one",
        ),
    ],
)
def test_an_image_without_a_full_inline_warrant_goes_to_related(image: dict) -> None:
    assert publish_disposition(1, image) is HomepageAssetDisposition.RELATED


def test_the_frozen_document_is_create_once(tmp_path: Path) -> None:
    entity_dir = tmp_path / "entities" / "地点" / "景区" / "测试实体甲"
    records = [_record("hero.jpg", HomepageAssetDisposition.COVER, "jia_cover")]

    first = _freeze(entity_dir, records)
    _freeze(entity_dir, records)

    assert read_json(entity_dir / "evidence" / "media_dispositions.json") == first


def test_a_second_decision_point_cannot_overwrite_the_frozen_one(tmp_path: Path) -> None:
    """重跑写出不同结论是「有第二个决策点」的信号，必须当场失败。"""

    entity_dir = tmp_path / "entities" / "地点" / "景区" / "测试实体甲"
    _freeze(entity_dir, [_record("hero.jpg", HomepageAssetDisposition.COVER, "jia_cover")])

    with pytest.raises(ValueError, match="already frozen"):
        _freeze(
            entity_dir,
            [_record("hero.jpg", HomepageAssetDisposition.RELATED, "jia_cover")],
        )


def test_a_published_disposition_must_carry_a_frozen_asset_id(tmp_path: Path) -> None:
    """assetId 与处置同批成型；留空等于把分配推迟回物化期。"""

    entity_dir = tmp_path / "entities" / "地点" / "景区" / "测试实体甲"

    with pytest.raises(ValueError):
        _freeze(entity_dir, [_record("hero.jpg", HomepageAssetDisposition.COVER)])


def test_placement_does_not_promote_a_related_asset_from_the_body() -> None:
    """成稿正文不得反过来改处置：冻结为 related 的图只能进相关图片区。"""

    body = "# 测试实体甲\n\n## 历史沿革\n\n清代重修。\n"
    assets = [
        {
            "assetId": "jia_cover",
            "fileName": "jia_cover.jpg",
            "role": "cover",
            "caption": "测试实体甲",
        },
        {
            "assetId": "jia_gate",
            "fileName": "jia_gate.jpg",
            "role": "related",
            "caption": "测试实体甲的清代山门",
        },
    ]
    placements = [
        {
            "assetId": "jia_gate",
            "sectionSlug": "历史沿革",
            "placementType": "inline",
        }
    ]

    out = place_homepage_assets_in_markdown(body, assets, placements=placements)

    assert "## 相关图片" in out
    assert ':::figure id="jia_gate"' not in out
    assert assets[1]["role"] == "related"


def test_a_frozen_inline_asset_without_an_anchor_fails_closed() -> None:
    """冻结说内嵌、成稿既无锚点也无占位符时失败，由 repair 通道让创作方补回。"""

    body = "# 测试实体甲\n\n## 概况\n\n正文。\n"
    assets = [
        {
            "assetId": "jia_gate",
            "fileName": "jia_gate.jpg",
            "role": "inline",
            "caption": "测试实体甲的清代山门",
        }
    ]

    with pytest.raises(ValueError, match="no anchor in the delivered draft"):
        place_homepage_assets_in_markdown(body, assets, placements=[])


def test_current_freeze_plan_reads_request_and_target_set_without_legacy_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    execution_id = "20260901--travel-image-current-freeze--china--pilot-016"
    root = tmp_path / execution_id
    target = {
        "name": "测试实体甲",
        "entityType": "地点/景区",
        "publishAngle": "美图",
        "publishTitle": "测试图片作品",
        "publishSeq": 1,
    }
    from core.io import write_json
    from core import paths

    write_json(
        root / "0.plan/request.json",
        {"executionId": execution_id, "carrier": "image"},
    )
    write_json(
        root / "0.plan/target_set.json",
        {"executionId": execution_id, "targetCount": 1, "targets": [target]},
    )
    monkeypatch.setattr(paths, "execution_root", lambda _execution_id: root)

    carrier, targets = _frozen_execution_plan(execution_id)

    assert carrier == "image"
    assert targets == [target]
    assert not (root / "0.plan/execution_spec.yaml").exists()


def test_image_disposition_is_create_once_and_freezes_registry_asset_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    execution_id = "20260901--travel-image-current-freeze--china--pilot-017"
    object_dir = tmp_path / "posts/image/美图/测试图片作品/1"
    source_ref = "sources/image-unit/assets/001.jpg"
    candidate = {
        "path": tmp_path / "source.jpg",
        "sourceAssetRef": source_ref,
        "sourceAssetId": "001_001",
        "caption": "测试实体甲",
        "license": "CC BY 4.0",
        "collectionPageUrl": "https://example.com/image",
        "authorizationProof": "https://example.com/license",
        "usageScope": "app_publish",
        "distributionDecision": "research_allowed",
    }
    candidate["path"].write_bytes(b"fixture")

    class RuntimeState:
        execution_sequence = 17

    class Verdict:
        status = "safe"
        reasons = ()

    monkeypatch.setattr(
        "content.execution.runtime_state.load_execution_runtime_state",
        lambda _execution_id: RuntimeState(),
    )
    monkeypatch.setattr(
        "content.source.source_assets.object_image_candidates",
        lambda _object_dir, _execution_id: [candidate],
    )
    monkeypatch.setattr(
        "core.paths.execution_post_object_dir",
        lambda *_args, **_kwargs: object_dir,
    )
    monkeypatch.setattr(
        homepage_media_freeze,
        "_image_publish_admission_issue",
        lambda _image: "",
    )
    from content.execution import asset_registry

    registry = asset_registry.ExecutionAssetRegistry(execution_id, 17)
    monkeypatch.setattr(
        asset_registry,
        "load_execution_asset_registry",
        lambda _execution_id, _sequence: registry,
    )

    target = {
        "name": "测试实体甲",
        "publishAngle": "美图",
        "publishTitle": "测试图片作品",
        "publishSeq": 1,
    }
    first = homepage_media_freeze.freeze_image_media_dispositions(execution_id, target)
    second = homepage_media_freeze.freeze_image_media_dispositions(execution_id, target)

    assert first == second
    assert first["objectRef"] == "posts/image/美图/测试图片作品/1"
    assert first["assets"][0]["disposition"] == "cover"
    assert first["assets"][0]["assetId"]
    assert registry.resolve(
        asset_registry.execution_asset_owner_key(
            execution_sequence=17,
            entity_name="测试实体甲",
            role="cover",
            ref=f"posts/image/美图/测试图片作品/1#{source_ref}",
        )
    ) == first["assets"][0]["assetId"]


def test_image_compose_consumes_frozen_asset_id_without_reassessment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from content.execution.asset_registry import (
        ExecutionAssetRegistry,
        execution_asset_owner_key,
    )
    from content.post.article import route_assets

    execution_id = "20260901--travel-image-current-freeze--china--pilot-018"
    ref = "测试图片作品"
    source_asset_ref = "sources/image-unit/assets/001.jpg"
    object_dir = tmp_path / "posts/image/美图/测试图片作品/1"
    source_unit = tmp_path / "sources/image-unit"
    source_path = source_unit / "assets/001.jpg"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"fixture")
    write_json(
        source_unit / "meta.json",
        {"researchLane": "image", "imagePlacements": [{"fileName": "001.jpg"}]},
    )
    write_json(
        source_unit / "assets/index.json",
        {
            "assets": [
                {
                    "sourceAssetId": "001_001",
                    "fileName": "001.jpg",
                    "sourceCollectionId": "fixture:collection",
                    "caption": "测试实体甲",
                }
            ]
        },
    )
    write_json(
        object_dir / "1.download/source_refs.json",
        {
            "schema": "quwoquan_data.object_source_refs",
            "objectRef": "posts/image/美图/测试图片作品/1",
            "sources": [
                {
                    "sourceUnitId": "image-unit",
                    "sourceRef": "sources/image-unit/source.md",
                    "metaRef": "sources/image-unit/meta.json",
                }
            ],
        },
    )
    (source_unit / "source.md").write_text("fixture", encoding="utf-8")
    registry = ExecutionAssetRegistry(execution_id, 18)
    registry.path = tmp_path / "asset_id_registry.json"
    owner_ref = f"posts/image/美图/测试图片作品/1#{source_asset_ref}"
    owner_key = execution_asset_owner_key(
        execution_sequence=18,
        entity_name="测试实体甲",
        role="cover",
        ref=owner_ref,
    )
    assert registry.claim(owner_key, "frozen_cover_asset") is True
    _freeze(
        object_dir,
        [
            HomepageMediaDisposition(
                source_asset_ref=source_asset_ref,
                source_asset_id="001_001",
                disposition=HomepageAssetDisposition.COVER,
                asset_id="frozen_cover_asset",
                reason="published",
            )
        ],
    )
    candidate = {
        "path": source_path,
        "sourceRef": "sources/image-unit/source.md",
        "sourceAssetRef": source_asset_ref,
        "sourceAssetId": "001_001",
        "sourceCollectionId": "fixture:collection",
        "researchLane": "image",
        "caption": "测试实体甲",
    }
    monkeypatch.setattr(
        route_assets,
        "load_execution_runtime_state",
        lambda _execution_id: type("Runtime", (), {"execution_sequence": 18})(),
    )
    monkeypatch.setattr(
        route_assets,
        "load_execution_asset_registry",
        lambda _execution_id, _sequence: registry,
    )
    monkeypatch.setattr(
        route_assets,
        "_entity_image_candidates",
        lambda *_args, **_kwargs: [candidate],
    )
    monkeypatch.setattr(
        "content.post.object_index.content_object_dir",
        lambda _execution_id, _ref: object_dir,
    )
    monkeypatch.setattr(
        "core.paths.execution_root",
        lambda _execution_id: tmp_path,
    )
    monkeypatch.setattr(
        "content.source.source_assets.object_image_candidates",
        lambda _object_dir, _execution_id: [candidate],
    )
    monkeypatch.setattr(
        route_assets,
        "assess_image",
        lambda _path: pytest.fail("image compose must not reassess frozen media"),
    )
    monkeypatch.setattr(
        route_assets,
        "allocate_post_asset_id",
        lambda **_kwargs: pytest.fail("image compose must not allocate a second assetId"),
    )

    assets = route_assets._build_route_assets(
        execution_id,
        ref,
        {
            "carrier": "image",
            "sourceCollectionId": "fixture:collection",
            "assetRefs": [source_asset_ref],
            "executionSequence": 18,
        },
        {"routeNodes": [{"entityName": "测试实体甲", "entityRef": "地点/景区/测试实体甲"}]},
    )

    assert [asset["assetId"] for asset in assets] == ["frozen_cover_asset"]
    assert frozen_disposition_by_source_asset(object_dir)[source_asset_ref]["assetId"] == assets[0]["assetId"]

def test_image_freeze_fails_explicitly_without_safe_media_and_writes_no_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    execution_id = "20260901--travel-image-current-freeze--china--pilot-019"
    object_dir = tmp_path / "posts/image/美图/测试图片作品/1"
    candidate = {
        "path": tmp_path / "unsafe.jpg",
        "sourceAssetRef": "sources/image-unit/assets/unsafe.jpg",
        "sourceAssetId": "001_001",
    }
    candidate["path"].write_bytes(b"fixture")

    monkeypatch.setattr(
        "content.execution.runtime_state.load_execution_runtime_state",
        lambda _execution_id: type("Runtime", (), {"execution_sequence": 19})(),
    )
    monkeypatch.setattr(
        "content.source.source_assets.object_image_candidates",
        lambda _object_dir, _execution_id: [candidate],
    )
    monkeypatch.setattr(
        "core.paths.execution_post_object_dir",
        lambda *_args, **_kwargs: object_dir,
    )
    monkeypatch.setattr(
        homepage_media_freeze,
        "_image_publish_admission_issue",
        lambda _image: "safety:watermark_or_platform_text",
    )
    from content.execution import asset_registry

    registry = asset_registry.ExecutionAssetRegistry(execution_id, 19)
    registry.path = tmp_path / "unsafe_asset_id_registry.json"
    monkeypatch.setattr(
        asset_registry,
        "load_execution_asset_registry",
        lambda _execution_id, _sequence: registry,
    )

    with pytest.raises(ValueError, match="DATA.MEDIA.PUBLISHABLE_SHORTFALL"):
        homepage_media_freeze.freeze_image_media_dispositions(
            execution_id,
            {
                "name": "测试实体甲",
                "publishAngle": "美图",
                "publishTitle": "测试图片作品",
                "publishSeq": 1,
            },
        )

    assert not (object_dir / "evidence/media_dispositions.json").exists()
    assert registry.entries == {}
