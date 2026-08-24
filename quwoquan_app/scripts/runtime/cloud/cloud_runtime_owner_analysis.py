"""`verify_cloud_runtime_single_path` 的 adapter owner 发现与归属分析。

主 gate 负责判定与报告，本模块只回答「哪些 Dart 文件是 canonical adapter、
它们各自引用了哪些 generated operation」这一类事实问题。
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable, NamedTuple

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import REPO_ROOT  # noqa: E402

ROOT = REPO_ROOT
DART_NON_CODE_RE = re.compile(
    r"//[^\n]*"
    r"|/\*.*?\*/"
    r"|'''.*?'''"
    r'|""".*?"""'
    r"|r?'(?:\\.|[^'\\])*'"
    r'|r?"(?:\\.|[^"\\])*"',
    re.DOTALL,
)

GENERATED_CLIENT_BINDING_RE = re.compile(
    r"\b(?:[A-Za-z_][A-Za-z0-9_]*\s*\.\s*)?"
    r"GeneratedCloudOperationClient\s+([A-Za-z_][A-Za-z0-9_]*)\b"
)
GENERATED_UPGRADE_ID_RE = re.compile(
    r"\b(?:AppCloudOperationIds|AppCloudOperationUpgradeDescriptors)"
    r"\s*\.\s*([A-Za-z][A-Za-z0-9_]*)\b"
)
WEBSOCKET_UPGRADE_EXECUTOR_RE = re.compile(
    r"\bWebSocketChannel\s*\.\s*connect\s*\("
)

class OwnerReport(NamedTuple):
    canonical_paths: tuple[Path, ...]
    legacy_paths: tuple[Path, ...]
    canonical_owners: dict[str, tuple[Path, ...]]
    legacy_references: dict[str, tuple[Path, ...]]
    missing: frozenset[str]
    duplicates: dict[str, tuple[Path, ...]]
    legacy_only: frozenset[str]
    legacy_overlap: frozenset[str]
    non_ready: frozenset[str]
    legacy_non_ready: frozenset[str]


class UpgradeOwnerReport(NamedTuple):
    canonical_paths: tuple[Path, ...]
    legacy_paths: tuple[Path, ...]
    canonical_owners: dict[str, tuple[Path, ...]]
    legacy_references: dict[str, tuple[Path, ...]]
    executors: dict[str, tuple[Path, ...]]
    missing: frozenset[str]
    duplicates: dict[str, tuple[Path, ...]]
    legacy_only: frozenset[str]
    legacy_overlap: frozenset[str]
    missing_executors: frozenset[str]


def _without_dart_non_code(source: str) -> str:
    """Remove comments and strings while preserving source line numbers."""

    def replace(match: re.Match[str]) -> str:
        newline_count = match.group(0).count("\n")
        return "\n" * newline_count if newline_count else " "

    return DART_NON_CODE_RE.sub(replace, source)


def _display_path(path: Path, repo_root: Path = ROOT) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _canonical_adapter_paths(app_root: Path) -> tuple[Path, ...]:
    """Discover only exact service/<domain>/<context>/<object>/adapters files."""

    lib_root = app_root / "lib"
    paths: set[Path] = set()
    for adapter_root in lib_root.glob("service/*/*/*/adapters"):
        if adapter_root.is_dir():
            paths.update(adapter_root.rglob("*.dart"))
    return tuple(sorted(paths))


def _legacy_cloud_paths(app_root: Path) -> tuple[Path, ...]:
    paths: set[Path] = set()
    for legacy_root in (
        app_root / "lib/cloud/remote",
        app_root / "lib/cloud/services",
    ):
        if legacy_root.is_dir():
            paths.update(legacy_root.rglob("*.dart"))
    return tuple(sorted(paths))


def _typed_generated_method_references(source: str) -> frozenset[str]:
    code = _without_dart_non_code(source)
    bindings = set(GENERATED_CLIENT_BINDING_RE.findall(code))
    methods: set[str] = set()
    for binding in bindings:
        method_re = re.compile(
            rf"(?<![A-Za-z0-9_])(?:this\s*\.\s*)?{re.escape(binding)}"
            r"\s*\.\s*([A-Za-z][A-Za-z0-9_]*)\s*\("
        )
        methods.update(method_re.findall(code))
    return frozenset(methods)


def _collect_method_references(
    paths: Iterable[Path],
) -> dict[str, tuple[Path, ...]]:
    references: defaultdict[str, set[Path]] = defaultdict(set)
    for source_path in paths:
        source = source_path.read_text(encoding="utf-8")
        for method in _typed_generated_method_references(source):
            references[method].add(source_path)
    return {
        method: tuple(sorted(owner_paths))
        for method, owner_paths in sorted(references.items())
    }


def _collect_upgrade_references(
    paths: Iterable[Path],
    generated_upgrades: Iterable[str],
) -> dict[str, tuple[Path, ...]]:
    ready_upgrades = frozenset(generated_upgrades)
    references: defaultdict[str, set[Path]] = defaultdict(set)
    for source_path in paths:
        code = _without_dart_non_code(source_path.read_text(encoding="utf-8"))
        for identifier in GENERATED_UPGRADE_ID_RE.findall(code):
            if identifier in ready_upgrades:
                references[identifier].add(source_path)
    return {
        identifier: tuple(sorted(owner_paths))
        for identifier, owner_paths in sorted(references.items())
    }


def _collect_upgrade_executors(
    canonical_paths: Iterable[Path],
    owners: dict[str, tuple[Path, ...]],
) -> dict[str, tuple[Path, ...]]:
    paths = tuple(canonical_paths)
    result: dict[str, tuple[Path, ...]] = {}
    for identifier, owner_paths in owners.items():
        owner_directories = {path.parent for path in owner_paths}
        executors = tuple(
            sorted(
                path
                for path in paths
                if path.parent in owner_directories
                and WEBSOCKET_UPGRADE_EXECUTOR_RE.search(
                    _without_dart_non_code(path.read_text(encoding="utf-8"))
                )
            )
        )
        if executors:
            result[identifier] = executors
    return result


def _commercially_blocked_methods(source: str) -> frozenset[str]:
    """契约自己声明 App Remote 未接线的 operation，不要求端侧已有 adapter。

    这些 operation 的 `commercialStatus: "blocked"` 与 block_reason 由服务
    contracts 拥有并 codegen 到同一份产物，是既有真相源。门禁读它而不是另立
    baseline，避免为过门禁写空 adapter，也避免第二套豁免台账。
    """

    method_by_operation = {
        operation_id: method
        for method, operation_id in re.findall(
            r'^\s+static const String ([A-Za-z][A-Za-z0-9_]*) = "([^"]+)";',
            source,
            re.MULTILINE,
        )
    }
    blocked: set[str] = set()
    for operation_id, body in re.findall(
        r'^\s+"([^"]+)": CloudOperationContract\((.*?)^\s+\),$',
        source,
        re.MULTILINE | re.DOTALL,
    ):
        if not re.search(r'commercialStatus:\s*"blocked"', body):
            continue
        method = method_by_operation.get(operation_id)
        if method is not None:
            blocked.add(method)
    return frozenset(blocked)


def _analyze_method_owners(
    app_root: Path,
    generated_methods: Iterable[str],
    blocked_methods: Iterable[str] = (),
) -> OwnerReport:
    ready_methods = frozenset(generated_methods)
    canonical_paths = _canonical_adapter_paths(app_root)
    legacy_paths = _legacy_cloud_paths(app_root)
    canonical_owners = _collect_method_references(canonical_paths)
    legacy_references = _collect_method_references(legacy_paths)
    canonical_methods = frozenset(canonical_owners)
    legacy_methods = frozenset(legacy_references)
    without_canonical = ready_methods - canonical_methods
    return OwnerReport(
        canonical_paths=canonical_paths,
        legacy_paths=legacy_paths,
        canonical_owners=canonical_owners,
        legacy_references=legacy_references,
        missing=frozenset(
            without_canonical - legacy_methods - frozenset(blocked_methods)
        ),
        duplicates={
            method: paths
            for method, paths in canonical_owners.items()
            if len(paths) > 1
        },
        legacy_only=frozenset(without_canonical & legacy_methods),
        legacy_overlap=frozenset(
            ready_methods & canonical_methods & legacy_methods
        ),
        non_ready=frozenset(canonical_methods - ready_methods),
        legacy_non_ready=frozenset(legacy_methods - ready_methods),
    )


def _analyze_upgrade_owners(
    app_root: Path,
    generated_upgrades: Iterable[str],
) -> UpgradeOwnerReport:
    ready_upgrades = frozenset(generated_upgrades)
    canonical_paths = _canonical_adapter_paths(app_root)
    legacy_paths = _legacy_cloud_paths(app_root)
    canonical_owners = _collect_upgrade_references(
        canonical_paths,
        ready_upgrades,
    )
    legacy_references = _collect_upgrade_references(
        legacy_paths,
        ready_upgrades,
    )
    canonical_ids = frozenset(canonical_owners)
    legacy_ids = frozenset(legacy_references)
    without_canonical = ready_upgrades - canonical_ids
    executors = _collect_upgrade_executors(canonical_paths, canonical_owners)
    return UpgradeOwnerReport(
        canonical_paths=canonical_paths,
        legacy_paths=legacy_paths,
        canonical_owners=canonical_owners,
        legacy_references=legacy_references,
        executors=executors,
        missing=frozenset(without_canonical - legacy_ids),
        duplicates={
            identifier: paths
            for identifier, paths in canonical_owners.items()
            if len(paths) > 1
        },
        legacy_only=frozenset(without_canonical & legacy_ids),
        legacy_overlap=frozenset(
            ready_upgrades & canonical_ids & legacy_ids
        ),
        missing_executors=frozenset(canonical_ids - frozenset(executors)),
    )
