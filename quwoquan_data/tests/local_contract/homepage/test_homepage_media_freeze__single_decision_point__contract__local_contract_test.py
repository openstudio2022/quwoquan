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
from content.homepage.homepage_media_freeze import publish_disposition
from core.asset_placement import place_homepage_assets_in_markdown
from core.io import read_json
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
