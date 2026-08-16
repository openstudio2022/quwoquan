"""Dart `catch` 块的共享静态扫描原语。

异常链路上有多道门禁（吞错预算、空引用隔离），它们对「一个 catch 块的 body 是
什么」必须给出同一答案。解析一旦各写一份，两道门就会对同一段代码得出不同结论，
治理本身反而成了第二真相源。
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path


def strip_comments_and_strings(source: str) -> str:
    """把注释置空、字符串字面量替换为占位符，保持长度与行结构不变。"""
    out: list[str] = []
    i = 0
    n = len(source)
    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            while i < n and source[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if ch == "/" and nxt == "*":
            out.append("  ")
            i += 2
            while i < n and not (source[i] == "*" and i + 1 < n and source[i + 1] == "/"):
                out.append("\n" if source[i] == "\n" else " ")
                i += 1
            if i < n:
                out.append("  ")
                i += 2
            continue
        if ch in ("'", '"'):
            quote = ch
            triple = source[i : i + 3] == quote * 3
            token = quote * 3 if triple else quote
            out.append("s" * len(token))
            i += len(token)
            while i < n:
                if source[i] == "\\":
                    out.append("ss")
                    i += 2
                    continue
                if source[i : i + len(token)] == token:
                    out.append("s" * len(token))
                    i += len(token)
                    break
                out.append("\n" if source[i] == "\n" else "s")
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def catch_bodies(clean: str) -> list[str]:
    """提取所有 catch 块 body（花括号配对，输入已剥离字符串/注释）。"""
    return [body for body, _ in catch_bodies_with_offsets(clean)]


def catch_bodies_with_offsets(clean: str) -> list[tuple[str, int]]:
    """同 [catch_bodies]，但额外给出 body 起点偏移，便于报告行号。"""
    bodies: list[tuple[str, int]] = []
    idx = 0
    while True:
        idx = clean.find("catch", idx)
        if idx < 0:
            break
        before = clean[idx - 1] if idx > 0 else " "
        after = clean[idx + 5] if idx + 5 < len(clean) else " "
        if before.isalnum() or before == "_" or after.isalnum() or after == "_":
            idx += 5
            continue
        paren = clean.find("(", idx)
        if paren < 0:
            break
        depth = 1
        j = paren + 1
        while j < len(clean) and depth > 0:
            if clean[j] == "(":
                depth += 1
            elif clean[j] == ")":
                depth -= 1
            j += 1
        while j < len(clean) and clean[j] in " \n\t\r":
            j += 1
        if j >= len(clean) or clean[j] != "{":
            idx = j
            continue
        depth = 1
        k = j + 1
        while k < len(clean) and depth > 0:
            if clean[k] == "{":
                depth += 1
            elif clean[k] == "}":
                depth -= 1
            k += 1
        bodies.append((clean[j + 1 : k - 1], j + 1))
        idx = k
    return bodies


#: `Future` 的错误处理入口。`onError` 必须带词边界：`actionError:` 含有 `onError`
#: 子串，而它是 `copyWith` 的可空字段更新，与错误处理毫无关系。少了这个边界，
#: 扫描就会误报，而误报会逼出豁免名单。
_CATCH_ERROR_CALL = re.compile(r"(?<![\w$])catchError\s*\(")
_ON_ERROR_ARGUMENT = re.compile(r"(?<![\w$])onError\s*:")


def error_callback_bodies_with_offsets(clean: str) -> list[tuple[str, int]]:
    """提取 `catchError(...)` 与 `onError: ...` 的回调体。

    `catch {}` 与这两者在语义上是同一件事——异常到了这里就被处理掉了——但语法上
    完全不同，只扫 `catch` 关键字会整批漏掉 `Future` 链上的处理。
    """
    found: list[tuple[str, int]] = []
    for pattern in (_CATCH_ERROR_CALL, _ON_ERROR_ARGUMENT):
        for match in pattern.finditer(clean):
            body = _callback_body(_argument_segment(clean, match.end()))
            if body is not None:
                found.append((body, match.start()))
    return sorted(found, key=lambda item: item[1])


def _argument_segment(clean: str, start: int) -> str:
    """从 `start` 取一个实参，到顶层逗号或未配对的右括号为止。"""
    depth = 0
    index = start
    while index < len(clean):
        character = clean[index]
        if character in "([{":
            depth += 1
        elif character in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif character == "," and depth == 0:
            break
        index += 1
    return clean[start:index]


def _callback_body(segment: str) -> str | None:
    """`(e) => x` -> `x`；`(e) { ... }` -> `...`；不是回调字面量则 `None`。"""
    text = segment.strip()
    if not text.startswith("("):
        return None
    depth = 0
    rest = ""
    for index, character in enumerate(text):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                rest = text[index + 1 :].strip()
                break
    else:
        return None
    rest = rest.removeprefix("async").strip()
    if rest.startswith("=>"):
        return rest[2:].strip()
    if rest.startswith("{"):
        return rest[1:].rstrip().removesuffix("}")
    return None


def iter_business_dart_sources(
    lib_root: Path,
    app_root: Path,
) -> Iterator[tuple[str, str]]:
    """遍历业务 Dart 源，产出 `(相对路径, 已剥离注释与字符串的源码)`。

    generated 产物由 codegen 契约门禁负责，不进入手写代码的异常链路口径。
    """
    for path in sorted(lib_root.rglob("*.dart")):
        rel = path.relative_to(app_root).as_posix()
        if "/generated/" in rel or rel.endswith(".g.dart"):
            continue
        yield rel, strip_comments_and_strings(path.read_text(encoding="utf-8"))


def line_of(clean: str, offset: int) -> int:
    return clean.count("\n", 0, offset) + 1


#: 形如 `name(...) {` 或 `name(...) async {` 的声明起点。
#:
#: 参数表用非嵌套匹配：Dart 里带括号的参数（`int Function() cb`）少见，且回溯只需
#: 命中最近一处，漏掉一个签名会退化成「找不到函数名」，不会张冠李戴。
_ENCLOSING_DECLARATION = re.compile(
    r"(?<![\w$.])([A-Za-z_$]\w*)\s*\([^()]*\)\s*(?:async\*?|sync\*)?\s*\{"
)

#: 后面跟 `(...) {` 但不是函数的控制流关键字。
_CONTROL_FLOW = frozenset(
    {"if", "for", "while", "switch", "catch", "return", "else", "do", "on"}
)


def enclosing_declaration_name(clean: str, offset: int) -> str | None:
    """回溯 `offset` 之前最近的函数/方法名。

    用于让判定能看到「这个 catch 长在谁身上」。取不到名字时返回 `None`，调用方
    必须按最严格的分支处理，绝不能把「没识别出来」当成「符合约定」。
    """
    latest: str | None = None
    for match in _ENCLOSING_DECLARATION.finditer(clean, 0, offset):
        name = match.group(1)
        if name in _CONTROL_FLOW:
            continue
        latest = name
    return latest
