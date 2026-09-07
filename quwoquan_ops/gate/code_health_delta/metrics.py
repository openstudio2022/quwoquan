"""Deterministic builtin health metrics; optional external tools are advisory."""
from __future__ import annotations

import ast
import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .git_delta import blob, index_blob, working_tree_blob


@dataclass(frozen=True)
class FunctionMetric:
    name: str
    start: int
    end: int
    cyclomatic: int
    cognitive: int


def line_count(body: bytes | None) -> int:
    if not body:
        return 0
    return len(body.decode("utf-8", "replace").splitlines())


def _python_functions(text: str) -> list[FunctionMetric]:
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        raise ValueError(f"Python source syntax unavailable for complexity analysis: {error}") from error
    metrics: list[FunctionMetric] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        cyclomatic = 1
        cognitive = 0
        stack: list[tuple[ast.AST, int]] = [(node, 0)]
        while stack:
            current, depth = stack.pop()
            branch = isinstance(current, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp, ast.comprehension, ast.ExceptHandler, ast.Match))
            if branch and current is not node:
                cyclomatic += 1
                cognitive += 1 + depth
            if isinstance(current, ast.BoolOp):
                extra = max(0, len(current.values) - 1)
                cyclomatic += extra
                cognitive += extra
            next_depth = depth + 1 if branch else depth
            stack.extend((child, next_depth) for child in ast.iter_child_nodes(current))
        metrics.append(FunctionMetric(node.name, node.lineno, getattr(node, "end_lineno", node.lineno), cyclomatic, cognitive))
    return metrics


#: 控制流关键字出现在「函数头」位置时不是函数：`if len(x) == cap(x) {` 的 `len`
#: 曾被当作函数统计。
_CONTROL_KEYWORDS = frozenset({
    "if", "else", "for", "while", "switch", "return", "case", "catch", "do", "try",
    "defer", "go", "select", "await", "yield", "throw",
})
#: 函数头：`func (recv) Name(params) ReturnType {`、`Type name(params) async {`、`name() {`。
#: `)` 与 `{` 之间允许 Go 的裸返回类型或 Dart 的 `async`，但不允许 `;`/`{`。
_FUNCTION_START = re.compile(
    r"^\s*(?:func\s+(?:\([^)]*\)\s*)?|(?P<prefix>(?:[A-Za-z_][\w<>?\[\], ]+\s+)+))"
    r"(?P<name>[A-Za-z_]\w*)\s*\([^;]*\)\s*[^{;]*\{"
)
_BRANCH_TOKEN = re.compile(r"\b(?:if|for|while|case|catch)\b|&&|\|\|")


def _newlines_only(fragment: str) -> str:
    return "\n" * fragment.count("\n")


def _skip_block(text: str, start: int, terminator: str, *, keep_terminator: bool) -> tuple[str, int]:
    """Blank a span up to ``terminator``; return the replacement and the index after it."""
    end = text.find(terminator, start)
    if end < 0:
        return _newlines_only(text[start:]), len(text)
    replacement = _newlines_only(text[start:end]) + (terminator if keep_terminator else "")
    return replacement, end + len(terminator)


def _skip_quoted(text: str, start: int, quote: str) -> tuple[str, int]:
    """Blank a string body: Go raw strings may span lines, other literals stop at newline."""
    if quote == "`":
        return _skip_block(text, start, "`", keep_terminator=True)
    index = start
    while index < len(text) and text[index] not in (quote, "\n"):
        index += 2 if text[index] == "\\" else 1
    if index < len(text) and text[index] == quote:
        return quote, index + 1
    return "", index


def strip_code_noise(text: str) -> str:
    """Blank out string literal bodies and comments while preserving line structure.

    Brace/branch counting on raw text treats ``if`` inside a log message or a ``{`` inside a
    template string as code. Quotes and newlines are kept so line numbers stay stable.
    """
    out: list[str] = []
    index = 0
    while index < len(text):
        two = text[index:index + 2]
        three = text[index:index + 3]
        if two == "//":
            replacement, index = _skip_block(text, index, "\n", keep_terminator=True)
        elif two == "/*":
            replacement, index = _skip_block(text, index + 2, "*/", keep_terminator=False)
        elif three in {'"""', "'''"}:
            body, index = _skip_block(text, index + 3, three, keep_terminator=False)
            replacement = three + body + three
        elif text[index] in {'"', "'", "`"}:
            quote = text[index]
            body, index = _skip_quoted(text, index + 1, quote)
            replacement = quote + body
        else:
            replacement, index = text[index], index + 1
        out.append(replacement)
    return "".join(out)


