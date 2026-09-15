# 验收绑定缺口：现有来源计划 GWT-001 不覆盖官方表格无损/紧凑转录；待 owner 冻结专门 GWT。
"""离线名单机械转录：不丢行、不合并同名、不越真实合并区继承。"""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[4]
TOOL = ROOT / ".agents/skills/content-production/carriers/homepage/official_lists.py"
spec = importlib.util.spec_from_file_location("official_lists", TOOL)
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


def xlsx_bytes():
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("xl/workbook.xml", '''<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="名单" sheetId="1" r:id="r1"/><sheet name="另一表" sheetId="2" r:id="r2"/></sheets></workbook>''')
        archive.writestr("xl/_rels/workbook.xml.rels", '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Target="worksheets/sheet1.xml"/><Relationship Id="r2" Target="/xl/worksheets/sheet2.xml"/></Relationships>''')
        archive.writestr("xl/sharedStrings.xml", '''<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><r><t>景区</t></r><r><t>名称</t></r></si></sst>''')
        archive.writestr("xl/worksheets/sheet1.xml", '''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
<row r="1"><c r="A1" t="inlineStr"><is><t>序号</t></is></c><c r="B1" t="s"><v>0</v></c><c r="D1" t="inlineStr"><is><t>等级</t></is></c></row>
<row r="2"><c r="A2"><v>1</v></c><c r="B2" t="inlineStr"><is><t xml:space="preserve"> 同名山 </t></is></c><c r="C2" t="inlineStr"><is><t>甲地</t></is></c><c r="D2" t="inlineStr"><is><t>4A</t></is></c><c r="F2"><f>1+1</f><v>2</v></c></row>
<row r="3"><c r="B3" t="inlineStr"><is><t> 同名山 </t></is></c><c r="C3" t="inlineStr"><is><t>乙地</t></is></c></row>
<row r="4"><c r="B4" t="inlineStr"><is><t>空序号子项</t></is></c></row>
<row r="6"><c r="B6" t="inlineStr"><is><t>末行</t></is></c></row>
</sheetData><mergeCells><mergeCell ref="A2:A3"/><mergeCell ref="D2:E2"/></mergeCells></worksheet>''')
        archive.writestr("xl/worksheets/sheet2.xml", '''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>另一表头</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>独立值</t></is></c></row></sheetData></worksheet>''')
    return output.getvalue()


def extract(data, fmt="xlsx", sheet="名单", columns=None):
    return subject.parse_bytes(data, format=fmt, sheet=sheet, header_row=1,
                               columns=columns or {"serial": 1, "name": 2, "rating": 4})


def test_xlsx_sparse_inline_shared_strings_and_merge_provenance():
    result = extract(xlsx_bytes())
    assert result["header"]["fields"]["name"]["value"] == "景区名称"
    rows = result["rows"]
    assert [row["row"] for row in rows] == [2, 3, 4, 5, 6]
    assert [row["fields"]["name"]["value"] for row in rows[:2]] == [" 同名山 "] * 2
    serial = rows[1]["fields"]["serial"]
    assert (serial["ref"], serial["raw_value"], serial["value"], serial["source_ref"], serial["merge_ref"]) == ("A3", None, "1", "A2", "A2:A3")
    assert rows[2]["fields"]["serial"]["value"] is None
    assert rows[1]["fields"]["rating"]["value"] is None
    assert rows[0]["cells"][4]["source_ref"] == "D2"
    assert rows[0]["cells"][4]["merge_ref"] == "D2:E2"
    assert rows[0]["cells"][5]["original"]["formula"] == "1+1"
    assert rows[0]["cells"][2]["value"] == "甲地"
    assert rows[1]["cells"][2]["value"] == "乙地"
    assert result["merges"][0]["source"]["kind"] == "mergeCells"
    second = extract(xlsx_bytes(), sheet="另一表", columns={"name": 1})
    assert second["rows"][0]["fields"]["name"]["value"] == "独立值"
    assert second["merges"] == []


def test_far_sparse_style_cell_does_not_expand_all_rows():
    output = io.BytesIO()
    with ZipFile(io.BytesIO(xlsx_bytes())) as original, ZipFile(output, "w") as archive:
        for name in original.namelist():
            data = original.read(name)
            if name == "xl/worksheets/sheet1.xml":
                data = data.replace(b'<c r="F2">', b'<c r="XFD2" s="1"/><c r="F2">')
            archive.writestr(name, data)
    result = extract(output.getvalue())
    assert result["column_count"] == 16384
    assert result["rows"][0]["cells"][-1]["ref"] == "F2"
    assert result["sheet"]["statistics"]["omittedStyleOnlyCellCount"] == 1
    assert len(result["rows"][0]["cells"]) == 6
    assert len(result["rows"][1]["cells"]) == 4


