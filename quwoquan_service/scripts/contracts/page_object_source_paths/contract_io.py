"""契约 YAML 的读取与逐行外科手术式改写。

整文件 ``yaml.dump`` 会抹掉注释、flow-style 与空行；本模块坚持逐行改写，
保证 diff 只有目标行。
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Sequence

import yaml

from .models import ContractError


def load_contract(contract_path: Path) -> tuple[dict, str]:
    text = contract_path.read_text(encoding="utf-8")
    document = yaml.safe_load(text)
    if not isinstance(document, dict):
        raise ContractError(f"{contract_path}: YAML 根必须是 mapping")
    pages = document.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ContractError(f"{contract_path}: pages 必须是非空列表")
    return document, text


def contract_pages(document: dict) -> list[dict]:
    pages: list[dict] = []
    for index, page in enumerate(document["pages"]):
        if not isinstance(page, dict):
            raise ContractError(f"pages[{index}] 必须是 mapping")
        page_id = page.get("page_id")
        source_path = page.get("source_path")
        if not isinstance(page_id, str) or not page_id.strip():
            raise ContractError(f"pages[{index}]: page_id 缺失")
        if not isinstance(source_path, str) or not source_path.strip():
            raise ContractError(f"{page_id}: source_path 缺失")
        pages.append(page)
    return pages


def _page_block_range(lines: Sequence[str], page_id: str) -> tuple[int, int]:
    item_pattern = re.compile(rf"\s*-\s+page_id:\s*{re.escape(page_id)}\s*$")
    starts = [
        index
        for index, line in enumerate(lines)
        if item_pattern.fullmatch(line.rstrip("\n"))
    ]
    if len(starts) != 1:
        raise ContractError(f"{page_id}: 页面块定位不唯一（命中 {len(starts)} 次）")
    start = starts[0]
    indent = len(lines[start]) - len(lines[start].lstrip())
    for index in range(start + 1, len(lines)):
        stripped = lines[index].lstrip()
        if stripped.startswith("- ") and (len(lines[index]) - len(stripped)) <= indent:
            return start, index
    return start, len(lines)


def _field_region(
    lines: Sequence[str], start: int, end: int, page_id: str, field_name: str
) -> tuple[int, int]:
    """返回页面块内某字段自身及其续行（block list）的行区间。"""

    field_pattern = re.compile(rf"(\s*){re.escape(field_name)}:.*$")
    hits: list[int] = []
    for index in range(start, end):
        if field_pattern.fullmatch(lines[index].rstrip("\n")):
            hits.append(index)
    if len(hits) != 1:
        raise ContractError(
            f"{page_id}: 字段 {field_name} 定位不唯一（命中 {len(hits)} 次）"
        )
    field_line = hits[0]
    indent = len(lines[field_line]) - len(lines[field_line].lstrip())
    region_end = field_line + 1
    for index in range(field_line + 1, end):
        stripped = lines[index].strip()
        if not stripped:
            break
        if len(lines[index]) - len(lines[index].lstrip()) <= indent:
            break
        region_end = index + 1
    return field_line, region_end


def replace_page_path(
    text: str, page_id: str, field_name: str, old_path: str, new_path: str
) -> str:
    """只替换指定页面指定字段内那一处路径，不触碰任何其它字节。

    整文件 ``yaml.dump`` 会抹掉注释、flow-style 与空行，并把并发搬迁流的其它改动
    一起重排；这里坚持逐行外科手术，保证 diff 只有目标行。
    """

    lines = text.splitlines(keepends=True)
    start, end = _page_block_range(lines, page_id)
    field_start, field_end = _field_region(lines, start, end, page_id, field_name)
    token = re.compile(rf"(?<![\w./-]){re.escape(old_path)}(?![\w./-])")
    hits = [
        index
        for index in range(field_start, field_end)
        if token.search(lines[index])
    ]
    if len(hits) != 1 or len(token.findall(lines[hits[0]])) != 1:
        raise ContractError(
            f"{page_id}.{field_name}: 路径出现次数不唯一，放弃改写: {old_path}"
        )
    target = hits[0]
    lines[target] = token.sub(lambda _: new_path, lines[target], count=1)
    return "".join(lines)


def _atomic_write(target: Path, payload: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise
