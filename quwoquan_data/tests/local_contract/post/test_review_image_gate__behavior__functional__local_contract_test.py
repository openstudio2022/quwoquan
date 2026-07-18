"""审查阶段图片门 contract tests：unsafe->阻断改稿，人脸->人工复核，clean->放行。

可直接运行：python3 quwoquan_data/tests/local_contract/post/test_review_image_gate__behavior__functional__local_contract_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(SCRIPTS_ROOT))

import numpy as np  # noqa: E402
import cv2  # noqa: E402

from content.post.article.route_review_checks import (  # noqa: E402
    _check_image_gate,
    _check_image_fidelity,
    _check_carrier_consistency,
    _check_evidence_quality,
    _check_image_source_scope,
    _review_fallback_stage,
)
from content.post.article.route_core import _image_caption_from_article  # noqa: E402

FIXTURE_MEDIA = (
    DATA_ROOT.parent
    / "quwoquan_service/contracts/metadata/_shared/test_fixtures/media/media"
)
FACE_FIXTURE = FIXTURE_MEDIA / "avatar/user/fixture_user_article/v1/avatar.png"
_TMP = Path(tempfile.mkdtemp(prefix="review_img_"))


def _clean(path: Path) -> Path:
    img = np.zeros((220, 300, 3), np.uint8)
    for x in range(300):
        img[:, x] = (x % 256, (x * 2) % 256, (x * 3) % 256)
    cv2.imwrite(str(path), img)
    return path


def _watermark(path: Path) -> Path:
    img = np.full((220, 300, 3), 255, np.uint8)
    cv2.putText(img, "tripadvisor", (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 3)
    cv2.imwrite(str(path), img)
    return path


def _face_fixture() -> Path | None:
    return FACE_FIXTURE if FACE_FIXTURE.is_file() else None


def test_clean_assets_pass():
    assets = [{"assetId": "a1", "sourcePath": str(_clean(_TMP / "c1.jpg"))}, {"assetId": "a2", "sourcePath": str(_clean(_TMP / "c2.jpg"))}]
    gate = _check_image_gate({"assets": assets})
    # 两张几乎相同的渐变图会被判近重复 -> 仍应阻断（去重保护）；用一张即可
    single = _check_image_gate({"assets": [assets[0]]})
    assert single["passed"] is True, single["issues"]
    assert single["humanReview"] is False


def test_text_only_article_skips_image_gate():
    gate = _check_image_gate({"carrier": "article", "publishMediaMode": "text_only", "assets": []})
    assert gate["passed"] is True
    assert gate["humanReview"] is False
    assert any("text-only" in note for note in gate.get("notes", []))


def test_text_only_article_skips_evidence_asset_requirement():
    gate = _check_evidence_quality(
        "这是一篇已经由 agent 写好的长文，发布降级为纯文本时不需要配图。",
        {"mustIncludeFacts": []},
        {"recommendation": "use", "evidenceBundle": {}},
        {"carrier": "article", "publishMediaMode": "text_only", "assets": []},
    )

    assert "compose payload missing assets" not in gate["issues"]


def test_unsafe_blocks_revision():
    assets = [{"assetId": "w", "sourcePath": str(_watermark(_TMP / "wm.jpg"))}]
    gate = _check_image_gate({"assets": assets})
    assert gate["passed"] is False
    assert any("unsafe" in i for i in gate["issues"])
    fallback = _review_fallback_stage({
        "evidenceQuality": {"passed": True},
        "provenanceRewrite": {"passed": True},
        "routeCoverage": {"passed": True},
        "narrativeContinuity": {"passed": True},
        "travelogueDensity": {"passed": True},
        "imageGate": gate,
        "carrierConsistency": {"passed": True},
    })
    assert fallback == "agent_compose"


def test_face_requires_human_review():
    """新 HITL 契约：含人脸图片不再硬阻断 review，而是标记 humanReview 并记入账本，
    由发布门 + annotate 在发布前裁决（存疑必须人确认）。"""
    face = _face_fixture()
    assert face is not None, f"缺少仓库固定人脸 fixture: {FACE_FIXTURE}"
    gate = _check_image_gate({"assets": [{"assetId": "f", "sourcePath": str(face)}]})
    # 不因人脸阻断 review（无 unsafe/重复时 passed=True）
    assert gate["passed"] is True, gate["issues"]
    assert gate["humanReview"] is True
    assert "f" in gate["humanReviewTargets"]
    # review 不再为人脸触发 manual fallback（仅记录到账本，发布门兜底）
    fallback = _review_fallback_stage({
        "generatorProvenance": {"passed": True},
        "evidenceQuality": {"passed": True},
        "provenanceRewrite": {"passed": True},
        "routeCoverage": {"passed": True},
        "narrativeContinuity": {"passed": True},
        "travelogueDensity": {"passed": True},
        "factTraceability": {"passed": True},
        "imageGate": gate,
        "carrierConsistency": {"passed": True},
    })
    assert fallback == "review"


def test_image_only_fallback_does_not_require_prose_checks():
    fallback = _review_fallback_stage({
        "generatorProvenance": {"passed": True},
        "imageGate": {"passed": True},
        "imageFidelity": {"passed": True},
        "carrierConsistency": {"passed": True},
    })

    assert fallback == "review"


def test_image_caption_extraction_ignores_structural_gallery_markup():
    article = """# 毕棚沟龙王海与红石滩秋色

这组图只看两件事：湖面倒影够不够稳，红石与彩林是不是在同一条秋色线上。

:::figure
asset://bipenggou_01
caption: 龙王海
:::

