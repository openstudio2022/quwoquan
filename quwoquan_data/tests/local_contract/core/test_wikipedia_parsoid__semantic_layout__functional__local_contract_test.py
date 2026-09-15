# spec_ref: user-scoped exact-revision Wikipedia acquisition and semantic IR acceptance
"""Offline fixtures for exact-revision Parsoid semantic parsing."""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

from core.wiki_parsoid import build_semantic_document, parse_parsoid_layout, verify_semantic_document  # noqa: E402
from core.wiki_wikitext import parse_wikitext_layout  # noqa: E402
from generated.semantic_document import CAPABILITY_IDS, ProcessingDisposition, ValidationCode, validate_envelope  # noqa: E402


def test_parsoid_allowlist_preserves_semantics_and_unknown_visible_content() -> None:
    html = """<html><body>
    <meta property="mw:pageId" content="7"><h1>条目</h1>
    <p>正文<a href="./目标">链接</a><strong>重点</strong><br>下一行<sup class="reference"><a href="#cite_note-1">[1]</a></sup></p>
    <ul><li>项目一<ul><li>嵌套项</li></ul></li></ul>
    <dl><dt>术语</dt><dd>定义</dd></dl>
    <aside class="infobox"><table><tr><th>地点</th><td>杭州</td></tr></table></aside>
    <figure><img resource="./File:Lake.jpg"><figcaption>湖景</figcaption></figure>
    <blockquote>不能识别但必须保留的引文</blockquote>
    <div class="navbox">导航噪声</div>
    </body></html>"""
    layout = parse_parsoid_layout(html, title="条目", revision=123)
    assert layout["captureCoverage"] == {"wikitext": True, "parsoidHtml": True, "revisionSpecific": True}
    assert layout["sourceProfile"]["revision"] == 123
    assert any(block["type"] == "paragraph" and block["hardbreakCount"] == 1 for block in layout["blocks"])
    paragraph = next(block for block in layout["blocks"] if block["type"] == "paragraph")
    assert any(run["type"] == "link" and run["href"] == "./目标" for run in paragraph["inlines"])
    assert any(block["type"] == "listItem" and block.get("depth") == 1 for block in layout["blocks"])
    assert any(block["type"] == "factRow" and block["key"] == "地点" for block in layout["blocks"])
    assert any(block["type"] == "figure" and block["caption"] == "湖景" for block in layout["blocks"])
    assert any(block["type"] == "unsupportedOpaque" and "必须保留" in block["text"] for block in layout["blocks"])
    assert any(row["disposition"] == ProcessingDisposition.DROPPED_NOISE.value for row in layout["dispositions"])
    assert {row["disposition"] for row in layout["dispositions"]} <= {item.value for item in ProcessingDisposition}
    assert layout["semanticParseCoverage"]["status"] == "partial"


def test_parsoid_table_expands_rowspan_colspan_and_detects_grouped_directory() -> None:
    html = """<table><caption>景点名录</caption><tr><th>区域</th><th>名称</th><th>说明</th></tr>
    <tr><td rowspan="2">湖区</td><td>A</td><td>甲</td></tr>
    <tr><td colspan="2">B 合并说明</td></tr><tr><td>山区</td><td>C</td><td>丙</td></tr></table>"""
    layout = parse_parsoid_layout(html, revision=9)
    table = next(block for block in layout["blocks"] if block["type"] == "table")
    assert table["groupedDirectory"] is True
    assert len(table["logicalGrid"]) == 4
    assert all(len(row) == 3 for row in table["logicalGrid"])
    assert table["logicalGrid"][1][0]["rowspan"] == 2
    assert table["logicalGrid"][2][0]["covered"] is True
    assert table["logicalGrid"][2][1]["colspan"] == 2
    assert layout["tables"][0]["mappingDecision"] == "groupedDirectory"


