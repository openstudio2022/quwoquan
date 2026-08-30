#!/usr/bin/env python3
"""空引用与失败的隔离门禁（硬 BLOCK，无 allowlist、无基线）。

规格：`specs/feature-tree/runtime/system-architecture-and-engineering-guide/
absent-empty-failure-nullability/spec.md`（REQ-004）。

`T?` 只表达「缺席」。异常被处理掉之后 `return null` 会把「没做成」和「本来就没有」
压成同一个值，调用方无从区分。空集合与零计数同理：把加载失败伪装成「列表是空的」，
界面就会显示「暂无内容」而不是「加载失败，请重试」。

**范围三条边**：

* 异常处理点包含 `catch {}`、`catchError(...)` 与 `onError:` 三种形态。只扫 `catch`
  关键字会整批漏掉 `Future` 链上的处理，而 `.catchError((_) => null)` 与
  `catch (_) { return null; }` 在语义上完全是同一件事。
* `onError` 的匹配必须带词边界。`actionError: () => null` 是 `copyWith` 的可空字段
  更新，与错误处理无关，却恰好包含 `onError` 子串——误报会逼出豁免名单，而规则
  明令禁止新增 allowlist。
* `return false` 不在本门禁范围内。它没有把失败压成缺席或空值，调用方也不会把
  `false` 读成成功；异常被吞掉这件事由吞错预算门禁（`verify_catch_swallow_budget`）
  承担。两道门重叠只会让同一段代码得到两个结论。

但判据不是「禁止异常处理点返回 null」，那会把两类本质不同的代码一起判死：

1. **解析器**：`jsonDecode` 抛异常，含义就是「这段输入不是 JSON」。函数在非异常
   路径上也返回 null 表达同一件事，异常只是同一判定的另一条到达方式。这里没有
   任何动作「没做成」，null 是准确的。
2. **故障降级**：转码失败、box 打不开、token 解析炸了。这些是真实故障，返回 null
   之后调用方看到的和「本来就没有」一模一样，故障在运行期不留任何痕迹。

两类的区别是语义的，静态分析读不出来。所以让代码自己声明属于哪一类：

- 解析器用 `try` 前缀命名（对齐 `int.tryParse` 的生态惯例）。名字是承诺——叫
  `_tryReadCoordinate` 就等于声明「返回 null 表示这不是一个坐标」。
- 其余一律要求留下证据：结构化上报（`ExceptionTelemetryPort`）、显式失败态，或
  携带 error 的日志。

`try` 前缀只赦免 `null`，不赦免空集合。`null` 能准确表达「这段输入不是一个 X」，
而返回空 map 会把「不是 map」和「是个空 map」重新压回同一个值——换个容器犯同一个错。

两条路都可自动判定，因此不需要豁免名单，也不需要基线数字——没有可调的旋钮，新增
违规只能是 BLOCK。catch 解析与吞错预算门禁同源，避免两道门对同一段代码各执一词。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.dart_catch_scan import (
    catch_bodies_with_offsets,
    enclosing_declaration_name,
    error_callback_bodies_with_offsets,
    iter_business_dart_sources,
    line_of,
)
from _common.paths import APP_ROOT

LIB_ROOT = APP_ROOT / "lib"

_RETURN_NULL = re.compile(r"\breturn\s+null\s*;")

#: 空集合与零计数：把失败塌陷成「在场为空」。`<T>[]` 与 `const {}` 都算。
_RETURN_EMPTY = re.compile(
    r"\breturn\s+(?:const\s+)?(?:<[^>{}]*>\s*)?(?:\[\s*\]|\{\s*\}|0|''|\"\")\s*;"
)

#: 箭头回调没有 `return`，`(_) => null` 的整个 body 就是那个值。
_BARE_NULL = re.compile(r"^\s*null\s*$")
_BARE_EMPTY = re.compile(
    r"^\s*(?:const\s+)?(?:<[^>{}]*>\s*)?(?:\[\s*\]|\{\s*\}|0|''|\"\")\s*$"
)

#: `try` 前缀 = 「返回 null 表示输入不是这个形状」的显式承诺。
_PARSER_NAME = re.compile(r"^_?try[A-Z_]")

# 结构化上报或显式失败态：让降级在运行期留下证据。
#
# `error:` 小写命名参数覆盖两类真实形态：`developer.log(error:)` 与
# `state.copyWith(error: ...)`。后者是把失败搬到 UI 上的显式失败态，不是降级。
# 大写的 `onError:` / `actionError:` 不会命中。
_OBSERVED_MARKERS = (
    "recordHandledException",
    "recordGlobalException",
    "recordPageState",
    "logQuwoquanAppException",
    "rethrow",
    "failure:",
    "error:",
)
_OBSERVED_PATTERNS = (
    # 项目惯例的对象内上报方法：_recordDegrade / _recordLocalTimelineFailure 等。
    re.compile(r"_record[A-Z]\w*\s*\("),
    # `Future.error` 是 Future 世界的 rethrow；`throw` 同理。处理体里出现它们，
    # 说明作者为真实失败留了通路，`null` 只是其中「确实不存在」那一支。
    re.compile(r"Future(?:<[^>]*>)?\s*\.\s*error\s*\("),
    re.compile(r"(?<![\w$])throw(?![\w$])"),
)


def _is_observed(body: str) -> bool:
    if any(marker in body for marker in _OBSERVED_MARKERS):
        return True
    return any(pattern.search(body) for pattern in _OBSERVED_PATTERNS)


def _is_declared_parser(clean: str, offset: int) -> bool:
    name = enclosing_declaration_name(clean, offset)
    return bool(name and _PARSER_NAME.match(name))


def _disguise_kind(body: str) -> str | None:
    """这个异常处理体把失败伪装成了什么。`None` 表示没有伪装。"""
    if _RETURN_NULL.search(body) or _BARE_NULL.match(body):
        return "null"
    if _RETURN_EMPTY.search(body) or _BARE_EMPTY.match(body):
        return "empty"
    return None


def violations() -> list[tuple[str, int, str, str]]:
    """`(相对路径, 行号, 所在函数名, 伪装形态)`。

    命中条件：异常处理点把失败伪装成缺席或空值，且既没声明成解析器也没留证据。
    """
    hits: list[tuple[str, int, str, str]] = []
    for rel, clean in iter_business_dart_sources(LIB_ROOT, APP_ROOT):
        handlers = catch_bodies_with_offsets(clean) + error_callback_bodies_with_offsets(
            clean
        )
        for body, offset in handlers:
            kind = _disguise_kind(body)
            if kind is None or _is_observed(body):
                continue
            if kind == "null" and _is_declared_parser(clean, offset):
                continue
            name = enclosing_declaration_name(clean, offset) or "<unknown>"
            hits.append((rel, line_of(clean, offset), name, kind))
    return sorted(hits)


_KIND_LABEL = {"null": "压成 null", "empty": "塌陷成空集合/零值"}


def main() -> int:
    hits = violations()
    if "--locate" in sys.argv:
        for rel, line, name, kind in hits:
            print(f"{rel}:{line} ({name}) {kind}")
        return 0

    if hits:
        print(f"FAIL: {len(hits)} 处异常处理把失败伪装成缺席或空值，且没有留下任何证据：")
        for rel, line, name, kind in hits:
            print(f"  - {rel}:{line} in {name}() —— {_KIND_LABEL[kind]}")
        print(
            "  三选一：\n"
            "  1) 失败向上抛出或转结构化失败（用户动作未达成）；\n"
            "  2) 确属降级则保留原返回值，并经 ExceptionTelemetryPort.recordHandledException"
            " 或 developer.log(error:) 留证据（已达成但降级）；\n"
            "  3) 若异常本身就是形状判定（这段输入不是一个 X），返回 null 并把函数改名为"
            " try 前缀，由命名承诺该语义——空集合不适用这条，它会把「不是 X」和"
            "「空的 X」重新压回同一个值。"
        )
        return 1

    print("OK: 异常处理点未把失败伪装成缺席或空值")
    return 0


if __name__ == "__main__":
    sys.exit(main())