授权归因：CC BY-SA 4.0 / Photographer
"""

    assert _image_caption_from_article(article) == (
        "这组图只看两件事：湖面倒影够不够稳，红石与彩林是不是在同一条秋色线上。"
    )


def test_carrier_consistency_article_needs_sections():
    bad = _check_carrier_consistency({"carrier": "article", "articleMarkdown": "# t\n\n只有一段没有小节。\n"})
    assert bad["passed"] is False
    good = _check_carrier_consistency({"carrier": "article", "articleMarkdown": "# t\n\n## a\n\nx\n\n## b\n\ny\n\n## c\n\nz" * 40})
    assert good["passed"] is True


def test_carrier_consistency_image_tracks_pack_assets():
    article = '\n'.join([
        '# 图集',
        '',
        ':::figure',
        'asset://a1',
        ':::',
        '',
        ':::figure',
        'asset://a2',
        ':::',
    ])
    gate = _check_carrier_consistency(
        {
            "carrier": "image",
            "articleMarkdown": article,
            "assets": [
                {"assetId": "a1", "sourceCollectionId": "collection-a"},
                {"assetId": "a2", "sourceCollectionId": "collection-a"},
            ],
        }
    )
    assert gate["passed"] is True, gate["issues"]


def test_carrier_consistency_image_blocks_mixed_source_collections():
    article = '\n'.join([
        '# 图集',
        '',
        ':::figure',
        'asset://a1',
        ':::',
        '',
        ':::figure',
        'asset://a2',
        ':::',
    ])
    gate = _check_carrier_consistency(
        {
            "carrier": "image",
            "articleMarkdown": article,
            "assets": [
                {"assetId": "a1", "sourceCollectionId": "collection-a"},
                {"assetId": "a2", "sourceCollectionId": "collection-a"},
                {"assetId": "a3", "sourceCollectionId": "collection-b"},
            ],
        }
    )
    assert gate["passed"] is False
    assert any("one sourceCollectionId" in issue for issue in gate["issues"]), gate["issues"]


def test_image_source_scope_blocks_article_sources_in_image_work():
    gate = _check_image_source_scope(
        {
            "carrier": "image",
            "assets": [
                {
                    "assetId": "a1",
                    "sourcePath": "/batch/entities/地点/景区/九寨沟/1.download/sources/14.image_open/assets/001.jpg",
                    "sourceCollectionId": "collection-a",
                }
            ],
            "sourcePaths": [
                "/batch/entities/地点/景区/九寨沟/1.download/sources/14.image_open/source.md",
                "/batch/entities/地点/景区/九寨沟/1.download/sources/03.article_qunar_base_1/source.md",
            ],
        }
    )
    assert gate["passed"] is False
    assert any("non-image source units" in issue for issue in gate["issues"]), gate["issues"]


def test_image_fidelity_blocks_multi_creator_and_missing_provenance():
    gate = _check_image_fidelity(
        {
            "carrier": "image",
            "title": "九寨沟夏末倒影",
            "caption": "湖面倒影与彩林一起出现。",
            "storySpine": {"primaryEntity": "九寨沟", "sourceCollectionId": "pin-001", "beats": ["九寨沟倒影", "彩林"]},
            "assets": [
                {
                    "assetId": "a1",
                    "sourceCollectionId": "pin-001",
                    "collectionPageUrl": "https://www.pinterest.com/pin/1/",
                    "license": "attribution_no_watermark",
                    "authorizationProof": "https://img.example.com/1.jpg",
                    "creator": "作者甲",
                    "title": "九寨沟倒影",
                },
                {
                    "assetId": "a2",
                    "sourceCollectionId": "pin-001",
                    "collectionPageUrl": "https://www.pinterest.com/pin/1/",
                    "license": "attribution_no_watermark",
                    "authorizationProof": "https://img.example.com/2.jpg",
                    "creator": "作者乙",
                    "title": "九寨沟彩林",
                },
                {
                    "assetId": "a3",
                    "sourceCollectionId": "pin-001",
                    "license": "attribution_no_watermark",
                    "title": "缺少出处字段",
                },
            ],
        }
    )
    assert gate["passed"] is False
    assert any("one creator/sourceAuthor" in issue for issue in gate["issues"]), gate["issues"]
    assert any("image provenance fields incomplete" in issue for issue in gate["issues"]), gate["issues"]


def test_image_fidelity_blocks_rewrite_drift_and_routes_to_compose_brief():
    gate = _check_image_fidelity(
        {
            "carrier": "image",
            "title": "城市咖啡馆夜谈",
            "caption": "深夜创业者的都市神经漫游与电车轰鸣。",
            "storySpine": {"primaryEntity": "九寨沟", "sourceCollectionId": "pin-002", "beats": ["九寨沟瀑布", "原始森林"]},
            "assets": [
                {
                    "assetId": "a1",
                    "sourceCollectionId": "pin-002",
                    "collectionPageUrl": "https://www.pinterest.com/pin/2/",
                    "license": "attribution_no_watermark",
                    "authorizationProof": "https://img.example.com/21.jpg",
                    "creator": "作者甲",
                    "title": "九寨沟瀑布",
                    "caption": "原始森林与瀑布",
                }
            ],
        }
    )
    assert gate["passed"] is False
    assert any("light polishing" in issue for issue in gate["issues"]), gate["issues"]
    fallback = _review_fallback_stage(
        {
            "generatorProvenance": {"passed": True},
            "imageGate": {"passed": True},
            "imageFidelity": gate,
            "carrierConsistency": {"passed": True},
        }
    )
    assert fallback == "compose_brief"


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"review image gate tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