def test_style_area_size_does_not_control_output_size_or_lose_payload():
    def decorated(count):
        output = io.BytesIO()
        with ZipFile(io.BytesIO(xlsx_bytes())) as original, ZipFile(output, "w") as archive:
            for name in original.namelist():
                data = original.read(name)
                if name == "xl/worksheets/sheet1.xml":
                    styles = ''.join(f'<c r="{subject._ref(2, c)}" s="7"/>' for c in range(20, 20 + count))
                    extra = '<c r="G2"><f t="shared" si="1"/></c><c r="H2"><v>0</v></c><c r="I2" t="inlineStr"><is><t/></is></c><c r="E2" s="9"/>'
                    data = data.replace(b'<sheetData>', b'<dimension ref="A1:XFD1048576"/><sheetData>')
                    data = data.replace(b'<c r="F2">', (styles + extra + '<c r="F2">').encode())
                    data = data.replace(b'<row r="4">', b'<row r="4"><c r="A4" s="8"/>')
                archive.writestr(name, data)
        return output.getvalue()

    small, large = decorated(1), decorated(12000)
    before = hashlib.sha256(large).hexdigest()
    a, b = extract(small), extract(large)
    assert b["source"] == {"bytes": len(large), "sha256": before}
    assert hashlib.sha256(large).hexdigest() == before
    assert b["rows"] == a["rows"]
    assert b["merges"] == a["merges"]
    assert b["row_count"] == 6
    stats = b["sheet"]["statistics"]
    assert stats["omittedStyleOnlyCellCount"] == 12000
    assert stats["styleOnlyCellCount"] == 12002
    assert stats["sourceCellCount"] == stats["payloadCellCount"] + stats["styleOnlyCellCount"]
    by_ref = {c["ref"]: c for c in b["rows"][0]["cells"]}
    assert by_ref["G2"]["original"]["formula_attributes"] == {"t": "shared", "si": "1"}
    assert by_ref["H2"]["raw_value"] == "0"
    assert by_ref["I2"]["raw_value"] == ""
    assert by_ref["E2"]["original"]["attributes"]["s"] == "9"
    assert by_ref["E2"]["source_ref"] == "D2"
    assert b["rows"][2]["cells"][0]["original"]["attributes"]["s"] == "8"
    text = json.dumps(b, ensure_ascii=False, indent=2)
    assert len(text.encode()) < 22000
    assert abs(len(text) - len(json.dumps(a, ensure_ascii=False, indent=2))) < 100
    assert '"xml"' not in text
    assert all("original" not in field for row in b["rows"] for field in row["fields"].values())


@pytest.mark.parametrize("html", [
    '<table><tr><td rowspan="0">坏跨度</td></tr></table>',
    '<table><tr><td rowspan="2">越界</td></tr></table>',
    '<table><tr><td><table></table></td></tr></table>',
    '<table><tr><td>未闭合</table>',
])
def test_unsupported_html_structure_fails_instead_of_guessing(html):
    with pytest.raises(ValueError):
        extract(html.encode(), fmt="html", sheet="1", columns={"name": 1})


def test_html_rowspan_colspan_and_independent_tables():
    data = '''<table><tr><th>序号</th><th>名称</th><th>等级</th></tr>
<tr><td rowspan="2">1</td><td>同名山</td><td colspan="2">4A</td></tr>
<tr><td>同名山</td><td></td></tr>
<tr><td></td><td>空序号子项<br>原文&amp;尾</td></tr></table>
<table><tr><th>名称</th></tr><tr><td>另一表</td></tr></table>'''.encode()
    result = extract(data, fmt="html", sheet="1", columns={"serial": 1, "name": 2, "rating": 3})
    rows = result["rows"]
    assert len(rows) == 3
    assert rows[1]["fields"]["serial"]["value"] == "1"
    assert rows[1]["fields"]["serial"]["source_ref"] == "A2"
    assert rows[1]["fields"]["serial"]["raw_value"] is None
    assert rows[2]["fields"]["serial"]["value"] == ""
    assert rows[1]["fields"]["rating"]["value"] == ""
    assert rows[2]["fields"]["name"]["value"] == "空序号子项\n原文&尾"
    assert result["merges"][0]["source"]["attributes"]["rowspan"] == "2"
    assert rows[0]["cells"][3]["source_ref"] == "C2"
    assert rows[0]["cells"][1]["original"]["cell_index"] == 2
    assert "original" not in rows[0]["fields"]["name"]
    assert extract(data, fmt="html", sheet="2", columns={"name": 1})["rows"][0]["fields"]["name"]["value"] == "另一表"


@pytest.mark.parametrize("options", [
    {"sheet": "不存在"}, {"header_row": 0}, {"header_row": 99},
    {"columns": {"name": 0}}, {"columns": {"name": True}},
    {"columns": {"name": "B"}}, {"columns": {}}, {"columns": {"name": 99}},
])
def test_explicit_selection_rejects_invalid_input(options):
    args = {"format": "xlsx", "sheet": "名单", "header_row": 1, "columns": {"name": 2}}
    args.update(options)
    with pytest.raises(ValueError):
        subject.parse_bytes(xlsx_bytes(), **args)


def test_cli_stdout_and_create_once_output(tmp_path, capsys):
    source = tmp_path / "original.xlsx"
    source.write_bytes(xlsx_bytes())
    before = source.read_bytes()
    args = ["--input", str(source), "--format", "xlsx", "--sheet", "名单", "--header-row", "1", "--columns", '{"name":2}']
    assert subject.main(args) == 0
    assert len(json.loads(capsys.readouterr().out)["rows"]) == 5
    assert subject.main(args + ["--output", str(source)]) == 2
    output = tmp_path / "snapshot.json"
    assert subject.main(args + ["--output", str(output)]) == 0
    snapshot = output.read_bytes()
    assert subject.main(args + ["--output", str(output)]) == 2
    assert output.read_bytes() == snapshot
    assert source.read_bytes() == before
    alias = tmp_path / "alias.xlsx"
    alias.symlink_to(source)
    assert subject.main(args + ["--output", str(alias)]) == 2
    assert source.read_bytes() == before
