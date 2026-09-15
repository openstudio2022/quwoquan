"""本地官方名单机械转录；列为 1 起始整数，Excel sheet 用原名，HTML 用 1 起始表序号。

只按显式表头行/列映射投影；原格、合并来源与所有后续行均保留，不作语义判断。
XLS 需调用方显式提供 xlrd（例如 PYTHONPATH=/tmp/xlrd_pkg），本工具不安装依赖。
"""
import argparse
import hashlib
import io
import json
import posixpath
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile


NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _position(ref):
    match = re.fullmatch(r"([A-Z]+)([1-9][0-9]*)", ref)
    if not match:
        raise ValueError(f"无效单元格引用: {ref}")
    column = 0
    for char in match[1]:
        column = column * 26 + ord(char) - ord("A") + 1
    return int(match[2]), column


def _ref(row, column):
    letters = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row}"


def _merge(ref, source):
    start, end = ref.split(":") if ":" in ref else (ref, ref)
    r1, c1 = _position(start)
    r2, c2 = _position(end)
    if r2 < r1 or c2 < c1:
        raise ValueError(f"倒置合并区: {ref}")
    return {"ref": ref, "anchor_ref": start, "bounds": [r1, c1, r2, c2], "source": source}


def _selected_blank(row, column, columns, merges):
    return column in columns.values() or any(
        r1 <= row <= r2 and c1 <= column <= c2
        for r1, c1, r2, c2 in (merge["bounds"] for merge in merges)
    )


def _xlsx_cell(cell, strings):
    kind = cell.get("t", "n")
    raw = cell.findtext(NS + "v")
    value = raw
    if kind == "inlineStr":
        value = "".join(t.text or "" for t in cell.findall(f"{NS}is//{NS}t"))
    elif kind == "s" and raw is not None:
        value = strings[int(raw)]
    formula = cell.find(NS + "f")
    return {"value": value, "ref": cell.attrib["r"], "type": kind, "stored_value": raw,
            "attributes": dict(cell.attrib), "formula": cell.findtext(NS + "f"),
            "formula_attributes": dict(formula.attrib) if formula is not None else None}


def _xlsx(data, sheet, columns):
    with ZipFile(io.BytesIO(data)) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets = workbook.findall(f"{NS}sheets/{NS}sheet")
        matches = [item for item in sheets if item.get("name") == sheet]
        if len(matches) != 1:
            raise ValueError(f"sheet 必须精确匹配唯一原名，可选: {[s.get('name') for s in sheets]}")
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_id = matches[0].get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        relation = next(item for item in rels if item.get("Id") == rel_id)
        if relation.get("TargetMode") == "External":
            raise ValueError("不支持外部 worksheet 关系")
        target = relation.attrib["Target"]
        part = posixpath.normpath(target.lstrip("/") if target.startswith("/") else "xl/" + target)
        root = ET.fromstring(archive.read(part))
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(t.text or "" for t in item.iter(NS + "t")) for item in shared]
        merges = [_merge(item.attrib["ref"], {"kind": "mergeCells", "part": part, "ref": item.attrib["ref"]})
                  for item in root.findall(f"{NS}mergeCells/{NS}mergeCell")]
        cells, row_numbers = {}, set()
        stats = {"sourceCellCount": 0, "payloadCellCount": 0, "styleOnlyCellCount": 0, "omittedStyleOnlyCellCount": 0}
        source_last_column = 0
        for row in root.findall(f"{NS}sheetData/{NS}row"):
            row_number = int(row.attrib["r"])
            if row_number in row_numbers:
                raise ValueError(f"重复行号: {row_number}")
            row_numbers.add(row_number)
            seen = set()
            for cell in row.findall(NS + "c"):
                ref = cell.attrib["r"]
                position = _position(ref)
                if position[0] != row_number or position in seen:
                    raise ValueError(f"行号冲突或重复单元格: {ref}")
                seen.add(position)
                source_last_column = max(source_last_column, position[1])
                stats["sourceCellCount"] += 1
                payload = any(cell.find(NS + tag) is not None for tag in ("v", "f", "is"))
                stats["payloadCellCount" if payload else "styleOnlyCellCount"] += 1
                if not payload and not _selected_blank(*position, columns, merges):
                    stats["omittedStyleOnlyCellCount"] += 1
                    continue
                cells[position] = _xlsx_cell(cell, strings)
    return cells, merges, max(row_numbers, default=0), {"name": sheet, "part": part,
                                                       "sourceColumnCount": source_last_column, "statistics": stats}


