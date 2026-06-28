"""章节大纲解析 + 确定性配图注入 contract test。

覆盖用户契约：
- 百科 source.md 的 wiki `==/===` 多级标题被正确解析为 outline（含「技术变革」「相关古迹」）。
- 配图按封面优先 / 章节锚点 / 段落锚点 / 图集兜底注入为 App `:::figure` 块，且幂等。

可直接运行：python3 quwoquan_data/tests/local_contract/common/test_section_outline_and_placement__local_contract_test.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from _common.asset_placement import caption_semantic_issues, place_assets_in_markdown, referenced_asset_ids  # noqa: E402
from _common.section_outline import (  # noqa: E402
    outline_coverage_issues,
    outline_required_sections,
    page_section_slugs,
    parse_section_outline,
    render_outline_tree,
    section_titles,
)
from build.homepage_validation import _asset_closure_issues  # noqa: E402

# 都江堰式 wiki source.md 片段（含 ==/=== 多级标题与尾节）。
_WIKI_SOURCE = """---
url: https://zh.wikipedia.org/wiki/都江堰
platform: 维基百科
---

都江堰是中国古代的大型水利工程，位于四川省都江堰市城西。导语段提供基础事实，篇幅足够。

== 主体工程 ==


=== 分水鱼嘴 ===

鱼嘴是都江堰的分水工程，因其形如鱼嘴而得名，位于江心，把岷江分成内外二江，决定内外江分流比例，是整个工程的关键所在，承担分水职责。

=== 宝瓶口 ===

宝瓶口是引水工程，在玉垒山的山崖上人工凿开缺口，上宽下窄形如瓶颈，控制内江进水量，灌溉成都平原大片农田，是关键的控水节点。

== 历史变迁 ==

=== 技术变革 ===

自秦以降都江堰一直以竹笼盛装卵石构筑，元朝吉当普首次引入铁石结构，明清两代在竹笼与铁石间反复，近代水泥混凝土技术引入后彻底平息争论，是工程史上的重大变革。

=== 相關古蹟 ===

都江堰周边古迹甚多，主要有二王庙、伏龙观、安澜桥、玉垒关等，二王庙纪念李冰父子，伏龙观内有东汉李冰石像，安澜桥横跨岷江，都是珍贵文物。

== 参考文献 ==

