#!/usr/bin/env python3
"""Build a typed, evidence-backed closure graph for every Data JSON schema."""
from __future__ import annotations

import ast
import json
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator
from core.paths import REPO_ROOT

SCHEMA_SUFFIX = ".schema.json"
CALL_NAMES = frozenset({"assert_valid", "load_schema", "validate_result"})
SCHEMA_REGISTRY_SUFFIX = "_SCHEMAS"
SKIPPED_PARTS = frozenset({"test", "tests", "generated", ".qwq_output", ".git", "node_modules", "build", ".dart_tool", "vendor"})
LIVE_CATEGORIES = frozenset({"writer", "runtime_reader", "importer", "generator", "validator"})
ROOT_CATEGORIES = frozenset({"writer", "runtime_reader", "importer", "generator"})

@dataclass(frozen=True)
class SchemaNode:
    path: Path
    relative: str
    document: dict[str, Any]
    identities: frozenset[str]

@dataclass(frozen=True)
class Binding:
    schema: Path
    source: str
    category: str
    evidence: str

@dataclass(frozen=True)
class ClosureReport:
    issues: tuple[str, ...]
    schema_count: int
    scanned_files: int
    bindings: tuple[Binding, ...]
    category_counts: dict[str, int]


def _walk(value: object) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values(): yield from _walk(child)
    elif isinstance(value, list):
        for child in value: yield from _walk(child)


def _logical_identities(document: dict[str, Any]) -> set[str]:
    identities = {document["$id"]} if isinstance(document.get("$id"), str) and document["$id"] else set()
    def collect_root(node: object) -> None:
        if not isinstance(node, dict): return
        properties = node.get("properties")
        marker = properties.get("schema") if isinstance(properties, dict) else None
        if isinstance(marker, dict):
            if isinstance(marker.get("const"), str) and marker["const"]: identities.add(marker["const"])
            identities.update(value for value in marker.get("enum", []) if isinstance(value, str) and value)
        for keyword in ("allOf", "anyOf", "oneOf"):
            for branch in node.get(keyword, []) if isinstance(node.get(keyword), list) else (): collect_root(branch)
    collect_root(document)
    return identities


def load_nodes(repo_root: Path = REPO_ROOT) -> tuple[dict[Path, SchemaNode], list[str]]:
    schema_root = (repo_root / "quwoquan_data/schema").resolve(); nodes = {}; issues = []
    for path in sorted(schema_root.rglob(f"*{SCHEMA_SUFFIX}")):
        try: document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            issues.append(f"{path.relative_to(repo_root)}: invalid JSON: {error}"); continue
        if not isinstance(document, dict): issues.append(f"{path.relative_to(repo_root)}: schema root must be an object"); continue
        try: Draft202012Validator.check_schema(document)
        except Exception as error: issues.append(f"{path.relative_to(repo_root)}: invalid Draft 2020-12 schema: {error}")
        resolved = path.resolve(); nodes[resolved] = SchemaNode(resolved, resolved.relative_to(schema_root).as_posix(), document, frozenset(_logical_identities(document)))
    if not nodes: issues.append("quwoquan_data/schema: no schema files found")
    return nodes, issues


def schema_edges(nodes: dict[Path, SchemaNode], *, schema_root: Path | None = None) -> tuple[dict[Path, set[Path]], list[str]]:
    edges = {path: set() for path in nodes}; issues = []; boundary = (schema_root or next(iter(nodes)).parents[1]).resolve()
    for source, node in nodes.items():
        for item in _walk(node.document):
            reference = item.get("$ref")
            if not isinstance(reference, str) or reference.startswith("#"): continue
            target = (source.parent / reference.split("#", 1)[0]).resolve()
            try: target.relative_to(boundary)
            except ValueError: issues.append(f"{node.relative}: external $ref escapes Data schema root: {reference}"); continue
            if target not in nodes: issues.append(f"{node.relative}: dangling external $ref: {reference}"); continue
            edges[source].add(target)
    return edges, issues


def _cycle_issues(nodes: dict[Path, SchemaNode], edges: dict[Path, set[Path]]) -> list[str]:
    state = {}; stack = []; issues = []
    def visit(path: Path) -> None:
        if state.get(path) == 2: return
        if state.get(path) == 1:
            start = stack.index(path); issues.append("schema $ref cycle: " + " -> ".join(nodes[item].relative for item in stack[start:] + [path])); return
        state[path] = 1; stack.append(path)
        for target in sorted(edges[path]): visit(target)
        stack.pop(); state[path] = 2
    for path in sorted(nodes): visit(path)
    return issues


