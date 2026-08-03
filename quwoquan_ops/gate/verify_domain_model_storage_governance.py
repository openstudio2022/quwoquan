#!/usr/bin/env python3
"""领域对象存储唯一归属与跨服务旁路静态门。

只读取受版本控制的 `storage.yaml` 与生产源码。测试、生成物和 contracts 本身不作为
运行时访问证据；发现未声明、多 owner 或跨服务直连时 fail-closed。
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml


_SQL_TABLE = re.compile(
    r"\b(?:(?<!DISTINCT\s)FROM|JOIN|INSERT\s+INTO|(?<!DO\s)(?<!FOR\s)UPDATE|DELETE\s+FROM)\s+"
    r"(?:[a-zA-Z_][a-zA-Z0-9_]*\.)?[\"`]?([a-z][a-z0-9_]*)[\"`]?",
    re.IGNORECASE,
)
_PYTHON_STREAM_METHODS = {
    "xadd": "write",
    "xdel": "write",
    "xtrim": "write",
    "xack": "read",
    "xclaim": "read",
    "xgroup_create": "read",
    "xautoclaim": "read",
    "xpending": "read",
    "xread": "read",
    "xreadgroup": "read",
}
_PYTHON_REDIS_KEY_METHODS = {
    "delete",
    "expire",
    "get",
    "hdel",
    "hget",
    "hset",
    "sadd",
    "set",
    "setnx",
    "srem",
    "zadd",
    "zrem",
    "zscore",
}

_SQL_MARKERS = (
    "database/sql",
    "pgx",
    "postgres",
    "psycopg",
    "asyncpg",
    "sqlalchemy",
)
_SQL_NON_BUSINESS_NAMES = {
    "excluded",
    "information_schema",
    "pg_catalog",
    "unnest",
    "values",
}


def _source_string_literals(source: str, suffix: str) -> Iterable[str]:
    """只返回源码字面量，避免把注释/标识符中的 FROM/UPDATE 当 SQL。"""
    if suffix == ".go":
        yield from re.findall(r"`([^`]*)`", source, re.DOTALL)
        return
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value


def _sql_tables(source: str, suffix: str) -> Iterable[str]:
    for literal in _source_string_literals(source, suffix):
        if not re.search(
            r"\b(?:SELECT|INSERT|UPDATE|DELETE|WITH)\b", literal, re.IGNORECASE
        ):
            continue
        cte_names = {
            name.lower()
            for name in re.findall(
                r"(?:\bWITH\b|,)\s*([a-z][a-z0-9_]*)\s+AS\s*\(",
                literal,
                re.IGNORECASE,
            )
        }
        for name in _SQL_TABLE.findall(literal):
            normalized = name.lower()
            if normalized in _SQL_NON_BUSINESS_NAMES or normalized in cte_names:
                continue
            yield normalized


@dataclass(frozen=True)
class StorageOwner:
    kind: str
    name: str
    service: str
    path: str
    writers: tuple[str, ...] = ()


@dataclass(frozen=True)
class StorageReference:
    kind: str
    name: str
    service: str
    path: str
    access: str = "read_write"


def _scan_go_storage_references(root: Path) -> list[StorageReference]:
    service_root = root / "quwoquan_service"
    scanner = service_root / "tools" / "storage_reference_scan"
    if not scanner.is_dir():
        # Unit tests pass a synthetic repository root; the scanner itself remains
        # the checked-in executable owned by this gate.
        scanner = (
            Path(__file__).resolve().parents[2]
            / "quwoquan_service"
            / "tools"
            / "storage_reference_scan"
        )
        service_root = scanner.parents[1]
    completed = subprocess.run(
        [
            "go",
            "run",
            "./tools/storage_reference_scan",
            "--repo-root",
            str(root),
        ],
        cwd=service_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"Go storage AST scanner failed: {detail}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Go storage AST scanner returned invalid JSON: {exc}") from exc
    services_root = root / "quwoquan_service" / "services"
    result: list[StorageReference] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        relative = str(item.get("path", ""))
        path = root / relative
        try:
            service = _service_name(path, services_root)
        except (ValueError, IndexError):
            continue
        result.append(
            StorageReference(
                kind=str(item.get("kind", "")),
                name=str(item.get("name", "")),
                service=service,
                path=relative,
                access=str(item.get("access", "read_write")),
            )
        )
    return result


def _python_string_constants(tree: ast.AST) -> dict[str, str]:
    constants: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = node.value
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                constants[target.id] = value.value
    return constants


def _python_static_string(node: ast.AST, constants: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _python_static_string(node.left, constants)
        right = _python_static_string(node.right, constants)
        if left is not None and right is not None:
            return left + right
    return None


def _python_static_prefix(node: ast.AST, constants: dict[str, str]) -> str | None:
    """Resolve the stable prefix of a string or f-string storage identity."""
    value = _python_static_string(node, constants)
    if value is not None:
        return value
    if not isinstance(node, ast.JoinedStr):
        return None
    parts: list[str] = []
    for item in node.values:
        if isinstance(item, ast.Constant) and isinstance(item.value, str):
            parts.append(item.value)
            continue
        break
    prefix = "".join(parts)
    return prefix or None


def _python_call_static_values(
    node: ast.Call,
    constants: dict[str, str],
) -> Iterable[str]:
    for argument in node.args:
        if value := _python_static_prefix(argument, constants):
            yield value
        if isinstance(argument, ast.Dict):
            for key in argument.keys:
                if key is not None and (
                    value := _python_static_prefix(key, constants)
                ):
                    yield value
    for keyword in node.keywords:
        if value := _python_static_prefix(keyword.value, constants):
            yield value


def _python_attribute_path(node: ast.AST) -> str:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts)).lower()


def _python_is_redis_receiver(node: ast.AST) -> bool:
    path = _python_attribute_path(node)
    return any(token in path for token in ("redis", "cache"))


def _python_lookup_collections(
    tree: ast.AST,
    constants: dict[str, str],
) -> Iterable[str]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        fields: dict[str, ast.AST] = {}
        for key, value in zip(node.keys, node.values):
            if key is None:
                continue
            resolved = _python_static_string(key, constants)
            if resolved is not None:
                fields[resolved] = value
        lookup = fields.get("$lookup")
        if not isinstance(lookup, ast.Dict):
            continue
        for key, value in zip(lookup.keys, lookup.values):
            if key is None or _python_static_string(key, constants) != "from":
                continue
            collection = _python_static_string(value, constants)
            if collection:
                yield collection


def _scan_python_storage_references(
    source: str,
    service: str,
    relative: str,
) -> set[StorageReference]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    constants = _python_string_constants(tree)
    result: set[StorageReference] = set()
    for name in _python_lookup_collections(tree, constants):
        result.add(StorageReference("collection", name, service, relative, "read"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            owner = node.value
            if isinstance(owner, ast.Name) and owner.id in {
                "db",
                "database",
                "mongo_db",
            }:
                name = _python_static_string(node.slice, constants)
                if name:
                    result.add(StorageReference("collection", name, service, relative))
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        method = node.func.attr.lower()
        if method in {"get_collection", "collection"} and node.args:
            name = _python_static_string(node.args[0], constants)
            if name:
                result.add(StorageReference("collection", name, service, relative))
            continue
        if method in _PYTHON_STREAM_METHODS:
            for value in _python_call_static_values(node, constants):
                if value.startswith("events."):
                    result.add(
                        StorageReference(
                            "stream",
                            value,
                            service,
                            relative,
                            _PYTHON_STREAM_METHODS[method],
                        )
                    )
            continue
        if method in _PYTHON_REDIS_KEY_METHODS and _python_is_redis_receiver(
            node.func.value
        ):
            for value in _python_call_static_values(node, constants):
                if _looks_like_redis_key(value):
                    result.add(
                        StorageReference("redis_key", value, service, relative)
                    )
    return result


def _looks_like_redis_key(value: str) -> bool:
    if re.match(r"^[a-z][a-z0-9+.-]*://", value, re.IGNORECASE):
        return False
    prefix, separator, _remainder = value.partition(":")
    return bool(
        separator
        and re.fullmatch(r"[a-z][a-z0-9_-]*", prefix)
    )


def _service_name(path: Path, services_root: Path) -> str:
    return path.relative_to(services_root).parts[0]


def _mapping_names(value: object) -> Iterable[str]:
    if isinstance(value, dict):
        for name in value:
            if isinstance(name, str) and name.strip():
                yield name.strip()
        return
    if isinstance(value, list):
        for entry in value:
            if isinstance(entry, dict):
                name = entry.get("name")
                if isinstance(name, str) and name.strip():
                    yield name.strip()


def _mapping_entries(value: object) -> Iterable[tuple[str, dict[str, object]]]:
    if isinstance(value, dict):
        for name, config in value.items():
            if not isinstance(name, str) or not name.strip():
                continue
            yield name.strip(), config if isinstance(config, dict) else {}
        return
    if isinstance(value, list):
        for entry in value:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if isinstance(name, str) and name.strip():
                yield name.strip(), entry


def _declared_key_prefix(key: str) -> str:
    marker = key.find("{")
    return key if marker < 0 else key[:marker]


def load_storage_owners(root: Path) -> dict[tuple[str, str], list[StorageOwner]]:
    services_root = root / "quwoquan_service" / "services"
    owners: dict[tuple[str, str], list[StorageOwner]] = {}
    for path in sorted(services_root.glob("*/contracts/**/storage.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(document, dict):
            continue
        service = _service_name(path, services_root)
        relative = path.relative_to(root).as_posix()
        for kind, field in (
            ("collection", "collections"),
            ("table", "tables"),
        ):
            for name in _mapping_names(document.get(field)):
                owners.setdefault((kind, name), []).append(
                    StorageOwner(kind, name, service, relative)
                )
        for name, config in _mapping_entries(document.get("streams")):
            raw_writers = config.get("writers") or []
            writers = tuple(
                sorted(
                    {
                        writer.strip()
                        for writer in raw_writers
                        if isinstance(writer, str) and writer.strip()
                    }
                )
            ) if isinstance(raw_writers, list) else ()
            owners.setdefault(("stream", name), []).append(
                StorageOwner("stream", name, service, relative, writers)
            )
        redis_cache = document.get("redis_cache") or []
        if isinstance(redis_cache, list):
            for entry in redis_cache:
                if not isinstance(entry, dict):
                    continue
                key = entry.get("key")
                if not isinstance(key, str) or not key.strip():
                    continue
                prefix = _declared_key_prefix(key.strip())
                owners.setdefault(("redis_key", prefix), []).append(
                    StorageOwner("redis_key", prefix, service, relative)
                )
    return owners


def _production_sources(root: Path) -> Iterable[Path]:
    services_root = root / "quwoquan_service" / "services"
    for path in services_root.rglob("*"):
        if not path.is_file() or path.suffix not in {".go", ".py"}:
            continue
        relative = path.relative_to(services_root).as_posix()
        if any(part in {"tests", "test", "generated", "contracts"} for part in path.parts):
            continue
        if "/vendor/" in f"/{relative}":
            continue
        yield path


def scan_storage_references(root: Path) -> list[StorageReference]:
    services_root = root / "quwoquan_service" / "services"
    references: set[StorageReference] = set(_scan_go_storage_references(root))
    for path in _production_sources(root):
        source = path.read_text(encoding="utf-8", errors="ignore")
        service = _service_name(path, services_root)
        relative = path.relative_to(root).as_posix()
        if path.suffix == ".py":
            references.update(
                _scan_python_storage_references(source, service, relative)
            )

        if any(marker in source for marker in _SQL_MARKERS):
            for name in _sql_tables(source, path.suffix):
                references.add(StorageReference("table", name, service, relative))

    return sorted(
        references,
        key=lambda item: (item.kind, item.name, item.service, item.path, item.access),
    )


def collect_storage_governance_issues(root: Path) -> list[str]:
    owners = load_storage_owners(root)
    try:
        references = scan_storage_references(root)
    except RuntimeError as exc:
        return [str(exc)]
    issues: list[str] = []

    for (kind, name), declared in sorted(owners.items()):
        unique_paths = sorted({owner.path for owner in declared})
        if len(unique_paths) > 1:
            issues.append(
                f"storage {kind} {name!r} has multiple owners: "
                + ", ".join(unique_paths)
            )

    redis_owners = [
        owner
        for (kind, _), declared in owners.items()
        if kind == "redis_key"
        for owner in declared
    ]
    for reference in references:
        declared = owners.get((reference.kind, reference.name), [])
        if reference.kind == "redis_key" and not declared:
            declared = [
                owner
                for owner in redis_owners
                if reference.name.startswith(owner.name)
            ]
        if not declared:
            issues.append(
                f"{reference.path} accesses undeclared {reference.kind} "
                f"{reference.name!r}"
            )
            continue
        owner_services = sorted({owner.service for owner in declared})
        if reference.kind == "stream" and reference.access == "read":
            continue
        if reference.kind == "stream" and reference.access == "write":
            allowed_writers = {
                writer
                for owner in declared
                for writer in owner.writers
            }
            if reference.service in allowed_writers:
                continue
        if owner_services != [reference.service]:
            issues.append(
                f"{reference.path} accesses {reference.kind} {reference.name!r} "
                f"owned by {', '.join(owner_services)}"
            )
    return sorted(set(issues))


if __name__ == "__main__":
    import sys

    repository_root = Path(__file__).resolve().parents[2]
    failures = collect_storage_governance_issues(repository_root)
    if failures:
        print("[verify-domain-model-storage-governance] FAIL")
        for failure in failures:
            print(f"  - {failure}")
        raise SystemExit(1)
    print("[verify-domain-model-storage-governance] OK")
    raise SystemExit(0)