这些是参考文献尾节内容，不应作为关键章节统计。
"""


def test_parse_wiki_outline_keeps_multilevel_and_key_sections() -> None:
    outline = parse_section_outline(_WIKI_SOURCE)
    titles = section_titles(outline)
    # 多级层级保留：H2 主体工程/历史变迁，H3 分水鱼嘴/技术变革/相关古迹。
    assert "主体工程" in titles
    assert "历史变迁" in titles
    assert "技术变革" in titles, "技术变革 H3 必须被解析"
    assert "相關古蹟" in titles, "相关古迹 H3 必须被解析"
    by_title = {node.title: node for node in outline}
    assert by_title["主体工程"].level == 2
    assert by_title["分水鱼嘴"].level == 3
    assert by_title["技术变革"].level == 3
    # 关键章节（>200 字以下阈值放宽到 80 便于片段测试）有实质正文。
    required = outline_required_sections(outline, min_body_chars=60)
    required_titles = {n.title for n in required}
    assert {"分水鱼嘴", "技术变革", "相關古蹟"} <= required_titles
    # 渲染树形给 prompt：含 ### 缩进。
    tree = render_outline_tree(outline)
    assert "`### 技术变革`" in tree
    assert "`## 主体工程`" in tree


def test_placement_cover_then_section_then_gallery() -> None:
    body = (
        "# 都江堰\n\n"
        "## 概况\n\n都江堰是著名的水利工程，灌溉成都平原。这一段足够长以承载左右环绕排版的配图，避免过短拥挤。\n\n"
        "## 主体工程\n\n鱼嘴、飞沙堰、宝瓶口三大主体工程协同运作，泄洪排沙调节水量，这一段同样具备足够篇幅。\n\n"
        "## 技术变革\n\n竹笼到铁石再到混凝土的演进，是工程史上的重大变革，这一段也写得足够长。\n"
    )
    assets = [
        {"assetId": "都江堰_cover_3_aaa", "role": "cover", "caption": "都江堰鸟瞰"},
        {"assetId": "都江堰_detail_3_bbb", "role": "gallery", "caption": "鱼嘴分水"},
        {"assetId": "都江堰_detail_3_ccc", "role": "gallery", "caption": "宝瓶口"},
        {"assetId": "都江堰_detail_3_ddd", "role": "gallery", "caption": "二王庙"},
        {"assetId": "都江堰_detail_3_eee", "role": "gallery", "caption": "李冰石像"},
    ]
    out = place_assets_in_markdown(body, assets)
    # 封面 fullWidth 紧随 H1。
    h1_idx = out.index("# 都江堰")
    cover_idx = out.index(':::figure id="cover" layout="fullWidth"')
    assert cover_idx > h1_idx
    assert "asset://都江堰_cover_3_aaa" in out
    # 章节图：3 个章节各分配一张，layout 在 wrapRight/wrapLeft 间交替。
    assert 'layout="wrapRight"' in out
    assert 'layout="wrapLeft"' in out
    # 5 图 > 1封面+3章节 → 剩余进图集兜底。
    assert "## 图集" in out
    # 全部 5 张资产都出现（无丢图）。
    assert referenced_asset_ids(out) == {a["assetId"] for a in assets}


def test_placement_is_idempotent() -> None:
    body = "# 标题\n\n## 章节\n\n正文内容足够长以承载配图排版需求，不会过短。\n"
    assets = [{"assetId": "x_cover_1_aaa", "role": "cover", "caption": "封面"}]
    once = place_assets_in_markdown(body, assets)
    twice = place_assets_in_markdown(once, assets)
    assert once == twice, "已注入的 asset:// 不得重复注入"


def test_placement_respects_section_anchor() -> None:
    body = (
        "# 都江堰\n\n"
        "## 概况\n\n概况正文写得足够长，提供基础认知，不至于过短影响排版。\n\n"
        "## 技术变革\n\n技术演进的正文段落，足够长以承载章节锚点定位的配图。\n"
    )
    assets = [
        {"assetId": "djy_cover_1_aaa", "role": "cover", "caption": "封面"},
        {"assetId": "djy_detail_1_bbb", "role": "gallery", "caption": "铁龟"},
    ]
    placements = [{"assetId": "djy_detail_1_bbb", "sectionSlug": "技术变革", "caption": "铁龟"}]
    out = place_assets_in_markdown(body, assets, placements=placements)
    lines = out.split("\n")
    tech_idx = next(i for i, ln in enumerate(lines) if ln.strip() == "## 技术变革")
    overview_idx = next(i for i, ln in enumerate(lines) if ln.strip() == "## 概况")
    detail_idx = next(i for i, ln in enumerate(lines) if "asset://djy_detail_1_bbb" in ln)
    # 锚点图必须落在「技术变革」章节之后，而非「概况」。
    assert detail_idx > tech_idx > overview_idx


def test_outline_coverage_and_caption_semantic_gates() -> None:
    page = (
        "# 都江堰\n\n"
        "## 主体工程\n\n正文足够长以通过最小章节阈值检验，这里写一些与主体工程相关的描述内容。\n\n"
        "## 历史变迁\n\n历史变迁段落同样足够长，包含背景叙述。\n\n"
        "### 技术变革\n\n技术变革子章节保留多级目录结构，竹笼到混凝土的演进写在这里。\n\n"
        "### 相关古迹\n\n相关古迹子章节写二王庙伏龙观等内容，保证 slug 覆盖通过。\n"
    )
    required = ["技术变革", "相关古迹", "主体工程"]
    assert not outline_coverage_issues(required, page, label="test")
    assert "技术变革" in page_section_slugs(page)

    good_assets = [{"assetId": "a1", "fileName": "a1.jpg", "caption": "都江堰鸟瞰实景"}]
    bad_assets = [{"assetId": "a2", "fileName": "36661-Dujiangyan.jpg", "caption": "36661-Dujiangyan"}]
    assert not caption_semantic_issues(good_assets)
    assert caption_semantic_issues(bad_assets)


def test_homepage_validation_allows_text_only_and_inline_figures() -> None:
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        entity_dir = Path(tmp)
        manifest = {
            "assets": [
                {
                    "assetId": "都江堰_cover_2_a1b2c3d4",
                    "fileName": "都江堰_cover_2_a1b2c3d4.jpg",
                    "role": "cover",
                    "sourceRef": "entities/x/1.download/sources/01.wiki/source.md",
                    "sourceAssetRef": "entities/x/1.download/sources/01.wiki/assets/001.jpg",
                    "authorizationProof": "https://example.com/proof",
                }
            ],
            "textSourceRefs": ["entities/x/1.download/sources/01.wiki/source.md"],
            "imageSourceRefs": ["entities/x/1.download/sources/01.wiki/source.md"],
        }
        # 纯文字 page.md + manifest 有图 → 合法（finalize 前 Agent 草稿态）。
        (entity_dir / "assets").mkdir()
        (entity_dir / "assets" / "都江堰_cover_2_a1b2c3d4.jpg").write_bytes(b"fake")
        (entity_dir / "page.md").write_text("# 标题\n\n纯文字正文。\n", encoding="utf-8")
        assert not _asset_closure_issues(entity_dir, manifest, "pure-text")

        inline_page = (
            "# 标题\n\n"
            ':::figure id="cover" layout="fullWidth" caption="封面"\n'
            "asset://都江堰_cover_2_a1b2c3d4\n"
            ":::\n"
        )
        (entity_dir / "page.md").write_text(inline_page, encoding="utf-8")
        (entity_dir / "assets").mkdir(exist_ok=True)
        (entity_dir / "assets" / "都江堰_cover_2_a1b2c3d4.jpg").write_bytes(b"fake")
        assert not _asset_closure_issues(entity_dir, manifest, "inline-ok")

        broken = inline_page.replace("都江堰_cover_2_a1b2c3d4", "missing_asset")
        (entity_dir / "page.md").write_text(broken, encoding="utf-8")
        issues = _asset_closure_issues(entity_dir, manifest, "inline-broken")
        assert any("不在 manifest" in i for i in issues)


def _run() -> None:
    test_parse_wiki_outline_keeps_multilevel_and_key_sections()
    test_placement_cover_then_section_then_gallery()
    test_placement_is_idempotent()
    test_placement_respects_section_anchor()
    test_outline_coverage_and_caption_semantic_gates()
    test_homepage_validation_allows_text_only_and_inline_figures()
    print("OK: section_outline + asset_placement contract passed")


if __name__ == "__main__":
    _run()
