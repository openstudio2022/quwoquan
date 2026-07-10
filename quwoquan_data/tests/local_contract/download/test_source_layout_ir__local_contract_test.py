"""统一结构化 IR（source.layout.json）local_contract。

覆盖百科主页结构化计划的第一工作包（wiki-layout-ir）：

- Wiki wikitext 前端：表格降维为 listItem 事实句 + 行图连续 figure（共享 groupId）、
  `<gallery>` 宫格降维为连续 figure（保序、仅原图注）、infobox 图为封面候选、
  地图/定位图 coverCandidateRank=-1 禁封面。
- 百度/搜狗 HTML 前端：章节/段落/basic-info factRow 进同一 IR schema，
  图片不采只记存在性证据；解析失败结构化 reject，禁止静默降级纯文本。
- write_source_unit 落盘 source.layout.json + manifest layoutSummary。
- caption 仅原图注：无原图注的 figure caption 必须为空串。
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

from _common.source_layout import (  # noqa: E402
    SOURCE_LAYOUT_FILE,
    cover_candidates,
    layout_figures,
    read_source_layout,
)
from _common.wiki_wikitext import parse_wikitext_layout, parse_wikitext_placements  # noqa: E402
from download.baike_layout import parse_baike_layout, render_layout_markdown  # noqa: E402


# 黄龙式样本：infobox（含地图）+ 正文 + 景点表（行图）+ 图库宫格 + 无图注图。
_HUANGLONG_WIKITEXT = """{{Infobox 景区
| name = 黄龙风景名胜区
| image = Huanglong_Wucai_Pond.jpg
| caption = 黄龙五彩池
| map = Sichuan_location_map.png
| 地址 = 四川省阿坝州松潘县
| 海拔 = 3100-3600 米
}}

'''黄龙风景名胜区'''位于[[四川省]][[松潘县]]，以彩池、雪山、峡谷、森林闻名。<ref>来源</ref>

== 主要景点 ==

黄龙沟内主要景点自下而上分布，彩池群与钙华滩流构成核心景观。

{| class="wikitable"
|+ 主要景点列表
! 景点 !! 海拔 !! 池子数量
|-
| [[迎宾池]] || 3230米 || 约350个
|-
| 飞瀑流辉 [[File:Huanglong_Feipu.jpg|thumb|飞瀑流辉]] || 3245米 || —
|-
| 五彩池 || 3576米 || 693个
|}

== 图库 ==

<gallery>
File:Huanglong1.jpg|争艳池
File:Huanglong2.jpg
File:Huanglong3.jpg|石塔镇海
</gallery>
"""


def test_wikitext_table_degrades_to_list_items_with_row_figures() -> None:
    layout = parse_wikitext_layout(_HUANGLONG_WIKITEXT, title="黄龙风景名胜区")
    assert layout["parseStatus"] == "ok"
    items = [b for b in layout["blocks"] if b["type"] == "listItem" and b.get("origin") == "wikitable"]
    assert len(items) == 3
    assert any("迎宾池" in b["text"] and "3230米" in b["text"] and "约350个" in b["text"] for b in items)
    # 行图挂靠为相邻 figure，共享表格 groupId。
    table = layout["tables"][0]
    assert table["mappingDecision"] == "orderedList"
    row_figures = [f for f in layout_figures(layout) if f["groupId"] == table["tableId"]]
    assert [f["fileTitle"] for f in row_figures] == ["Huanglong_Feipu.jpg"]
    assert row_figures[0]["caption"] == "飞瀑流辉"


_ORDINAL_TABLE_WIKITEXT = """== 黄龙沟景区 ==

