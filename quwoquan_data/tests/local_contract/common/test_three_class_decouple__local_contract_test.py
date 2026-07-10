"""P3 三类解耦契约（R-HSE06 扩源后口径）：主页主源两级权威 + 文章【含视频则放弃】检测。

- 实体主页 base draft 主源 = 第一权威百科（wiki/维基导游/百度/搜狗）优先 +
  第二权威（官网/政务文旅）兜底；权威媒体/知识图谱仍 supporting，头条百科 reference_only。
- 排序恒为百科在前、第二权威在后（homepage_primary_authority_rank）。
- 文章来源含内联视频（原生 <video> / 主流视频站嵌入）即标记 hasVideo，内容计划据此弃稿。

可直接运行：python3 quwoquan_data/tests/local_contract/common/test_three_class_decouple__local_contract_test.py
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

os.environ.setdefault("QWQ_RUNTIME_ROOT", tempfile.mkdtemp(prefix="three_class_rt_"))

from download.fetch import html_has_inline_video  # noqa: E402
from build.homepage_text import _homepage_source_priority  # noqa: E402
from download.research.source_quality import _homepage_can_seed_base_draft  # noqa: E402
from download.source_inputs import content_type_for_lane, LANE_CONTENT_TYPE  # noqa: E402


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


def test_homepage_primary_source_two_tier_authority():
    # 第一权威百科授予 primary（priority > 0）。
    encyclopedia_priorities = []
    for meta in (
        {"researchLane": "homepage", "platform": "维基百科", "category": "encyclopedia"},
        {"researchLane": "homepage", "platform": "维基导游", "category": "encyclopedia"},
        {"researchLane": "homepage", "platform": "百度百科", "category": "encyclopedia"},
        {"researchLane": "homepage", "platform": "搜狗百科", "category": "encyclopedia"},
    ):
        priority = _homepage_source_priority(meta)
        assert priority > 0, meta
        encyclopedia_priorities.append(priority)

    # 头条百科只允许 reference_only，不得作为 primary。
    toutiao = {"researchLane": "homepage", "platform": "头条百科", "category": "encyclopedia"}
    assert _homepage_source_priority(toutiao) <= 0, toutiao

    # R-HSE06：官网/政务文旅是第二权威主源（priority > 0），但恒排在全部百科之后。
    official = {"researchLane": "homepage", "platform": "官方网站", "category": "official_site"}
    gov = {"researchLane": "homepage", "platform": "政务文旅", "category": "government_tourism"}
    official_priority = _homepage_source_priority(official)
    gov_priority = _homepage_source_priority(gov)
    assert official_priority > 0, official
    assert gov_priority > 0, gov
    assert min(encyclopedia_priorities) > max(official_priority, gov_priority)

    # 权威媒体仍不具备主源资格。
    media = {"researchLane": "homepage", "platform": "权威媒体", "category": "authoritative_media"}
    assert _homepage_source_priority(media) <= 0, media


def test_homepage_base_draft_seed_two_tier_authority():
    # 第一权威百科可作主页 base draft 主源。
    assert _homepage_can_seed_base_draft({"platform": "维基百科", "category": "encyclopedia"})
    assert _homepage_can_seed_base_draft({"platform": "维基导游", "category": "encyclopedia"})
    assert _homepage_can_seed_base_draft({"platform": "百度百科", "category": "encyclopedia"})
    assert not _homepage_can_seed_base_draft({"platform": "头条百科", "category": "encyclopedia"})
    # R-HSE06：官网/政务文旅（第二权威）可作主页 base draft 主源。
    assert _homepage_can_seed_base_draft({"platform": "景区官网", "category": "official_site"})
    assert _homepage_can_seed_base_draft({"platform": "文旅厅", "category": "government_tourism"})
    # 权威媒体与攻略/UGC 仍不可。
    assert not _homepage_can_seed_base_draft({"platform": "权威媒体", "category": "authoritative_media"})
    assert not _homepage_can_seed_base_draft({"platform": "小红书", "category": "community_post"})


def test_secondary_authority_requires_factual_compression():
    """R-HSE06：第二权威源（官网/政务文旅）与百度/搜狗百科一样必须走事实化压缩。"""
    from download.handler_fetch import _requires_factual_compression

    assert _requires_factual_compression({"url": "https://baike.baidu.com/item/x"})
    assert _requires_factual_compression({"url": "https://baike.sogou.com/v?query=x"})
    assert _requires_factual_compression(
        {"platform": "官方网站", "category": "official_site", "url": "https://www.example-scenic.cn/"}
    )
    assert _requires_factual_compression(
        {"platform": "政务文旅", "url": "https://wlt.sc.gov.cn/scwlt/gsgg/notice.shtml"}
    )
    # 第一权威维基（开放许可）不压缩。
    assert not _requires_factual_compression(
        {"platform": "维基百科", "category": "encyclopedia", "url": "https://zh.wikipedia.org/wiki/x"}
    )


def test_write_source_unit_persists_has_video_flag():
    from _common.source_unit import write_source_unit

    obj = Path(tempfile.mkdtemp(prefix="three_class_obj_"))
    # 含视频来源：hasVideo=True 必须落入 manifest（meta.json），供内容计划弃稿。
    manifest_video = write_source_unit(
        obj,
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
        ordinal=2,
        source_id="article_plain",
        source_md="---\ntitle: y\n---\n正文",
        research_lane="article",
        source_role="base",
        url="https://example.com/b",
        title="纯图文攻略",
    )
    assert manifest_plain.get("hasVideo") is False


def test_content_type_routing_by_lane():
    # P3 三类解耦：lane → 内容类型路由真相源（homepage=entity/article=article/image=image）。
    assert content_type_for_lane("homepage") == "entity"
    assert content_type_for_lane("article") == "article"
    assert content_type_for_lane("image") == "image"
    # 未知/空/legacy 回落为 article（旧混合计划无独立 lane）。
    assert content_type_for_lane("") == "article"
    assert content_type_for_lane("legacy") == "article"
    assert content_type_for_lane("unknown_lane") == "article"
    # 三类不串味：每个 lane 路由唯一确定。
    assert set(LANE_CONTENT_TYPE.values()) == {"entity", "article", "image"}


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"three-class decouple tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
