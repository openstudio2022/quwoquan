"""spec_ref 语法解析单轨防回潮锁。

全仓唯一 lexical 解析入口是 feature-tree 库（patterns.py 定义正则，
evidence.extract_spec_refs 提供状态机）；任何门禁/工具再定义第二套
spec_ref 解析正则都会形成静默漏计的第二真相源（R4 最终复审实证）。
本测试以 AST 级判据扫描全仓非测试 Python 源，锁死第五套解析器出现。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
ALLOWED = "quwoquan_ops/cli/lib/feature_tree/patterns.py"
SCAN_BASES = ("quwoquan_ops", "quwoquan_service", "quwoquan_data", "quwoquan_app")
# marker 解析型判据：pattern 文本含 `spec_ref:` 或 `spec_ref\s*:`（解析绑定语法），
# 关键词枚举 `(?:...|spec_ref)` 与语义锚点过滤 `(?:uat|dom|sit|gwt)-` 不触发。
_MARKER_PARSE = re.compile(r"spec_ref(?:\\s[*+])?:", re.IGNORECASE)


def _compile_literals(call: ast.Call) -> str:
    if not call.args:
        return ""
    return "".join(
        node.value
        for node in ast.walk(call.args[0])
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    )


def spec_ref_parser_compile_lines(source: str) -> list[int]:
    """返回源码中定义 spec_ref 语法解析正则的 re.compile 行号。

    判据（AST 级，对格式变化稳健）：pattern 字面量含 `specs/feature-tree`
    （spec 路径解析型），或含 `spec_ref:` 绑定语法（marker 解析型）。
    """
    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "compile"
            and isinstance(func.value, ast.Name)
            and func.value.id == "re"
        ):
            continue
        literals = _compile_literals(node)
        if "specs/feature-tree" in literals.lower() or _MARKER_PARSE.search(literals):
            lines.append(node.lineno)
    return lines


def _is_test_path(path: Path) -> bool:
    parts = set(path.parts)
    return (
        "tests" in parts
        or "test" in parts
        or path.name.startswith("test_")
        or path.name.endswith("_test.py")
    )


def test_repo_defines_spec_ref_parser_only_in_feature_tree_patterns() -> None:
    offenders: list[str] = []
    for base in SCAN_BASES:
        root = ROOT / base
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if _is_test_path(path) or "/generated/" in rel:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if "re.compile" not in text:
                continue
            if "spec_ref" not in text.lower() and "specs/feature-tree" not in text:
                continue
            try:
                found = spec_ref_parser_compile_lines(text)
            except SyntaxError:
                continue
            if found and rel != ALLOWED:
                offenders.append(f"{rel}:{found}")

    assert offenders == [], (
        f"spec_ref 语法解析只允许定义在 {ALLOWED}，其余消费方必须复用 "
        f"feature_tree.evidence.extract_spec_refs；违例: {', '.join(offenders)}"
    )
    # 判据自检：真相源自身必须命中，否则判据静默失效。
    allowed_hits = spec_ref_parser_compile_lines(
        (ROOT / ALLOWED).read_text(encoding="utf-8")
    )
    assert allowed_hits, "判据失效：feature-tree patterns.py 未被命中"


def test_detector_catches_legacy_parser_shapes_and_ignores_semantic_filters() -> None:
    """R4 实证的三种旧解析器形态必须检出；语义过滤与关键词枚举不误伤。

    fixture 内 token 与路径用源码级相邻字符串拆开，避免本文件被证据扫描器
    计入假绑定；AST 合并后判据看到的是完整 pattern 文本。
    """
    legacy_inline = (
        "import re\n"
        'X = re.compile(r"spec_" r"ref:\\s*(specs/feature-" r"tree/[^\\s#]+/spec\\.md)#")\n'
    )
    legacy_comment_prefix = (
        "import re\n"
        'Y = re.compile(r"(?m)^\\s*(?://|#)\\s*spec_" r"ref:\\s*")\n'
    )
    path_only = (
        "import re\n"
        'Z = re.compile(r"specs/feature-" r"tree/(?:[A-Za-z0-9_.-]+/)*spec\\.md#")\n'
    )
    assert spec_ref_parser_compile_lines(legacy_inline)
    assert spec_ref_parser_compile_lines(legacy_comment_prefix)
    assert spec_ref_parser_compile_lines(path_only)

    semantic_anchor_filter = (
        "import re\n"
        'A = re.compile(r"^((?:uat|dom|sit|gwt)-\\d+)(?:\\.t\\d+)?$")\n'
    )
    keyword_enum = (
        "import re\n"
        'B = re.compile(r"(?:local_contract|api_integration|spec_" r"ref)")\n'
    )
    assert spec_ref_parser_compile_lines(semantic_anchor_filter) == []
    assert spec_ref_parser_compile_lines(keyword_enum) == []