{| class="wikitable"
! 序号 !! 景点名 !! 海拔高度
|-
| 1 || 迎宾池 [[File:黃龍-迎賓池.JPG|80px]] || 3230米
|-
| 2 || 飞瀑流辉 [[File:HuangLong_Feipu2.jpg|80px]] || 3245米
|-
| 3 || [[File:HuangLong_NoName.jpg|80px]] || 3260米
|}
"""


def test_wikitext_table_row_figure_caption_skips_bare_ordinal_subject() -> None:
    """行图 caption 兜底禁止用纯序号首列（黄龙 '1'..'14' 假图注根因）。

    - 有语义列（景点名）时：caption = 景点名；
    - 整行只剩序号/数字时：caption 必须为空（无图注不补）。
    """
    layout = parse_wikitext_layout(_ORDINAL_TABLE_WIKITEXT, title="黄龙风景名胜区")
    assert layout["parseStatus"] == "ok"
    figures = [f for f in layout_figures(layout) if f["placementType"] == "groupMember"]
    by_file = {f["fileTitle"]: f["caption"] for f in figures}
    assert by_file["黃龍-迎賓池.JPG"] == "迎宾池"
    assert by_file["HuangLong_Feipu2.jpg"] == "飞瀑流辉"
    # 第三行除序号与海拔外无语义文字列；海拔 3260米 含单位不算纯序号，作为原文事实兜底可接受，
    # 但绝不允许出现 '3' 这类纯序号 caption。
    assert by_file["HuangLong_NoName.jpg"] != "3"
    assert all(not f["caption"].strip().isdigit() for f in figures)


def test_wikitext_gallery_degrades_to_consecutive_figures_with_original_captions() -> None:
    layout = parse_wikitext_layout(_HUANGLONG_WIKITEXT)
    gallery_figures = [
        f for f in layout_figures(layout) if f["placementType"] == "groupMember" and f["groupId"].startswith("gal-")
    ]
    assert [f["fileTitle"] for f in gallery_figures] == [
        "Huanglong1.jpg",
        "Huanglong2.jpg",
        "Huanglong3.jpg",
    ]
    # 共享同一 groupId、保原顺序（sourceOrder 单调递增）。
    assert len({f["groupId"] for f in gallery_figures}) == 1
    orders = [f["sourceOrder"] for f in gallery_figures]
    assert orders == sorted(orders)
    # caption 仅原图注：无原图注必须为空串，禁止人为补注。
    assert [f["caption"] for f in gallery_figures] == ["争艳池", "", "石塔镇海"]


def test_wikitext_infobox_yields_cover_candidate_and_blocks_locator_map() -> None:
    layout = parse_wikitext_layout(_HUANGLONG_WIKITEXT)
    figures = layout_figures(layout)
    lead = [f for f in figures if f["placementType"] == "infoboxLead"]
    assert lead and lead[0]["fileTitle"] == "Huanglong_Wucai_Pond.jpg"
    assert lead[0]["caption"] == "黄龙五彩池"
    assert lead[0]["coverCandidateRank"] == 1
    maps = [f for f in figures if f["placementType"] == "locatorMap"]
    assert maps and maps[0]["coverCandidateRank"] == -1
    # 封面候选：infobox 实景图第一，地图绝不出现。
    candidates = cover_candidates(layout)
    assert candidates[0]["fileTitle"] == "Huanglong_Wucai_Pond.jpg"
    assert all(not c["isMapLike"] for c in candidates)
    # 信息框键值行进 factRow。
    facts = {b["key"]: b["value"] for b in layout["blocks"] if b["type"] == "factRow"}
    assert facts.get("地址") == "四川省阿坝州松潘县"


def test_wikitext_placements_view_includes_gallery_and_table_figures() -> None:
    _outline, placements = parse_wikitext_placements(_HUANGLONG_WIKITEXT, min_section_body_chars=10)
    names = [p["fileName"] for p in placements]
    # 旧实现只识别行内 [[File:]]，图库/表格行图整组丢失；新口径必须齐全。
    for expected in ("Huanglong_Feipu.jpg", "Huanglong1.jpg", "Huanglong2.jpg", "Huanglong3.jpg"):
        assert expected in names, f"missing {expected} in placements"
    by_name = {p["fileName"]: p for p in placements}
    assert by_name["Huanglong1.jpg"]["placementType"] == "groupMember"
    assert by_name["Sichuan_location_map.png"]["coverCandidateRank"] == -1


_BAIKE_HTML = """<!DOCTYPE html>
<html><head><title>西岭雪山_百度百科</title></head><body>
<div class="navbar">百度首页 登录</div>
<h1>西岭雪山</h1>
<div class="basic-info cmn-clearfix"><dl>
<dt>中文名</dt><dd>西岭雪山</dd>
<dt>地理位置</dt><dd>四川省成都市大邑县</dd>
<dt>景区级别</dt><dd>AAAA级</dd>
</dl></div>
<div class="para">西岭雪山位于四川省成都市大邑县境内，属世界自然遗产大熊猫栖息地。<sup>[1]</sup></div>
<h2>地理环境<span>编辑</span></h2>
<div class="para">景区最高峰苗基岭海拔5364米，为成都第一峰，山顶终年积雪。</div>
<div class="para"><img src="https://baike.example/xiling.jpg">冬季滑雪场面积广阔。</div>
<div class="album">图册推荐区不应进入正文</div>
</body></html>"""


def test_baike_html_parses_sections_facts_and_records_image_evidence() -> None:
    layout = parse_baike_layout(
        _BAIKE_HTML.encode("utf-8"),
        source_kind="home_baidu_baike",
        extractor="baidu_baike_html",
    )
    assert layout["parseStatus"] == "ok"
    assert layout["title"] == "西岭雪山"
    facts = {b["key"]: b["value"] for b in layout["blocks"] if b["type"] == "factRow"}
    assert facts.get("地理位置") == "四川省成都市大邑县"
    headings = [b["text"] for b in layout["blocks"] if b["type"] == "heading"]
    assert "地理环境" in headings
    assert all("编辑" not in h for h in headings)
    paragraphs = [b["text"] for b in layout["blocks"] if b["type"] == "paragraph"]
    assert any("苗基岭海拔5364米" in p for p in paragraphs)
    assert all("图册推荐区" not in p for p in paragraphs)
    assert all("[1]" not in p for p in paragraphs)
    # 版权约束：图片不采，只记录存在性证据供质量门判断。
    assert layout["figureCount"] == 0
    assert layout["imageEvidence"]["imageCount"] >= 1
    assert layout["imageEvidence"]["imagesUsable"] is False
    # 从 IR 渲染的 source 正文保留结构语义。
    text = render_layout_markdown(layout)
    assert "## 地理环境" in text
    assert "- 地理位置：四川省成都市大邑县" in text


def test_baike_html_parse_failure_is_structured_reject_not_plaintext_fallback() -> None:
    layout = parse_baike_layout(
        b"<html><body><script>window.location.href='/verify'</script></body></html>",
        source_kind="home_baidu_baike",
        extractor="baidu_baike_html",
    )
    assert layout["parseStatus"] == "rejected"
    assert layout["rejectReason"] == "baike_structure_not_found"
    assert layout["blocks"] == []
    # fetch 层的正文产物必须为空（不允许把验证码壳当正文）。
    import download.fetch as fetch_mod

    text = fetch_mod._baike_html_plaintext(
        "https://baike.baidu.com/item/x",
        extractor="baidu_baike_html",
        html_bytes=b"<html><body><script>x</script></body></html>",
    )
    assert text == ""


def test_write_source_unit_persists_layout_and_manifest_summary(monkeypatch) -> None:
    from _common import paths as paths_mod
    from _common.source_unit import write_source_unit

    layout = parse_wikitext_layout(_HUANGLONG_WIKITEXT, title="黄龙风景名胜区")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(root))
        # batches root 依赖环境；直接用非批次对象目录走 source_unit_dir 回退路径。
        object_dir = root / "entities/地点/景区/黄龙风景名胜区"
        object_dir.mkdir(parents=True)
        manifest = write_source_unit(
            object_dir,
            ordinal=1,
            source_id="home_wikipedia",
            source_md="---\nsourceId: home_wikipedia\n---\n\n黄龙正文",
            url="https://zh.wikipedia.org/wiki/黄龙风景名胜区",
            title="黄龙风景名胜区",
            layout=layout,
        )
        summary = manifest["layoutSummary"]
        assert summary["parseStatus"] == "ok"
        assert summary["figureCount"] == layout["figureCount"]
        assert summary["tableCount"] == 1
        units = list(object_dir.rglob(SOURCE_LAYOUT_FILE))
        assert units, "source.layout.json missing on disk"
        persisted = read_source_layout(units[0].parent)
        assert persisted is not None
        assert persisted["schemaVersion"] == "quwoquan_data.source_layout/1"
        assert [b["type"] for b in persisted["blocks"]] == [b["type"] for b in layout["blocks"]]


def test_render_source_markdown_keeps_in_place_placeholders_and_original_captions() -> None:
    """source.md 底稿忠实还原：图片原位占位；仅原图注（无图注不补行）；宫格为连续单图占位。"""
    from _common.source_layout import render_source_markdown

    layout = parse_wikitext_layout(_HUANGLONG_WIKITEXT, title="黄龙风景名胜区")
    text = render_source_markdown(layout)
    # 章节结构保留。
    assert "## 主要景点" in text
    # 表格降维事实句以列表项呈现。
    assert "- 迎宾池：海拔 3230米，池子数量 约350个。" in text
    # 占位编号 = sourceOrder+1，与 plan imageUrls 的 placeholderId 同口径。
    assert "![黄龙五彩池](asset://source-inline-001)" in text
    # 有原图注：占位块内带一行图注。
    assert ":::figure\n![黄龙五彩池](asset://source-inline-001)\n黄龙五彩池\n:::" in text
    # 无原图注（Huanglong2.jpg，sourceOrder=4）：不补图注行。
    assert ":::figure\n![](asset://source-inline-005)\n:::" in text
    # 宫格三张为连续单图占位（无 figuregroup 第二套语法）。
    assert ":::figuregroup" not in text
    assert text.index("source-inline-004") < text.index("source-inline-005") < text.index("source-inline-006")


def test_bind_prunes_unbound_placeholder_blocks_without_caption_line() -> None:
    """未绑定占位整块剥离：有图注与无图注两种块形态都必须被剥离，绑定的保留。"""
    from _common.source_unit import bind_inline_source_placeholders

    text = (
        "正文开头。\n\n"
        ":::figure\n![黄龙五彩池](asset://source-inline-001)\n黄龙五彩池\n:::\n\n"
        ":::figure\n![](asset://source-inline-002)\n:::\n\n"
        "正文结尾。"
    )
    bound = bind_inline_source_placeholders(text, {"source-inline-001": "001_001"})
    assert "asset://001_001" in bound
    assert "source-inline-002" not in bound
    assert ":::figure\n![](" not in bound
    assert "正文开头。" in bound and "正文结尾。" in bound


def test_download_source_unit_images_group_quota_exempts_gallery_members(monkeypatch) -> None:
    """组配额：宫格/表格行图（groupId）成组保留不受散图 cap 截断；散图仍按 cap。"""
    import download.handler_images as hi

    jpeg = b"\xff\xd8\xff\xe0" + b"0" * 128 + b"\xff\xd9"
    # handler_bridge 会优先取 download.handler facade 上的原函数，绕过本测试对
    # hi.* 的 monkeypatch（套件内其它测试 import facade 后即触发）；强制无 facade，
    # 让 bridge 走 fallback（= 本测试注入的 mock）。
    monkeypatch.setattr(hi.handler_bridge, "_facade", lambda: None)
    monkeypatch.setattr(hi, "SOURCE_UNIT_MAX_IMAGES_PER_SOURCE", 2)
    monkeypatch.setattr(hi, "validate_image_rights", lambda spec, vertical: [])
    monkeypatch.setattr(hi, "_cached_source_image_payload", lambda *a, **k: None)
    monkeypatch.setattr(
        hi,
        "fetch_image_payload",
        lambda url, max_bytes=0: {
            "bytes": jpeg + url.encode("utf-8"),
            "ext": ".jpg",
            "url": url,
            "requestedUrl": url,
            "contentType": "image/jpeg",
        },
    )
    monkeypatch.setattr(hi, "image_dimensions", lambda b: (1200, 800))
    monkeypatch.setattr(hi, "pixel_size_issue", lambda w, h, asset_id: None)
    monkeypatch.setattr(
        hi,
        "_write_image_check_temp_file",
        lambda task_id, batch_id, subdir=None, payload=None: Path(tempfile.mkstemp()[1]),
    )

    class _Ok:
        blocks_image_publish = False
        status = "approved"
        reasons: tuple = ()

    monkeypatch.setattr(hi, "_assess_source_image", lambda temp, spec, task_id=None, batch_id=None: _Ok())
    monkeypatch.setattr(hi, "_cleanup_image_check_temp_file", lambda p: None)
    monkeypatch.setattr(hi, "relevance_issue", lambda relevance, entity_id, asset_id: None)
    monkeypatch.setattr(hi, "dedupe_image_payloads", lambda images: (images, []))

    def _img(idx: int, group: str = "") -> dict:
        return {
            "url": f"https://img.example/{idx}.jpg",
            "caption": f"图{idx}",
            "groupId": group,
            "sourceOrder": idx,
        }

    # 2 散图（cap=2）+ 1 散图溢出 + 4 宫格组图（应全保留）。
    image_urls = [_img(1), _img(2), _img(3)] + [_img(i, group="gal-001") for i in range(4, 8)]
    images, _issues, funnel = hi._download_source_unit_images(
        {
            "source_id": "home_wikipedia",
            "imageUrls": image_urls,
            "license": "CC BY-SA 4.0",
            "credit": "wiki",
            "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
            "url": "https://zh.wikipedia.org/wiki/黄龙风景名胜区",
        },
        task_id="t",
        batch_id="b",
        entity_id="黄龙风景名胜区",
        object_dir=Path(tempfile.mkdtemp(prefix="grp_quota_")),
        ordinal=1,
        vertical="travel",
    )
    kept_urls = [img["url"] for img in images]
    # 散图只留 cap=2 张；第 3 张散图被截断。
    assert "https://img.example/1.jpg" in kept_urls
    assert "https://img.example/2.jpg" in kept_urls
    assert "https://img.example/3.jpg" not in kept_urls
    # 宫格组图 4 张全保留（豁免散图 cap）。
    for idx in range(4, 8):
        assert f"https://img.example/{idx}.jpg" in kept_urls
    assert funnel["quotaMode"] == "group_aware"
    assert images[-1]["groupId"] == "gal-001"


def test_write_source_unit_asset_entries_carry_cover_candidate_fields(monkeypatch) -> None:
    """assets/index.json 携带封面候选语义：placementType/rank/isMapLike/代表性/视觉主体。"""
    from _common.source_unit import write_source_unit

    jpeg = b"\xff\xd8\xff\xe0" + b"0" * 200 + b"\xff\xd9"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(root))
        object_dir = root / "entities/地点/景区/黄龙风景名胜区"
        object_dir.mkdir(parents=True)
        manifest = write_source_unit(
            object_dir,
            ordinal=1,
            source_id="home_wikipedia",
            source_md=(
                "---\nsourceId: home_wikipedia\n---\n\n"
                ":::figure\n![黄龙五彩池](asset://source-inline-001)\n黄龙五彩池\n:::\n\n正文。"
            ),
            url="https://zh.wikipedia.org/wiki/黄龙风景名胜区",
            title="黄龙风景名胜区",
            images=[
                {
                    "bytes": jpeg,
                    "ext": ".jpg",
                    "url": "https://upload.wikimedia.org/a.jpg",
                    "caption": "黄龙五彩池",
                    "placeholderId": "source-inline-001",
                    "placementType": "infoboxLead",
                    "coverCandidateRank": 1,
                    "isMapLike": False,
                    "groupId": "",
                    "sectionSlug": "",
                    "sourceOrder": 0,
                },
                {
                    "bytes": jpeg + b"2",
                    "ext": ".png",
                    "url": "https://upload.wikimedia.org/map.png",
                    "caption": "",
                    "placementType": "locatorMap",
                    "coverCandidateRank": -1,
                    "isMapLike": True,
                },
            ],
            build_variants=False,
        )
        entries = manifest["assets"] if "assets" in manifest else []
        if not entries:
            import json

            index = json.loads(
                next(object_dir.rglob("assets/index.json")).read_text(encoding="utf-8")
            )
            entries = index["assets"]
        lead = entries[0]
        assert lead["placementType"] == "infoboxLead"
        assert lead["coverCandidateRank"] == 1
        assert lead["isMapLike"] is False
        assert lead["isRepresentativeVisual"] is True
        assert lead["visualSubject"] == "黄龙五彩池"
        map_entry = entries[1]
        assert map_entry["coverCandidateRank"] == -1
        assert map_entry["isMapLike"] is True
        assert map_entry["isRepresentativeVisual"] is False
        # 占位绑定后 source.md 中占位替换为真实 sourceAssetId。
        bound = next(object_dir.rglob("source.md")).read_text(encoding="utf-8")
        assert "asset://001_001" in bound
        assert "source-inline-001" not in bound


def _run() -> None:
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))


if __name__ == "__main__":
    _run()