def _xls(data, sheet, columns):
    try:
        import xlrd
    except ImportError as error:
        raise ValueError("XLS 需要已存在的 xlrd；请显式设置 PYTHONPATH，不会自动安装") from error
    book = xlrd.open_workbook(file_contents=data, formatting_info=True)
    try:
        if sheet not in book.sheet_names():
            raise ValueError(f"sheet 必须使用原名，可选: {book.sheet_names()}")
        table = book.sheet_by_name(sheet)
        merges = []
        for r1, r2, c1, c2 in table.merged_cells:
            ref = f"{_ref(r1 + 1, c1 + 1)}:{_ref(r2, c2)}"
            merges.append(_merge(ref, {"kind": "xls.merged_cells", "range_zero_based_half_open": [r1, r2, c1, c2]}))
        cells = {}
        for row in range(table.nrows):
            for column in range(table.row_len(row)):
                cell = table.cell(row, column)
                if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK) and not _selected_blank(
                    row + 1, column + 1, columns, merges
                ):
                    continue
                cells[row + 1, column + 1] = {"value": cell.value, "ref": _ref(row + 1, column + 1),
                                            "type": cell.ctype, "xf_index": cell.xf_index}
        return cells, merges, table.nrows, {"name": sheet, "index": book.sheet_names().index(sheet) + 1,
                                          "sourceColumnCount": table.ncols, "datemode": book.datemode,
                                          "reader": f"xlrd {xlrd.__version__}"}
    finally:
        book.release_resources()