def _brace_functions(text: str) -> list[FunctionMetric]:
    lines = strip_code_noise(text).splitlines()
    results: list[FunctionMetric] = []
    for index, line in enumerate(lines):
        match = _FUNCTION_START.search(line)
        if not match:
            continue
        prefix_tokens = (match.group("prefix") or "").split()
        name = match.group("name")
        if name in _CONTROL_KEYWORDS or any(token in _CONTROL_KEYWORDS for token in prefix_tokens):
            continue
        depth = 0; end = index; branches = 0; cognitive = 0
        for cursor in range(index, len(lines)):
            current = lines[cursor]
            before = depth
            branches_here = len(_BRANCH_TOKEN.findall(current))
            branches += branches_here
            cognitive += branches_here * (1 + max(0, before - 1))
            depth += current.count("{") - current.count("}")
            end = cursor
            if cursor > index and depth <= 0:
                break
        results.append(FunctionMetric(name, index + 1, end + 1, 1 + branches, cognitive))
    return results


def function_metrics(path: str, body: bytes | None) -> list[FunctionMetric]:
    if body is None:
        return []
    text = body.decode("utf-8", "replace")
    return _python_functions(text) if path.endswith(".py") else _brace_functions(text)


def changed_complexity_findings(path: str, old_body: bytes | None, new_body: bytes | None, changed_lines: frozenset[int], cyclomatic_limit: int, cognitive_limit: int) -> list[dict[str, object]]:
    old = {item.name: item for item in function_metrics(path, old_body)}
    findings = []
    for metric in function_metrics(path, new_body):
        if changed_lines and not any(metric.start <= line <= metric.end for line in changed_lines):
            continue
        previous = old.get(metric.name)
        worsened = previous is None or metric.cyclomatic > previous.cyclomatic or metric.cognitive > previous.cognitive
        if worsened and (metric.cyclomatic > cyclomatic_limit or metric.cognitive > cognitive_limit):
            findings.append({
                "code": "CODE_HEALTH.COMPLEXITY_ADVISORY", "path": path,
                "symbol": metric.name, "terminal": "PR_WARN",
                "message": f"changed function complexity cyclomatic={metric.cyclomatic} cognitive={metric.cognitive} exceeds advisory {cyclomatic_limit}/{cognitive_limit}",
                "measure": {"cyclomatic": metric.cyclomatic, "cognitive": metric.cognitive,
                            "previousCyclomatic": None if previous is None else previous.cyclomatic,
                            "previousCognitive": None if previous is None else previous.cognitive},
            })
    return findings


def _normalized_line(line: str) -> str:
    stripped = re.sub(r"\s+", " ", line.strip())
    return "" if not stripped or stripped.startswith(("#", "//", "/*", "*")) else stripped


def reuse_scope_key(path: str) -> str:
    """Derive a bounded structural reuse scope without inventing an owner registry."""
    parts = Path(path).as_posix().split("/")
    if len(parts) >= 3 and parts[:2] == ["quwoquan_service", "services"]:
        return "/".join(parts[:3])
    if len(parts) >= 4 and parts[:2] == ["quwoquan_app", "lib"] and parts[2] == "service":
        return "/".join(parts[:4])
    if len(parts) >= 3 and parts[:2] in (["quwoquan_app", "lib"], ["quwoquan_data", "scripts"], ["quwoquan_ops", "portal"]):
        return "/".join(parts[:3])
    if len(parts) >= 2 and parts[0] == "quwoquan_ops":
        return "/".join(parts[:2])
    return "/".join(parts[:2]) if len(parts) >= 2 else parts[0]


def duplicate_window_index(corpus: Iterable[tuple[str, bytes]], *, block_lines: int) -> dict[str, str]:
    """Index one bounded baseline corpus once for all changed candidates."""
    indexed: dict[str, str] = {}
    for path, body in corpus:
        lines = [_normalized_line(line) for line in body.decode("utf-8", "replace").splitlines()]
        for start in range(0, max(0, len(lines) - block_lines + 1)):
            window = lines[start:start + block_lines]
            if all(window):
                digest = hashlib.sha256("\n".join(window).encode()).hexdigest()
                indexed.setdefault(digest, path)
    return indexed


def _candidate_windows(candidate: bytes, *, block_lines: int) -> list[tuple[str, set[int]]]:
    lines = [_normalized_line(line) for line in candidate.decode("utf-8", "replace").splitlines()]
    windows: list[tuple[str, set[int]]] = []
    for start in range(0, max(0, len(lines) - block_lines + 1)):
        window = lines[start:start + block_lines]
        if not all(window):
            continue
        digest = hashlib.sha256("\n".join(window).encode()).hexdigest()
        windows.append((digest, set(range(start + 1, start + block_lines + 1))))
    return windows


