"""P3 三类解耦契约：主页三百科闭集 + 文章【含视频则放弃】检测。

- 实体主页 base draft 主源闭集 = Wikipedia / 百度 / 今日头条百科。
- 排序权威 rank = 0 / 1 / 2。
- 文章来源含内联视频（原生 <video> / 主流视频站嵌入）即标记 hasVideo，内容计划据此弃稿。

可直接运行：python3 quwoquan_data/tests/local_contract/core/test_three_class_decouple__behavior__functional__local_contract_test.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import os  # noqa: E402
import pytest  # noqa: E402


from content.source.html_text import html_has_inline_video  # noqa: E402
from content.homepage.homepage_text import _homepage_source_priority  # noqa: E402
from content.source.research.homepage_source_policy import _homepage_can_seed_base_draft  # noqa: E402
from content.source.source_inputs import content_type_for_lane  # noqa: E402
from core.carrier_contract import CARRIER_LANES  # noqa: E402


def test_article_video_detection_positive_and_negative():
    # 原生 <video> 标签。
    assert html_has_inline_video("<div><p>正文</p><video src='x.mp4'></video></div>")
    # <source type=video> 形式。
    assert html_has_inline_video("<video><source type='video/mp4' src='x.mp4'></video>")
    # 主流视频站 iframe 嵌入（B 站 / YouTube / 腾讯视频）。
    assert html_has_inline_video("<iframe src='https://player.bilibili.com/player.html?aid=1'></iframe>")
    assert html_has_inline_video("<iframe src='https://www.youtube.com/embed/abc'></iframe>")
    assert html_has_inline_video("<iframe src='https://v.qq.com/x/page/abc.html'></iframe>")
    # 纯图文文章不误判。
    assert not html_has_inline_video(
        "<article><h2>九寨沟</h2><p>清晨抵达五花海。</p><img src='a.jpg'/></article>"
    )
    assert not html_has_inline_video("")


def test_homepage_primary_source_three_encyclopedia_closed_set():
    encyclopedia_priorities = []
    for meta in (
        {"researchLane": "homepage", "sourceKind": "wikipedia", "extractor": "wikipedia_api", "canonicalUrl": "https://zh.wikipedia.org/wiki/西湖", "policyRevision": "encyclopedia-primary"},
        {"researchLane": "homepage", "sourceKind": "baidu_baike", "extractor": "baidu_baike_openapi", "canonicalUrl": "https://baike.baidu.com/item/西湖", "policyRevision": "encyclopedia-primary"},
        {"researchLane": "homepage", "sourceKind": "toutiao_baike", "extractor": "toutiao_baike_html", "canonicalUrl": "https://www.baike.com/wiki/西湖", "policyRevision": "encyclopedia-primary"},
    ):
        priority = _homepage_source_priority(meta)
        assert priority > 0, meta
        encyclopedia_priorities.append(priority)

    wikivoyage = {"researchLane": "homepage", "platform": "维基导游", "category": "encyclopedia"}
    official = {"researchLane": "homepage", "platform": "官方网站", "category": "official_site"}
    gov = {"researchLane": "homepage", "platform": "政务文旅", "category": "government_tourism"}
    assert _homepage_source_priority(wikivoyage) <= 0, wikivoyage
    assert _homepage_source_priority(official) <= 0, official
    assert _homepage_source_priority(gov) <= 0, gov

    # 权威媒体仍不具备主源资格。
    media = {"researchLane": "homepage", "platform": "权威媒体", "category": "authoritative_media"}
    assert _homepage_source_priority(media) <= 0, media


def test_homepage_base_draft_seed_three_encyclopedia_closed_set():
    identities = [
        ("wikipedia", "wikipedia_api", "https://zh.wikipedia.org/wiki/西湖"),
        ("baidu_baike", "baidu_baike_openapi", "https://baike.baidu.com/item/西湖"),
        ("toutiao_baike", "toutiao_baike_html", "https://www.baike.com/wiki/西湖"),
    ]
    for source_kind, extractor, url in identities:
        assert _homepage_can_seed_base_draft({
            "sourceKind": source_kind,
            "extractor": extractor,
            "canonicalUrl": url,
            "policyRevision": "encyclopedia-primary",
        })
    assert not _homepage_can_seed_base_draft(
        {"platform": "维基百科", "category": "encyclopedia"}
    ), "禁止 platform/host 猜 sourceKind"
    assert not _homepage_can_seed_base_draft({"platform": "维基导游", "category": "encyclopedia"})
    assert not _homepage_can_seed_base_draft({"platform": "景区官网", "category": "official_site"})
    assert not _homepage_can_seed_base_draft({"platform": "文旅厅", "category": "government_tourism"})
    assert not _homepage_can_seed_base_draft({"platform": "权威媒体", "category": "authoritative_media"})
    assert not _homepage_can_seed_base_draft({"platform": "小红书", "category": "community_post"})


def test_non_open_encyclopedia_requires_factual_compression():
    from content.source.handler_fetch import _requires_factual_compression

    assert _requires_factual_compression({"sourceKind": "baidu_baike"})
    assert _requires_factual_compression({"sourceKind": "toutiao_baike"})
    # 第一权威维基（开放许可）不压缩。
    assert not _requires_factual_compression(
        {"sourceKind": "wikipedia"}
    )


def test_write_source_unit_persists_has_video_flag():
    from content.source.source_unit import write_source_unit

    obj = Path(tempfile.mkdtemp(prefix="three_class_obj_"))
    execution_id = "20260711--travel-article-video-flag--cn-sichuan--canary-001"
    # 含视频来源：hasVideo=True 必须落入 manifest（meta.json），供内容计划弃稿。
    manifest_video = write_source_unit(
        obj,
        execution_id=execution_id,
        ordinal=1,
        source_id="article_with_video",
        source_md="---\ntitle: x\n---\n正文",
        research_lane="article",
        source_role="base",
        url="https://example.com/a",
        title="含视频攻略",
        has_video=True,
    )
    assert manifest_video.get("hasVideo") is True

    # 默认（无视频）：hasVideo=False。
    manifest_plain = write_source_unit(
        obj,
        execution_id=execution_id,
        ordinal=2,
        source_id="article_plain",
        source_md="---\ntitle: y\n---\n正文",
        research_lane="article",
        source_role="base",
        url="https://example.com/b",
        title="纯图文攻略",
    )
    assert manifest_plain.get("hasVideo") is False


def test_homepage_source_unit_rejects_forbidden_source():
    from content.source.source_unit import write_source_unit

    obj = Path(tempfile.mkdtemp(prefix="homepage_source_closed_set_"))
    try:
        write_source_unit(
            obj,
            ordinal=1,
            source_id="home_official",
            source_md="官网正文",
            platform="景区官网",
            source_category="official",
            research_lane="homepage",
            url="https://example.gov.cn/scenic",
        )
        raise AssertionError("官网不得进入 homepage source unit")
    except ValueError as exc:
        assert "encyclopedia-primary" in str(exc)


def test_content_type_routing_by_lane():
    # lane → 内容类型路由真相源（homepage=entity，其余 lane 与 carrier 同名）。
    assert content_type_for_lane("homepage") == "entity"
    assert content_type_for_lane("article") == "article"
    assert content_type_for_lane("image") == "image"
    assert content_type_for_lane("video") == "video"
    for invalid in ("", "legacy", "unknown_lane"):
        with pytest.raises(ValueError):
            content_type_for_lane(invalid)
    # 四载体不串味：每个 lane 由 CarrierContract 唯一声明。
    assert set(CARRIER_LANES) == {"homepage", "article", "image", "video"}


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"three-class decouple tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