def _literal_pair(node: ast.AST) -> tuple[str, str] | None:
    if not isinstance(node, (ast.Tuple, ast.List)) or len(node.elts) != 2: return None
    if not all(isinstance(v, ast.Constant) and isinstance(v.value, str) for v in node.elts): return None
    return node.elts[0].value, node.elts[1].value


def _python_bindings(path: Path, by_relative: dict[str, Path], repo_root: Path) -> tuple[list[Binding], list[str]]:
    relative = path.relative_to(repo_root).as_posix(); issues = []; result = []
    try: tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, SyntaxError) as error: return [], [f"{relative}: production Python parse/read failed: {error}"]
    registries: dict[str, dict[str, Path]] = {}
    registry_aliases: dict[str, str] = {}
    for assignment in (n for n in ast.walk(tree) if isinstance(n, (ast.Assign, ast.AnnAssign))):
        targets = assignment.targets if isinstance(assignment, ast.Assign) else [assignment.target]
        names = [t.id for t in targets if isinstance(t, ast.Name) and t.id.endswith(SCHEMA_REGISTRY_SUFFIX)]
        if not names: continue
        if not isinstance(assignment.value, ast.Dict):
            continue
        entries = {}
        entry_issues: list[str] = []
        for key, value in zip(assignment.value.keys, assignment.value.values):
            pair = _literal_pair(value)
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str) or pair is None:
                entry_issues.append(f"{relative}:{assignment.lineno}: schema registry contains a non-literal entry"); continue
            target = by_relative.get(f"{pair[0]}/{pair[1]}{SCHEMA_SUFFIX}")
            if target is None: issues.append(f"{relative}:{assignment.lineno}: schema registry target does not exist: {pair[0]}/{pair[1]}"); continue
            entries[key.value] = target
        if entries:
            issues.extend(entry_issues)
            for name in names: registries[name] = entries
    for assignment in (n for n in ast.walk(tree) if isinstance(n, (ast.Assign, ast.AnnAssign))):
        targets = assignment.targets if isinstance(assignment, ast.Assign) else [assignment.target]
        if len(targets) != 1 or not isinstance(targets[0], ast.Name) or not isinstance(assignment.value, ast.Call):
            continue
        call = assignment.value
        if isinstance(call.func, ast.Attribute) and call.func.attr == "get" and isinstance(call.func.value, ast.Name) and call.func.value.id in registries:
            registry_aliases[targets[0].id] = call.func.value.id
    verify_only = "/scripts/verify/" in "/" + relative
    for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
        fn = call.func.id if isinstance(call.func, ast.Name) else call.func.attr if isinstance(call.func, ast.Attribute) else ""
        if fn not in CALL_NAMES: continue
        offset = 0 if fn == "load_schema" else 1; args = call.args[offset:offset + 2]
        targets: set[Path] = set()
        if len(args) == 2 and all(isinstance(v, ast.Constant) and isinstance(v.value, str) for v in args):
            target = by_relative.get(f"{args[0].value}/{args[1].value}{SCHEMA_SUFFIX}")
            if target is None: issues.append(f"{relative}:{call.lineno}: schema call target does not exist")
            else: targets.add(target)
        elif any(isinstance(a, ast.Starred) for a in call.args):
            starred = next(a.value for a in call.args if isinstance(a, ast.Starred))
            if isinstance(starred, ast.Name) and starred.id in registries:
                targets.update(registries[starred.id].values())
            elif isinstance(starred, ast.Name) and starred.id in registry_aliases:
                targets.update(registries[registry_aliases[starred.id]].values())
            elif isinstance(starred, ast.Subscript) and isinstance(starred.value, ast.Name) and starred.value.id in registries:
                key = starred.slice.value if isinstance(starred.slice, ast.Constant) else None
                target = registries[starred.value.id].get(key)
                if target is not None: targets.add(target)
                else: issues.append(f"{relative}:{call.lineno}: registry key is not a closed literal target")
            else:
                issues.append(f"{relative}:{call.lineno}: dynamic schema call is not traceable to a closed *_SCHEMAS registry")
        else:
            # Generic loader implementation is infrastructure, not a consumer edge.
            if relative != "quwoquan_data/scripts/core/schema.py": issues.append(f"{relative}:{call.lineno}: dynamic schema call is not traceable to a closed *_SCHEMAS registry")
            continue
        category = "verify-only" if verify_only else "runtime_reader"
        result.extend(Binding(t, relative, category, f"{fn}@{call.lineno}") for t in targets)
    return result, issues