class _HTMLTables(HTMLParser):
    """只接受明确 tr/td 边界；嵌套表与非正跨度拒绝，避免猜测浏览器修复结果。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.table = None
        self.cell = None
        self.row = 0
        self.in_row = False
        self.cell_index = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            if self.table is not None:
                raise ValueError("不支持嵌套 HTML table")
            self.table = {"rows": [], "line": self.getpos()[0]}
            self.tables.append(self.table)
            self.row = 0
        elif self.table is not None and tag == "tr":
            if self.in_row:
                raise ValueError("HTML tr 未显式闭合")
            self.in_row = True
            self.row += 1
            self.cell_index = 0
            self.table["rows"].append([])
        elif self.table is not None and tag in ("td", "th"):
            if not self.in_row or self.cell is not None:
                raise ValueError("HTML 单元格缺少明确 tr/结束标签")
            self.cell_index += 1
            self.cell = {"tag": tag, "attributes": dict(attrs), "line": self.getpos()[0],
                         "cell_index": self.cell_index, "start_tag": self.get_starttag_text(), "value": ""}
        elif self.cell is not None and tag == "br":
            self.cell["value"] += "\n"

    def handle_data(self, data):
        if self.cell is not None:
            self.cell["value"] += data

    def handle_endtag(self, tag):
        if self.table is None:
            return
        if tag in ("td", "th"):
            if self.cell is None or self.cell["tag"] != tag:
                raise ValueError("HTML 单元格闭合不匹配")
            self.table["rows"][-1].append(self.cell)
            self.cell = None
        elif tag == "tr":
            if self.cell is not None or not self.in_row:
                raise ValueError("HTML 行闭合不匹配")
            self.in_row = False
        elif tag == "table":
            if self.cell is not None or self.in_row:
                raise ValueError("HTML table 中存在未闭合行/单元格")
            self.table = None


def _html(data, sheet, columns):
    parser = _HTMLTables()
    parser.feed(data.decode("utf-8-sig"))
    parser.close()
    if parser.table is not None:
        raise ValueError("HTML table 未闭合")
    if not re.fullmatch(r"[1-9][0-9]*", sheet) or int(sheet) > len(parser.tables):
        raise ValueError(f"HTML sheet 为 1 起始 table 序号，共 {len(parser.tables)} 张表")
    table = parser.tables[int(sheet) - 1]
    cells, merges, occupied = {}, [], set()
    for row, raw_cells in enumerate(table["rows"], 1):
        column = 1
        for cell in raw_cells:
            while (row, column) in occupied:
                column += 1
            attrs = cell["attributes"]
            rowspan, colspan = int(attrs.get("rowspan", "1")), int(attrs.get("colspan", "1"))
            if rowspan < 1 or colspan < 1 or row + rowspan - 1 > len(table["rows"]):
                raise ValueError("不支持非正或越过表尾的 HTML 跨度")
            ref = _ref(row, column)
            cells[row, column] = dict(cell, ref=ref)
            for r in range(row, row + rowspan):
                for c in range(column, column + colspan):
                    if (r, c) in occupied:
                        raise ValueError("HTML 合并单元格重叠")
                    occupied.add((r, c))
            if rowspan > 1 or colspan > 1:
                merges.append(_merge(f"{ref}:{_ref(row + rowspan - 1, column + colspan - 1)}",
                                     {"kind": "html.span", "attributes": attrs, "line": cell["line"],
                                      "cell_index": cell["cell_index"]}))
            column += colspan
    return cells, merges, len(table["rows"]), {"name": sheet, "index": int(sheet), "line": table["line"]}


def _cell(row, column, cells, merges):
    ref = _ref(row, column)
    original = cells.get((row, column))
    merged = [item for item in merges if item["bounds"][0] <= row <= item["bounds"][2]
              and item["bounds"][1] <= column <= item["bounds"][3]]
    if len(merged) > 1:
        raise ValueError(f"重叠合并区: {ref}")
    merge = merged[0] if merged else None
    source_ref = merge["anchor_ref"] if merge else ref
    source = cells.get(_position(source_ref))
    return {"row": row, "column": column, "ref": ref, "raw_value": original["value"] if original else None,
            "value": source["value"] if source else None, "source_ref": source_ref,
            "merge_ref": merge["ref"] if merge else None, "original": original}


def _rows(cells, merges, last_row, columns):
    # 只物化源格、映射格与真实合并格，避免远端样式格造成笛卡尔积膨胀。
    selected = {row: set(columns.values()) for row in range(1, last_row + 1)}
    for row, column in cells:
        selected[row].add(column)
    for merge in merges:
        r1, c1, r2, c2 = merge["bounds"]
        for row in range(r1, r2 + 1):
            selected[row].update(range(c1, c2 + 1))
    rows = []
    for row, indices in selected.items():
        values = {col: _cell(row, col, cells, merges) for col in sorted(indices)}
        rows.append({"row": row, "cells": list(values.values()),
                     "fields": {key: {k: v for k, v in values[col].items() if k != "original"}
                                for key, col in columns.items()}})
    return rows


def parse_bytes(data, *, format, sheet, header_row, columns):
    """显式映射为任意字段名 → 1 起始列号；返回原表格、表头和未过滤行。"""
    if type(header_row) is not int or header_row < 1:
        raise ValueError("header-row 必须为正整数")
    if not isinstance(sheet, str) or not sheet:
        raise ValueError("sheet 必须显式提供")
    if not isinstance(columns, dict) or not columns or any(
        not isinstance(key, str) or not key or type(value) is not int or value < 1
        for key, value in columns.items()
    ):
        raise ValueError("columns 必须是非空 JSON 对象，字段名映射到 1 起始整数列号")
    readers = {"xlsx": _xlsx, "xls": _xls, "html": _html}
    if format not in readers:
        raise ValueError(f"不支持的 format: {format}")
    cells, merges, last_row, sheet_info = readers[format](data, sheet, columns)
    last_row = max([last_row] + [item["bounds"][2] for item in merges])
    last_column = max([sheet_info.get("sourceColumnCount", 0)] + [c for _, c in cells]
                      + [item["bounds"][3] for item in merges])
    if header_row > last_row or max(columns.values()) > last_column:
        raise ValueError("header-row 或 columns 超出选定表范围")
    rows = _rows(cells, merges, last_row, columns)
    return {"source": {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()},
            "format": format, "sheet": sheet_info, "header_row": header_row, "columns": columns,
            "merges": merges, "preamble": rows[:header_row - 1], "header": rows[header_row - 1],
            "rows": rows[header_row:], "row_count": last_row, "column_count": last_column}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--format", required=True, choices=("xlsx", "xls", "html"))
    parser.add_argument("--sheet", required=True, help="Excel 原 sheet 名；HTML 为 1 起始 table 序号")
    parser.add_argument("--header-row", required=True, type=int)
    parser.add_argument("--columns", required=True, help='字段名到 1 起始列号，例如 {"serial":1,"name":2}')
    parser.add_argument("--output", type=Path, help="只允许新文件；不提供时仅 stdout")
    args = parser.parse_args(argv)
    try:
        if args.output and args.output.resolve() == args.input.resolve():
            raise ValueError("output 不得与 input 相同")
        result = parse_bytes(args.input.read_bytes(), format=args.format, sheet=args.sheet,
                             header_row=args.header_row, columns=json.loads(args.columns))
        text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(text)
        else:
            sys.stdout.write(text)
    except (OSError, ValueError, KeyError, ET.ParseError) as error:
        print(f"official_lists: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
