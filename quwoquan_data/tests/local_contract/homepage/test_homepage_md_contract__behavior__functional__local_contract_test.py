"""实体主页 Markdown 三段结构契约测试（homepage-md-contract 交付项）。

覆盖：
1. place_homepage_assets_in_markdown：封面不进正文、有原图注按章节注入块级 fullWidth
   figure（每章节最多 1 张）、其余归入文末 `## 相关图片` 单 gallery，roles 就地收敛。
2. homepage_structure_issues：frontmatter 封面唯一、正文禁 wrap figure、gallery 仅页尾、
   roles 收敛 cover/inline/related、占位符残留 BLOCK。
3. caption_semantic_issues：related 空 caption 合法（无原图注不加说明）。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.asset_placement import (  # noqa: E402
    caption_semantic_issues,
    place_homepage_assets_in_markdown,
)
from content.homepage.homepage_assets import (  # noqa: E402
    _asset_wiki_filename,
    _normalize_wiki_filename,
    _placement_is_map_like,
)
from content.homepage.homepage_release import (  # noqa: E402
    _asset_wiki_filename as release_asset_wiki_filename,
)
from content.homepage.homepage_release import (  # noqa: E402
    _normalize_wiki_filename as release_normalize_wiki_filename,
)
from content.homepage.homepage_validation import homepage_structure_issues  # noqa: E402


_BODY = """# 黄龙风景名胜区

黄龙位于四川省阿坝州松潘县，以彩池、雪山、峡谷、森林四绝著称。

## 地质地貌

黄龙沟全长约7.5公里，钙华滩流是其核心地质景观。

## 主要景点

