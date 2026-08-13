"""覆盖率产物解析：lcov 汇总/明细、Go coverprofile 与 Python trace。

`parse_lcov` 消费的是汇总口径（`LF`/`LH` + `BRDA` 计数），它回答「这份产物的
覆盖率是多少」。分片合并回答的是另一个问题：「怎么把 N 份产物拼成一份，使它
与全量运行产出的那一份等价」。这必须在明细层做——把两片的 `LF`/`LH` 相加会
把同一个文件的分母重复计数，把后一片直接覆盖前一片会丢掉只在前片被触达的文件。
除 import 重组外与拆分前逐字一致。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from .constants import (
    PYTHON_TRACE_ARTIFACT_SCHEMA,
    SERVICE_ROOT,
    CoverageError,
)
from .units import python_collection_targets

#: lcov 的行汇总记录。
LCOV_LINE_SUMMARY_RE = re.compile(r"^(LF|LH):(\d+)\s*$")
#: lcov 的可选分支汇总记录，仅用于与 BRDA 计数交叉校验。
LCOV_BRANCH_SUMMARY_RE = re.compile(r"^(BRF|BRH):(\d+)\s*$")
#: lcov 的行明细：`DA:<line>,<count>`（可选第三段 checksum）。
LCOV_LINE_DETAIL_RE = re.compile(r"^DA:(?P<line>\d+),(?P<count>\d+)(?:,[^,]*)?\s*$")
#: lcov 的分支明细：`BRDA:<line>,<block>,<branch>,<taken>`，`taken` 为 `-` 表示
#: 该分支所在的代码块从未被求值。
LCOV_BRANCH_DETAIL_RE = re.compile(
    r"^BRDA:(?P<line>\d+),(?P<block>\d+),(?P<branch>[^,]+),(?P<taken>-|\d+)\s*$"
)

#: go coverprofile 的块记录：`file.go:l.c,l.c numStmt count`。
GO_BLOCK_RE = re.compile(
    r"^(?P<block>.+:\d+\.\d+,\d+\.\d+)\s+(?P<statements>\d+)\s+(?P<count>\d+)\s*$"
)


def parse_lcov(text: str) -> dict[str, dict[str, tuple[int, int]]]:
    """解析 lcov，返回 ``{源文件: {"line": (covered,total), "branch": (...)}}``。

    行取 `LF`/`LH` 汇总；分支只数 `BRDA` 明细（Flutter 不写 `BRF`/`BRH`）。
    产出里同时给出 `BRF`/`BRH` 时与 BRDA 计数交叉校验，不一致即阻断——同一个
    维度不允许存在两套口径。
    """
    records: dict[str, dict[str, tuple[int, int]]] = {}
    source: str | None = None
    lines_found = lines_hit = 0
    branches_found = branches_hit = 0
    declared: dict[str, int] = {}

    def flush() -> None:
        if source is None:
            return
        if "BRF" in declared and declared["BRF"] != branches_found:
            raise CoverageError(
                f"{source}: BRF={declared['BRF']} 与 BRDA 计数 {branches_found} 不一致"
            )
        if "BRH" in declared and declared["BRH"] != branches_hit:
            raise CoverageError(
                f"{source}: BRH={declared['BRH']} 与 BRDA 命中数 {branches_hit} 不一致"
            )
        previous = records.get(source)
        if previous is None:
            records[source] = {
                "line": (lines_hit, lines_found),
                "branch": (branches_hit, branches_found),
            }
            return
        records[source] = {
            metric: (
                max(previous[metric][0], value[0]),
                max(previous[metric][1], value[1]),
            )
            for metric, value in {
                "line": (lines_hit, lines_found),
                "branch": (branches_hit, branches_found),
            }.items()
        }

    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("SF:"):
            flush()
            source = stripped[len("SF:") :]
            lines_found = lines_hit = branches_found = branches_hit = 0
            declared = {}
            continue
        if source is None:
            continue
        line_summary = LCOV_LINE_SUMMARY_RE.match(stripped)
        if line_summary:
            if line_summary.group(1) == "LF":
                lines_found = int(line_summary.group(2))
            else:
                lines_hit = int(line_summary.group(2))
            continue
        branch_summary = LCOV_BRANCH_SUMMARY_RE.match(stripped)
        if branch_summary:
            declared[branch_summary.group(1)] = int(branch_summary.group(2))
            continue
        branch_detail = LCOV_BRANCH_DETAIL_RE.match(stripped)
        if branch_detail:
            branches_found += 1
            if branch_detail.group("taken") not in {"-", "0"}:
                branches_hit += 1
    flush()
    if not records:
        raise CoverageError("lcov 中没有任何 SF: 记录")
    return records


# ---------------------------------------------------------------------------
# lcov 明细层：分片合并的唯一算术
# ---------------------------------------------------------------------------


def _lcov_file_record() -> dict:
    return {"lines": {}, "branches": {}}


def parse_lcov_records(text: str) -> dict[str, dict]:
    """把 lcov 拆成可合并的明细：``{源文件: {"lines": ..., "branches": ...}}``。

    ``lines`` 是 ``{行号: 命中次数}``，``branches`` 是
    ``{(行号, block, branch): 命中次数 | None}``，``None`` 对应 `taken` 为 `-`
    的「该分支所在代码块从未被求值」。

    每个 `SF:` 块自己声明的 `LF`/`LH`（以及 lcov 可选的 `BRF`/`BRH`）必须与它
    自己的明细自洽，否则阻断：合并后的汇总行由明细重新推导，若输入的汇总行本来
    就与明细不一致，同一维度就出现了两套口径，合并结果无从取舍。

    空文本返回空 dict：某一片的测试可能一个 `lib/**` 文件都没加载到（例如只测
    跨 package 的 generated contracts），此时 `flutter test` 产出的是零字节
    lcov。这是分片下的真实情况，不是采集失败——合并结果整体为空才是失败。
    """
    records: dict[str, dict] = {}
    source: str | None = None
    lines: dict[int, int] = {}
    branches: dict[tuple[int, str, str], int | None] = {}
    declared: dict[str, int] = {}

    def flush() -> None:
        if source is None:
            return
        _assert_lcov_summaries_match_details(source, declared, lines, branches)
        merge_lcov_file_record(
            records.setdefault(source, _lcov_file_record()),
            {"lines": lines, "branches": branches},
        )

    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("SF:"):
            flush()
            source = stripped[len("SF:") :]
            lines = {}
            branches = {}
            declared = {}
            continue
        if source is None:
            continue
        line_detail = LCOV_LINE_DETAIL_RE.match(stripped)
        if line_detail:
            number = int(line_detail.group("line"))
            lines[number] = lines.get(number, 0) + int(line_detail.group("count"))
            continue
        line_summary = LCOV_LINE_SUMMARY_RE.match(stripped)
        if line_summary:
            declared[line_summary.group(1)] = int(line_summary.group(2))
            continue
        branch_summary = LCOV_BRANCH_SUMMARY_RE.match(stripped)
        if branch_summary:
            declared[branch_summary.group(1)] = int(branch_summary.group(2))
            continue
        branch_detail = LCOV_BRANCH_DETAIL_RE.match(stripped)
        if branch_detail:
            key = (
                int(branch_detail.group("line")),
                branch_detail.group("block"),
                branch_detail.group("branch"),
            )
            taken = branch_detail.group("taken")
            branches[key] = _merge_branch_taken(
                branches.get(key), None if taken == "-" else int(taken)
            )
            continue
    flush()
    return records


def _assert_lcov_summaries_match_details(
    source: str,
    declared: dict[str, int],
    lines: dict[int, int],
    branches: dict[tuple[int, str, str], int | None],
) -> None:
    found = len(lines)
    hit = sum(1 for count in lines.values() if count > 0)
    branch_found = len(branches)
    branch_hit = sum(1 for taken in branches.values() if taken)
    for label, declared_key, derived in (
        ("LF", "LF", found),
        ("LH", "LH", hit),
        ("BRF", "BRF", branch_found),
        ("BRH", "BRH", branch_hit),
    ):
        if declared_key in declared and declared[declared_key] != derived:
            raise CoverageError(
                f"{source}: {label}={declared[declared_key]} 与明细推导值 {derived} 不一致；"
                "分片合并要求汇总行与 DA/BRDA 明细同源"
            )


def _merge_branch_taken(current: int | None, incoming: int | None) -> int | None:
    """合并同一个分支的 `taken`。

    `-`（None）表示「这一片没有求值过该分支」，与 `0`（求值过但没走到）不同：
    只要任一片给出了数字，合并结果就是数字之和；全部是 `-` 才继续是 `-`。这与
    `parse_lcov` 的命中判定（`-` 和 `0` 都算未命中）自洽，也不会让某一片的
    「没求值」抹掉另一片的实测命中。
    """
    if current is None:
        return incoming
    if incoming is None:
        return current
    return current + incoming


def merge_lcov_file_record(target: dict, incoming: dict) -> None:
    """把单个源文件的明细并入 ``target``（行命中累加，分支按上面的规则合并）。"""
    target_lines: dict[int, int] = target["lines"]
    for number, count in incoming["lines"].items():
        target_lines[number] = target_lines.get(number, 0) + count
    target_branches: dict[tuple[int, str, str], int | None] = target["branches"]
    for key, taken in incoming["branches"].items():
        target_branches[key] = _merge_branch_taken(target_branches.get(key), taken)


def merge_lcov_records(target: dict[str, dict], incoming: dict[str, dict]) -> None:
    """把一份 lcov 的全部明细并入 ``target``，按源文件取并集。

    「并集」是这里的关键：某个文件只在 A 片被触达时，它必须留在合并结果里；
    B 片没提到它不代表它没有覆盖率。同理某个文件在两片各覆盖了不同的行，合并
    后两批行都在分母里、都在分子里。
    """
    for source, record in incoming.items():
        merge_lcov_file_record(target.setdefault(source, _lcov_file_record()), record)


def _lcov_branch_sort_key(key: tuple[int, str, str]) -> tuple:
    line, block, branch = key
    return (line, _lcov_identifier_sort_key(block), _lcov_identifier_sort_key(branch))


def _lcov_identifier_sort_key(value: str) -> tuple[int, int, str]:
    return (0, int(value), "") if value.isdigit() else (1, 0, value)


def iter_lcov_lines(records: dict[str, dict]) -> Iterable[str]:
    """按 Flutter 产出的记录形状渲染合并结果：``SF / DA* / LF / LH / BRDA*``。

    `LF`/`LH` 由合并后的 `DA` 重新推导，不沿用任何一片的汇总行；不写
    `BRF`/`BRH`，与 Flutter 3.44 的原生产出保持同形，`parse_lcov` 因此对
    「全量运行的 lcov」与「分片合并的 lcov」走完全相同的代码路径。
    """
    for source in sorted(records):
        record = records[source]
        lines: dict[int, int] = record["lines"]
        yield f"SF:{source}\n"
        for number in sorted(lines):
            yield f"DA:{number},{lines[number]}\n"
        yield f"LF:{len(lines)}\n"
        yield f"LH:{sum(1 for count in lines.values() if count > 0)}\n"
        branches: dict[tuple[int, str, str], int | None] = record["branches"]
        for key in sorted(branches, key=_lcov_branch_sort_key):
            line, block, branch = key
            taken = branches[key]
            yield f"BRDA:{line},{block},{branch},{'-' if taken is None else taken}\n"
        yield "end_of_record\n"


def render_lcov(records: dict[str, dict]) -> str:
    return "".join(iter_lcov_lines(records))


def parse_go_coverprofile_files(text: str) -> dict[str, tuple[int, int]]:
    """解析 Go coverprofile，返回逐文件 ``{source: (covered, total)}``。

    首行是 `mode: atomic`。其后每行一个基本块，同一个块可能出现多次（不同测试
    二进制各写一份），按块去重并对计数求和，再按 source 聚合。逐文件明细是
    Cloud 对象归属的前提；先聚合成 service/domain 总数会永久丢失对象边界。
    """
    lines = text.splitlines()
    if not lines or not lines[0].startswith("mode:"):
        raise CoverageError("go coverprofile 缺少 `mode:` 首行")
    blocks: dict[str, tuple[int, int]] = {}
    for line in lines[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        match = GO_BLOCK_RE.match(stripped)
        if match is None:
            raise CoverageError(f"go coverprofile 无法解析的块记录: {stripped!r}")
        block = match.group("block")
        statements = int(match.group("statements"))
        count = int(match.group("count"))
        previous_statements, previous_count = blocks.get(block, (statements, 0))
        blocks[block] = (previous_statements, previous_count + count)
    if not blocks:
        raise CoverageError("go coverprofile 没有任何块记录")
    files: dict[str, list[int]] = {}
    for block, (statements, count) in blocks.items():
        source, separator, _coordinates = block.rpartition(":")
        if not separator or not source:
            raise CoverageError(f"go coverprofile block 缺少 source path: {block!r}")
        totals = files.setdefault(source, [0, 0])
        totals[1] += statements
        if count > 0:
            totals[0] += statements
    return {source: (values[0], values[1]) for source, values in files.items()}


def parse_go_coverprofile(text: str) -> dict[str, tuple[int, int]]:
    """解析 Go coverprofile 的全产物 statement 汇总；兼容公共解析入口。"""
    files = parse_go_coverprofile_files(text)
    return {
        "statement": (
            sum(covered for covered, _total in files.values()),
            sum(total for _covered, total in files.values()),
        )
    }


def parse_python_trace_files(
    text: str,
    target: str,
) -> dict[str, tuple[int, int]]:
    """解析标准库 trace 产物并锚定到 ``quwoquan_service`` 相对路径。"""
    if target not in python_collection_targets():
        raise CoverageError(f"{target}: 不是 Python coverage target")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise CoverageError(f"{target}: Python trace artifact 不是 JSON") from error
    if not isinstance(payload, dict) or set(payload) != {"schema", "files"}:
        raise CoverageError(f"{target}: Python trace artifact fields mismatch")
    if payload.get("schema") != PYTHON_TRACE_ARTIFACT_SCHEMA:
        raise CoverageError(
            f"{target}: Python trace schema 必须是 {PYTHON_TRACE_ARTIFACT_SCHEMA}"
        )
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise CoverageError(f"{target}: Python trace artifact 没有 production files")
    service_relative = Path(target).relative_to(SERVICE_ROOT.name).as_posix()
    parsed: dict[str, tuple[int, int]] = {}
    for relative, entry in sorted(files.items()):
        relative_path = Path(str(relative))
        if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
            or not relative_path.parts
            or relative_path.suffix != ".py"
        ):
            raise CoverageError(
                f"{target}: Python trace source path 非 canonical: {relative!r}"
            )
        if not isinstance(entry, dict) or set(entry) != {
            "coveredStatements",
            "totalStatements",
        }:
            raise CoverageError(
                f"{target}: Python trace source fields mismatch: {relative!r}"
            )
        covered = entry.get("coveredStatements")
        total = entry.get("totalStatements")
        if (
            not isinstance(covered, int)
            or isinstance(covered, bool)
            or not isinstance(total, int)
            or isinstance(total, bool)
            or covered < 0
            or total < 0
            or covered > total
        ):
            raise CoverageError(
                f"{target}: Python trace statement 计数非法: {relative!r}"
            )
        source = f"{service_relative}/{relative_path.as_posix()}"
        parsed[source] = (covered, total)
    return parsed