def _go_import_bindings(repo_root: Path, by_relative: dict[str, Path]) -> tuple[list[Binding], list[str], int]:
    results = []; issues = []; scanned = 0
    for metadata in (repo_root / "quwoquan_service/services").glob("*/contracts/**/operations.yaml"):
        try: text = metadata.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error: issues.append(f"{metadata.relative_to(repo_root)}: metadata read failed: {error}"); continue
        if "external_schema_imports:" not in text: continue
        scanned += 1
        for match in re.finditer(r"- schema_path: (\S+)\n\s+loader_ref: (\S+)#(\w+)\n\s+validator_ref: (\S+)#(\w+)", text):
            schema_path, loader_path, loader_fn, validator_path, validator_fn = match.groups()
            prefix = "quwoquan_data/schema/"
            target = by_relative.get(schema_path.removeprefix(prefix)) if schema_path.startswith(prefix) else None
            if target is None: issues.append(f"{metadata.relative_to(repo_root)}: importer schema target does not exist: {schema_path}"); continue
            try: loader = (repo_root / loader_path).read_text(encoding="utf-8"); validator = (repo_root / validator_path).read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error: issues.append(f"{metadata.relative_to(repo_root)}: importer source read failed: {error}"); continue
            if not re.search(rf"func\s+{re.escape(loader_fn)}\b", loader) or not re.search(rf"\b{re.escape(validator_fn)}\s*\(", loader): issues.append(f"{metadata.relative_to(repo_root)}: loader does not call declared validator") ; continue
            if not re.search(rf"func\s+{re.escape(validator_fn)}\b", validator): issues.append(f"{metadata.relative_to(repo_root)}: declared validator function is absent"); continue
            results.append(Binding(target, metadata.relative_to(repo_root).as_posix(), "importer", f"{loader_fn}->{validator_fn}"))
    return results, issues, scanned


def _tombstone_issues(repo_root: Path, nodes: dict[Path, SchemaNode]) -> list[str]:
    path = repo_root / "quwoquan_data/control_plane/_shared/schema_retirement_tombstones.json"
    try: document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error: return [f"schema retirement tombstones unreadable: {error}"]
    retired_paths = set(); retired_ids = set(); issues = []
    for entry in document.get("entries", []):
        relative = entry.get("path"); identities = entry.get("identities")
        if not isinstance(relative, str) or not isinstance(identities, list): issues.append("schema retirement tombstone entry invalid"); continue
        if relative in retired_paths: issues.append(f"duplicate retired schema path tombstone: {relative}")
        retired_paths.add(relative); retired_ids.update(i for i in identities if isinstance(i, str))
        if (repo_root / "quwoquan_data/schema" / relative).exists(): issues.append(f"retired schema path restored: {relative}")
    for node in nodes.values():
        collision = sorted(node.identities & retired_ids)
        if collision: issues.append(f"{node.relative}: restores retired schema identity: {', '.join(collision)}")
    return issues


def _governed_migration_schema_groups(repo_root: Path) -> tuple[frozenset[str], ...]:
    """一次性受治理重物化允许旧输入闭包与现役输出共享 payload identity。"""
    path = repo_root / "quwoquan_ops/policies/gates/governed_schema_migration_boundaries.json"
    if not path.is_file():
        return ()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ()
    groups = []
    for boundary in document.get("boundaries") or []:
        relatives = set()
        for key in ("input_schemas", "input_closure", "output_schemas"):
            relatives.update(item for item in boundary.get(key) or [] if isinstance(item, str))
        for key in ("evidence_schema", "lineage_schema"):
            item = boundary.get(key)
            if isinstance(item, str):
                relatives.add(item)
        if relatives:
            groups.append(frozenset(relatives))
    return tuple(groups)


def _group_ref_closure(
    group: frozenset[str],
    nodes: dict[Path, SchemaNode],
    edges: dict[Path, set[Path]],
) -> set[str]:
    by_relative = {node.relative: path for path, node in nodes.items()}
    pending = [by_relative[relative] for relative in group if relative in by_relative]
    seen = set(pending)
    while pending:
        source = pending.pop()
        for target in edges.get(source, ()):
            if target not in seen:
                seen.add(target)
                pending.append(target)
    return {nodes[path].relative for path in seen} | set(group)