def duplicate_windows(
    candidate: bytes,
    *,
    block_lines: int,
    baseline_index: dict[str, str],
    changed_lines: frozenset[int],
) -> tuple[frozenset[int], str | None]:
    """Changed candidate lines whose window already exists in the baseline corpus.

    只度量 ``changed_lines``：没有新增行的候选（纯删除）得到空集合，绝不退化为整文件，
    否则只删几行的文件会把全部旧内容当作“新重复”计入。
    """
    covered: set[int] = set()
    sources: set[str] = set()
    for digest, line_numbers in _candidate_windows(candidate, block_lines=block_lines):
        touched = line_numbers.intersection(changed_lines)
        source = baseline_index.get(digest) if touched else None
        if source is not None:
            covered.update(touched)
            sources.add(source)
    return frozenset(covered), (min(sources) if sources else None)


def candidate_duplicate_windows(
    candidates: list[tuple[str, bytes, frozenset[int]]], *, block_lines: int,
) -> dict[str, tuple[frozenset[int], str]]:
    """Changed lines whose window also appears elsewhere inside the same candidate.

    A window counts when it recurs in another changed file or at a second offset of the same
    file. Only changed lines are attributed so untouched context never inflates the ratio;
    a candidate with no new lines contributes nothing.
    """
    per_path = {path: _candidate_windows(body, block_lines=block_lines) for path, body, _ in candidates}
    occurrences: dict[str, list[tuple[str, set[int]]]] = {}
    for path, windows in per_path.items():
        for digest, line_numbers in windows:
            occurrences.setdefault(digest, []).append((path, line_numbers))
    result: dict[str, tuple[frozenset[int], str]] = {}
    for path, _body, changed in candidates:
        covered: set[int] = set()
        sources: set[str] = set()
        for digest, line_numbers in per_path[path]:
            touched = line_numbers.intersection(changed)
            others = {
                other_path for other_path, other_lines in occurrences[digest]
                if other_path != path or other_lines.isdisjoint(line_numbers)
            }
            if touched and others:
                covered.update(touched)
                sources.update(others)
        if covered:
            result[path] = (frozenset(covered), min(sources))
    return result


def tracked_paths(repo: Path, sha: str) -> list[str]:
    result = subprocess.run(["git", "ls-tree", "-r", "--name-only", "-z", sha], cwd=repo, check=True, capture_output=True)
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def has_repository_entry(repo: Path, head: str, path: str, *, working_tree: bool = False, index_only: bool = False) -> bool:
    if path.endswith("/__init__.py") or Path(path).name in {"cli.py", "stackctl.py"}:
        return True
    body = (
        index_blob(repo, path)
        if index_only
        else working_tree_blob(repo, path)
        if working_tree
        else blob(repo, head, path)
    ) or b""
    if b'__name__ == "__main__"' in body or b"__name__ == '__main__'" in body:
        return True
    dotted = path[:-3].replace("/", ".")
    stem = Path(path).stem
    # 包内相对导入（`from .stem import`、`from ..pkg.stem import`）与 `from . import stem`
    # 是 Data package 最常见的入口形态；只查绝对 dotted path 会把它们全部误判为无入口。
    patterns = (dotted, path, f"import {stem}", f"from {stem}", f".{stem} import")
    command = ["git", "grep", "-F", "-q"]
    for pattern in patterns:
        command.extend(["-e", pattern])
    if index_only:
        command.append("--cached")
    elif not working_tree:
        command.append(head)
    command.extend(["--", "*.py", "*.sh", "*.go", "*.dart", "*.yaml", "*.yml", "*.md", "Makefile"])
    matched = subprocess.run(command, cwd=repo, capture_output=True, check=False)
    if matched.returncode == 0:
        return True
    if matched.returncode not in {1}:
        raise ValueError(matched.stderr.decode("utf-8", "replace").strip() or "git grep failed")
    if working_tree and not index_only:
        # git grep does not see untracked entry files; bound this fallback to untracked files only.
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=repo, capture_output=True, check=True,
        ).stdout.split(b"\0")
        for raw_source in untracked:
            if not raw_source:
                continue
            source = raw_source.decode("utf-8", "replace")
            if source == path or not source.endswith((".py", ".sh", ".go", ".dart", ".yaml", ".yml", ".md")):
                continue
            try:
                text = (repo / source).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if any(pattern in text for pattern in patterns):
                return True
    return False


def executable_magic(body: bytes | None) -> str | None:
    if body is None:
        return None
    if body.startswith(b"\x7fELF"):
        return "ELF"
    if body[:4] in {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}:
        return "Mach-O"
    if body.startswith(b"MZ"):
        return "PE"
    return None