五彩池位于黄龙沟尽头，海拔3576米，共有693个彩池。
"""


def _assets() -> list[dict]:
    return [
        {"assetId": "黄龙_cover_9_aaaa1111", "role": "cover", "caption": "黄龙五彩池", "fileName": "黄龙_cover_9_aaaa1111.jpg"},
        {"assetId": "黄龙_detail_9_bbbb2222", "role": "related", "caption": "黄龙钙华滩流实景", "fileName": "黄龙_detail_9_bbbb2222.jpg"},
        {"assetId": "黄龙_detail_9_cccc3333", "role": "related", "caption": "", "fileName": "黄龙_detail_9_cccc3333.jpg"},
        {"assetId": "黄龙_detail_9_dddd4444", "role": "related", "caption": "争艳池彩池群", "fileName": "黄龙_detail_9_dddd4444.jpg"},
    ]


def test_homepage_placement_three_segment_contract():
    assets = _assets()
    out = place_homepage_assets_in_markdown(
        _BODY,
        assets,
        placements=[
            {
                "assetId": "黄龙_detail_9_bbbb2222",
                "placementType": "inline",
                "sectionSlug": "地质地貌",
            },
            {
                "assetId": "黄龙_detail_9_cccc3333",
                "placementType": "inline",
                "sectionSlug": "主要景点",
            },
            {
                "assetId": "黄龙_detail_9_dddd4444",
                "placementType": "inline",
                "sectionSlug": "主要景点",
            },
        ],
    )
    # 封面不进正文。
    assert "黄龙_cover_9_aaaa1111" not in out
    # 有原图注的两张进正文块级 figure（每章节最多 1 张，两个章节各一张）。
    assert out.count(":::figure") == 2
    assert 'layout="fullWidth"' in out and "wrapLeft" not in out and "wrapRight" not in out
    # 无图注的图不进正文，归入页尾相关图片 gallery。
    assert "## 相关图片" in out
    assert ':::gallery ids="黄龙_detail_9_cccc3333" layout="grid"' in out
    # roles 就地收敛。
    by_id = {a["assetId"]: a for a in assets}
    assert by_id["黄龙_cover_9_aaaa1111"]["role"] == "cover"
    assert by_id["黄龙_detail_9_bbbb2222"]["role"] == "inline"
    assert by_id["黄龙_detail_9_dddd4444"]["role"] == "inline"
    assert by_id["黄龙_detail_9_cccc3333"]["role"] == "related"


def test_homepage_placement_overflow_goes_related():
    """章节数不足时，多余的有图注图也进相关图片区，正文不堆图。"""
    assets = [
        {"assetId": f"黄龙_detail_9_e{i}", "role": "related", "caption": f"景点实景{i}", "fileName": f"e{i}.jpg"}
        for i in range(5)
    ]
    out = place_homepage_assets_in_markdown(
        _BODY,
        assets,
        placements=[
            {
                "assetId": "黄龙_detail_9_e0",
                "placementType": "inline",
                "sectionSlug": "地质地貌",
            },
            {
                "assetId": "黄龙_detail_9_e1",
                "placementType": "inline",
                "sectionSlug": "主要景点",
            },
            *[
                {
                    "assetId": f"黄龙_detail_9_e{index}",
                    "placementType": "inline",
                    "sectionSlug": "不存在章节",
                }
                for index in range(2, 5)
            ],
        ],
    )
    # 只有两个图片有可靠章节锚点；其余 3 张进入相关图片区。
    assert out.count(":::figure") == 2
    inline = [a for a in assets if a["role"] == "inline"]
    related = [a for a in assets if a["role"] == "related"]
    assert len(inline) == 2 and len(related) == 3
    ids_attr = [line for line in out.splitlines() if line.startswith(":::gallery")][0]
    for a in related:
        assert a["assetId"] in ids_attr


def _write_entity(tmp: Path, page_text: str) -> Path:
    obj = tmp / "entities" / "地点" / "景区" / "黄龙"
    obj.mkdir(parents=True, exist_ok=True)
    (obj / "page.md").write_text(page_text, encoding="utf-8")
    return obj


def test_structure_gate_passes_canonical_three_segment_page():
    assets = _assets()
    body = place_homepage_assets_in_markdown(_BODY, assets)
    page = f"---\ncoverImage: asset://黄龙_cover_9_aaaa1111\n---\n\n{body}"
    with tempfile.TemporaryDirectory() as td:
        obj = _write_entity(Path(td), page)
        issues = homepage_structure_issues(obj, {"assets": assets}, "黄龙")
    assert issues == [], issues


def test_structure_gate_flags_wrap_figure_and_body_gallery_and_leftover():
    page = (
        "---\ncoverImage: asset://黄龙_cover_9_aaaa1111\n---\n\n"
        "# 黄龙\n\n"
        ':::figure id="fig2" layout="wrapRight" caption="彩池"\nasset://黄龙_detail_9_bbbb2222\n:::\n\n'
        ':::gallery ids="黄龙_detail_9_cccc3333" layout="grid"\n:::\n\n'
        "## 地质\n\n[[IMG:fig_03]] 残留占位。\n"
    )
    with tempfile.TemporaryDirectory() as td:
        obj = _write_entity(Path(td), page)
        issues = homepage_structure_issues(obj, {"assets": _assets()}, "黄龙")
    text = "\n".join(issues)
    assert "fullWidth" in text, issues
    assert "相关图片" in text, issues
    assert "残留占位符" in text, issues


def test_structure_gate_flags_missing_frontmatter_cover_and_bad_roles():
    page = "# 黄龙\n\n正文。\n"
    assets = [
        {"assetId": "a", "role": "cover"},
        {"assetId": "b", "role": "cover"},
        {"assetId": "c", "role": "gallery"},
    ]
    with tempfile.TemporaryDirectory() as td:
        obj = _write_entity(Path(td), page)
        issues = homepage_structure_issues(obj, {"assets": assets}, "黄龙")
    text = "\n".join(issues)
    assert "frontmatter" in text, issues
    assert "恰好一个 role=cover" in text, issues
    assert "非法值 gallery" in text, issues


def test_caption_gate_allows_empty_related_caption():
    assets = [
        {"assetId": "a", "role": "related", "caption": "", "fileName": "x.jpg"},
        {"assetId": "b", "role": "inline", "caption": "", "fileName": "y.jpg"},
    ]
    issues = caption_semantic_issues(assets, label="黄龙")
    text = "\n".join(issues)
    assert "asset a" not in text, issues
    assert "asset b" in text, issues


def test_asset_wiki_filename_precise_match_ignores_entity_name_pollution():
    """caption 回填精确匹配契约（武侯祠全量'武侯祠过厅'根因）。

    资产原始 wiki 文件名必须从 authorizationProof/sourceUrl 的 `File:` 段还原，
    绝不使用批次路径（sources/武侯祠__encyclopedia__x/...）做子串匹配——
    路径含实体名会让所有资产误命中 `武侯祠.jpg` 的图注。
    """
    asset = {
        "assetId": "武侯祠_detail_1_92367e20",
        "fileName": "武侯祠_detail_1_92367e20.jpg",
        "sourceAssetRef": "sources/武侯祠__encyclopedia__fbd8d2d4/assets/002_home_wiki_2.jpg",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:35911-Chengdu_(49067699918).jpg",
    }
    # 还原的是 File: 段的原始文件名，而不是批次路径里的实体名文件。
    assert _asset_wiki_filename(asset) == "35911-chengdu (49067699918).jpg"

    placements = {
        _normalize_wiki_filename("武侯祠.jpg"): "武侯祠过厅",
        _normalize_wiki_filename("35911-Chengdu_(49067699918).jpg"): "汉昭烈庙大门",
    }
    assert placements[_asset_wiki_filename(asset)] == "汉昭烈庙大门"

    # URL 编码/下划线-空格归一：MediaWiki 等价形式必须命中同一 key。
    quoted = {
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:%E6%AD%A6%E4%BE%AF%E7%A5%A0.jpg",
    }
    assert _asset_wiki_filename(quoted) == "武侯祠.jpg"
    assert _normalize_wiki_filename("武侯祠.jpg") == _asset_wiki_filename(quoted)

    # 物化层必须复用媒体层的唯一归一实现，不能再维护一套文件名匹配规则。
    assert release_normalize_wiki_filename("35911-Chengdu_(49067699918).jpg") == (
        _normalize_wiki_filename("35911-Chengdu_(49067699918).jpg")
    )
    assert release_asset_wiki_filename(quoted) == _asset_wiki_filename(quoted)

    # 无任何 File:/URL 线索时返回空——宁可不回填也不模糊命中。
    assert _asset_wiki_filename({"sourceAssetRef": "sources/武侯祠__x/assets/001.jpg"}) == ""


def test_placement_map_like_blocks_locator_map_from_homepage_assets():
    """地图/位置图（locatorMap 或 coverCandidateRank<0）不可做封面也不进正文。"""
    assert _placement_is_map_like({"placementType": "locatorMap"})
    assert _placement_is_map_like({"coverCandidateRank": -1})
    assert not _placement_is_map_like({"placementType": "inline", "coverCandidateRank": 2})
    assert not _placement_is_map_like({})


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"homepage md contract tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