def build_report(repo_root: Path = REPO_ROOT) -> ClosureReport:
    nodes, issues = load_nodes(repo_root)
    if not nodes: return ClosureReport(tuple(issues), 0, 0, (), {})
    schema_root = (repo_root / "quwoquan_data/schema").resolve(); edges, edge_issues = schema_edges(nodes, schema_root=schema_root)
    issues.extend(edge_issues); issues.extend(_cycle_issues(nodes, edges)); issues.extend(_tombstone_issues(repo_root, nodes))
    owners: dict[str, list[SchemaNode]] = defaultdict(list)
    for node in nodes.values():
        if not node.identities and not any(node.path in targets for targets in edges.values()): issues.append(f"{node.relative}: identityless non-supporting authority")
        for identity in node.identities: owners[identity].append(node)
    migration_groups = _governed_migration_schema_groups(repo_root)
    for identity, matches in sorted(owners.items()):
        if len(matches) <= 1:
            continue
        relatives = {node.relative for node in matches}
        if any(relatives <= _group_ref_closure(group, nodes, edges) for group in migration_groups):
            continue
        issues.append(f"duplicate schema identity {identity!r}: " + ", ".join(n.relative for n in matches))
    by_relative = {n.relative: p for p, n in nodes.items()}; bindings = []; scanned = 0
    scripts_root = (repo_root / "quwoquan_data/scripts").resolve()
    for path in sorted(scripts_root.rglob("*.py")):
        # 只按相对 repo_root 的 segment 跳过；capsule 物化在 `.qwq_output/**/worktree`
        # 时绝对路径本身含 `.qwq_output`，不能把现役 scripts 全部扫成空集。
        try:
            relative_parts = path.resolve().relative_to(repo_root.resolve()).parts
        except ValueError:
            continue
        if any(part in SKIPPED_PARTS for part in relative_parts):
            continue
        scanned += 1; found, found_issues = _python_bindings(path, by_relative, repo_root); bindings.extend(found); issues.extend(found_issues)
    go_bindings, go_issues, go_scanned = _go_import_bindings(repo_root, by_relative); bindings.extend(go_bindings); issues.extend(go_issues); scanned += go_scanned
    roots = {b.schema for b in bindings if b.category in ROOT_CATEGORIES}; reachable = set(roots); pending = list(roots)
    while pending:
        source = pending.pop()
        for target in edges[source]:
            if target not in reachable: reachable.add(target); pending.append(target)
    for path, node in sorted(nodes.items(), key=lambda item: item[1].relative):
        if path not in reachable: issues.append(f"{node.relative}: no production consumer (writer/runtime_reader/importer/generator) and not supporting a live authority")
    # Static Alpha assets are instances only. If present, require the existing handoff freshness gate.
    alpha = repo_root / "quwoquan_app/assets/content/alpha/manifest.json"
    if alpha.is_file():
        completed = subprocess.run(["python3", "-B", "quwoquan_ops/cli/cloud_contract_handoff.py", "verify"], cwd=repo_root, capture_output=True, text=True)
        if completed.returncode: issues.append("App alpha instance provenance stale: existing app contract handoff verify failed")
    counts = Counter(b.category for b in bindings)
    return ClosureReport(tuple(issues), len(nodes), scanned, tuple(bindings), dict(sorted(counts.items())))


def production_roots(nodes: dict[Path, SchemaNode], repo_root: Path = REPO_ROOT) -> dict[Path, set[str]]:
    report = build_report(repo_root); roots: dict[Path, set[str]] = defaultdict(set)
    for binding in report.bindings:
        if binding.category in ROOT_CATEGORIES: roots[binding.schema].add(binding.source)
    return roots


def evaluate(repo_root: Path = REPO_ROOT) -> list[str]: return list(build_report(repo_root).issues)


def main() -> int:
    report = build_report(); print(f"[contract-closure] scanned={report.scanned_files} schemas={report.schema_count} bindings={len(report.bindings)} categories={json.dumps(report.category_counts, sort_keys=True)}")
    if report.issues:
        print("[contract-closure] FAIL")
        for issue in report.issues: print(f"  - {issue}")
        return 1
    print("[contract-closure] OK: every Data schema has a typed executable closure")
    return 0

if __name__ == "__main__": raise SystemExit(main())
