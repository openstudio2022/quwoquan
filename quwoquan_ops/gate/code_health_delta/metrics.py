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


def _brace_functions(text: str) -> list[FunctionMetric]:
    lines = text.splitlines()
    starts = re.compile(r"^\s*(?:func\s+(?:\([^)]*\)\s*)?|(?:[A-Za-z_][\w<>?\[\], ]+\s+)+)([A-Za-z_]\w*)\s*\([^;]*\)\s*(?:async\s*)?\{")
    results: list[FunctionMetric] = []
    for index, line in enumerate(lines):
        match = starts.search(line)
        if not match:
            continue
        depth = 0; end = index; branches = 0; cognitive = 0
        for cursor in range(index, len(lines)):
            current = lines[cursor]
            before = depth
            branches_here = len(re.findall(r"\b(?:if|for|while|case|catch)\b|&&|\|\|", current))
            branches += branches_here
            cognitive += branches_here * (1 + max(0, before - 1))
            depth += current.count("{") - current.count("}")
            end = cursor
            if cursor > index and depth <= 0:
                break
        results.append(FunctionMetric(match.group(1), index + 1, end + 1, 1 + branches, cognitive))
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


def duplicate_windows(
    candidate: bytes,
    corpus: Iterable[tuple[str, bytes]] = (),
    *,
    block_lines: int,
    baseline_index: dict[str, str] | None = None,
    changed_lines: frozenset[int] | None = None,
) -> tuple[int, str | None]:
    """Count unique candidate lines covered by matching changed windows."""
    lines = [_normalized_line(line) for line in candidate.decode("utf-8", "replace").splitlines()]
    indexed = baseline_index if baseline_index is not None else duplicate_window_index(corpus, block_lines=block_lines)
    changed = changed_lines or frozenset()
    covered: set[int] = set()
    sources: set[str] = set()
    for start in range(0, max(0, len(lines) - block_lines + 1)):
        window = lines[start:start + block_lines]
        if not all(window):
            continue
        line_numbers = set(range(start + 1, start + block_lines + 1))
        if changed and not line_numbers.intersection(changed):
            continue
        source = indexed.get(hashlib.sha256("\n".join(window).encode()).hexdigest())
        if source is not None:
            covered.update(line_numbers.intersection(changed) if changed else line_numbers)
            sources.add(source)
    return len(covered), min(sources) if sources else None


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
    patterns = (dotted, path, f"import {stem}", f"from {stem}")
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