def test_legacy_wikitext_complex_table_stays_table_not_fact_sentences() -> None:
    layout = parse_wikitext_layout("""{| class=wikitable
! 分组 !! 名称
|-
| rowspan=2 | 湖区 || 甲
|-
| 乙
|}""")
    assert any(block["type"] == "table" for block in layout["blocks"])
    assert not any(block["type"] == "listItem" and block.get("origin") == "wikitable" for block in layout["blocks"])
    assert layout["tables"][0]["sourceComplexStructure"] is True


def test_semantic_envelope_validates_and_opaque_raw_slice_roundtrips() -> None:
    opaque = '<custom-panel data-x="原值"><b>未知可见内容</b></custom-panel>'
    html = f"<h2>章节</h2><p>正文</p>{opaque}"
    layout = parse_parsoid_layout(html, revision=94349972)
    block = next(row for row in layout["blocks"] if row["type"] == "unsupportedOpaque")
    assert block["rawSlice"] == opaque
    import hashlib
    assert block["rawSliceFingerprint"] == hashlib.sha256(opaque.encode()).hexdigest()
    semantic = build_semantic_document(layout, html, revision=94349972)
    assert validate_envelope(semantic, CAPABILITY_IDS).code == ValidationCode.OK
    assert all(verify_semantic_document(semantic).values())
    import json
    canonical = {key: value for key, value in semantic.items() if key != "canonicalDigest"}
    recomputed = hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert semantic["canonicalDigest"] == recomputed
    semantic_material = {key: value for key, value in semantic.items() if key not in {"semanticFingerprint", "canonicalDigest"}}
    assert semantic["semanticFingerprint"] == hashlib.sha256(json.dumps(semantic_material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    node = next(row for row in semantic["nodes"] if row["kind"] == "unsupportedOpaque")
    assert node["rawSlice"] == opaque
    assert node["rawSliceFingerprint"] == block["rawSliceFingerprint"]
    assert layout["semanticParseCoverage"]["publicationDecision"] == "block"
    assert layout["semanticParseCoverage"]["homepageComplete"] is False
    coverage = layout["semanticParseCoverage"]
    assert coverage["allVisibleClassified"] is True
    assert coverage["visibleCandidateNodes"] == coverage["visibleClassifiedNodes"]
    assert coverage["classifiedNodeTotal"] == sum(coverage["dispositionCounts"].values())


def test_dynasty_people_table_projects_lossless_grouped_directory() -> None:
    html = """<table><tr><th>王朝</th><th>入祀人物</th><th>编号</th></tr>
    <tr><td rowspan="2">汉</td><td>刘邦</td><td>1</td></tr>
    <tr><td>刘秀</td><td>2</td></tr>
    <tr><td>唐</td><td>李世民</td><td>3</td></tr></table>"""
    layout = parse_parsoid_layout(html, revision=94349972)
    semantic = build_semantic_document(layout, html, revision=94349972)
    directory = next(row for row in semantic["nodes"] if row["kind"] == "groupedDirectory")
    assert [(group["label"], [member["text"] for member in group["members"]]) for group in directory["attributes"]["groups"]] == [("汉", ["刘邦", "刘秀"]), ("唐", ["李世民"])]
    assert [member["order"] for group in directory["attributes"]["groups"] for member in group["members"]] == [0, 1, 2]
    table = next(row for row in semantic["nodes"] if row["kind"] == "table")
    assert len(table["attributes"]["logicalGrid"]) == 4
    assert validate_envelope(semantic, CAPABILITY_IDS).code == ValidationCode.OK



def test_inline_conservation_across_heading_list_definition_table_and_fact_row() -> None:
    html = """<h2><a href="#part">标题</a></h2><ul><li><a href="./甲">甲</a><sub>下</sub></li></ul>
    <dl><dt><abbr title="术语全称">术语</abbr></dt><dd><a href="https://example.test">定义</a></dd></dl>
    <aside class="infobox"><table><tr><th><a href="./键">键</a></th><td><code>值</code></td></tr></table></aside>
    <table><caption><a href="./目录">目录</a></caption><tr><th scope="col">组</th><th>人</th></tr>
    <tr><td rowspan="2" data-sort-value="1"><a href="./汉">汉</a></td><td><a href="./刘邦">刘邦</a></td></tr>
    <tr><td><a href="./刘秀">刘秀</a></td></tr></table>"""
    layout = parse_parsoid_layout(html, revision=1)
    heading = next(row for row in layout["blocks"] if row["type"] == "heading")
    item = next(row for row in layout["blocks"] if row["type"] == "listItem" and row.get("listKind") == "unordered")
    definition = next(row for row in layout["blocks"] if row.get("listKind") == "definition")
    fact = next(row for row in layout["blocks"] if row["type"] == "factRow")
    table = next(row for row in layout["blocks"] if row["type"] == "table")
    assert heading["inlines"][0]["linkType"] == "section"
    assert any(run.get("href") == "./甲" for run in item["inlines"])
    assert definition["termInlines"][0]["marks"] == ["abbr"]
    assert definition["definitionInlines"][0]["linkType"] == "external"
    assert any("inlineCode" in run.get("marks", []) for run in fact["valueInlines"])
    cell = table["logicalGrid"][1][0]
    assert cell["rowspan"] == 2 and cell["sortKey"] == "1" and cell["sourceAnchor"]["selector"] == "td"
    assert cell["inlines"][0]["href"] == "./汉"
    semantic = build_semantic_document(layout, html, revision=1)
    directory = next(row for row in semantic["nodes"] if row["kind"] == "groupedDirectory")
    assert directory["attributes"]["groups"][0]["label"] == "汉"
    assert directory["attributes"]["groups"][0]["members"][0]["text"] == "刘邦"


def test_named_reference_graph_preserves_reuse_backlinks_and_definition_links() -> None:
    html = """<p>甲<sup class="mw-ref reference" id="cite_ref-n_1-0" typeof="mw:Extension/ref" data-mw='{"name":"ref","attrs":{"name":"n"},"body":{"id":"mw-reference-text-cite_note-n-1"}}'><a href="#cite_note-n-1">[1]</a></sup>
    乙<sup class="mw-ref reference" id="cite_ref-n_1-1" typeof="mw:Extension/ref" data-mw='{"name":"ref","attrs":{"name":"n"}}'><a href="#cite_note-n-1">[1]</a></sup></p>
    <ol class="references" typeof="mw:Extension/references"><li id="cite_note-n-1"><span class="mw-cite-backlink"><a href="#cite_ref-n_1-0">1</a><a href="#cite_ref-n_1-1">2</a></span><span class="reference-text">见<a href="https://example.test/source">来源</a></span></li></ol>"""
    layout = parse_parsoid_layout(html, revision=1)
    paragraph = next(row for row in layout["blocks"] if row["type"] == "paragraph")
    refs = [run for run in paragraph["inlines"] if run["type"] == "footnoteRef"]
    assert len(refs) == 2 and {run["refId"] for run in refs} == {"cite_note-n-1"}
    definition = next(row for row in layout["blocks"] if row["type"] == "footnoteDefinition")
    assert definition["backlinks"] == ["#cite_ref-n_1-0", "#cite_ref-n_1-1"]
    assert [run["href"] for run in definition["inlines"] if run["type"] == "link"] == ["https://example.test/source"]
    assert next(row for row in layout["blocks"] if row["type"] == "footnoteList")["definitionIds"] == ["cite_note-n-1"]


def test_infobox_lead_locator_and_gallery_keep_source_order_without_duplicates() -> None:
    html = """<table class="infobox"><tr><td class="infobox-image"><a href="./File:Lead.jpg"><img resource="./File:Lead.jpg" src="lead.jpg" srcset="lead2.jpg 2x" alt="主图"></a></td></tr>
    <tr><td class="infobox-full-data"><a class="mw-kartographer-map" href="./地图"><img src="map.png"></a></td></tr></table>
    <figure><a href="./File:Body.jpg"><img resource="./File:Body.jpg" src="body.jpg"></a><figcaption>正文图</figcaption></figure>
    <ul class="gallery"><li><figure><a href="./File:G.jpg"><img resource="./File:G.jpg" src="g.jpg"></a><figcaption>宫格图</figcaption></figure></li></ul>"""
    layout = parse_parsoid_layout(html, revision=1)
    figures = [row for row in layout["blocks"] if row["type"] == "figure"]
    assert [row["placementType"] for row in figures] == ["infoboxLead", "locatorMap", "inline", "groupMember"]
    assert [row["sourceOrder"] for row in figures] == [0, 1, 2, 3]
    assert len({row["sourceAnchor"]["start"] for row in figures}) == 4
    assert figures[0]["resource"] == "./File:Lead.jpg" and figures[0]["srcset"] == "lead2.jpg 2x"
    assert figures[1]["coverCandidateRank"] == -1


def _load_mediawiki():
    import importlib.util
    root = DATA_ROOT.parent
    path = root / ".agents/skills/content-production/scripts/clients/mediawiki.py"
    spec = importlib.util.spec_from_file_location("mediawiki_rights_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_commons_exact_titles_capture_rights_and_fail_closed() -> None:
    request = {"fileTitles": ["File:One.jpg", "File:Missing.jpg"], "limit": 2}
    from urllib.parse import parse_qs, urlsplit
    import json
    class CommonsClient:
        def get(self, url, **kwargs):
            query = parse_qs(urlsplit(url).query)
            assert query["titles"] == ["File:One.jpg|File:Missing.jpg"]
            assert query["iiprop"] == ["url|sha1|size|mime|extmetadata|user|timestamp"]
            return json.dumps({"query":{"pages":[
                {"pageid":1,"title":"File:One.jpg","imageinfo":[{"url":"https://upload.wikimedia.org/one.jpg","descriptionurl":"https://commons.wikimedia.org/wiki/File:One.jpg","sha1":"ABC","size":10,"mime":"image/jpeg","user":"Uploader","timestamp":"2020-01-01T00:00:00Z","extmetadata":{"Artist":{"value":"<b>Alice</b>"},"LicenseShortName":{"value":"CC BY-SA 4.0"},"LicenseUrl":{"value":"https://creativecommons.org/licenses/by-sa/4.0/"},"Credit":{"value":"Own work"}}}]},
                {"title":"File:Missing.jpg","missing":True}
            ]}}).encode()
    body = _load_mediawiki().commons_fetch(request, CommonsClient(), "image")
    rows, evidence = _load_mediawiki().commons_parse(body, request, "image")
    captured = next(row for row in rows if row["disposition"] == "captured")
    missing = next(row for row in rows if row["disposition"] == "commons_missing")
    assert captured["creator"] == "Alice" and captured["license"] == "CC BY-SA 4.0"
    assert captured["assets"][0]["creatorRaw"] == "<b>Alice</b>"
    assert captured["assets"][0]["mediaBytesCaptured"] is False
    assert captured["assets"][0]["sha1"] == "abc" and captured["pageId"] == 1
    assert missing["title"] == "File:Missing.jpg"
    assert evidence["requestedFileTitles"] == request["fileTitles"]


def test_commons_rights_missing_fields_is_typed_block() -> None:
    import json
    body = json.dumps({"query":{"pages":[{"pageid":1,"title":"File:X.jpg","imageinfo":[{"url":"https://upload.wikimedia.org/x.jpg","sha1":"a","size":1,"mime":"image/jpeg","user":"U","timestamp":"2020-01-01T00:00:00Z","extmetadata":{}}]}]}}).encode()
    rows, _ = _load_mediawiki().commons_parse(body, {"fileTitles":["File:X.jpg"],"limit":1}, "image")
    assert rows[0]["disposition"] == "rights_metadata_incomplete"
