#!/usr/bin/env python3
"""Verify physical three-layer test directories and canonical file names."""
# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-001

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

from test_directory_layout_lib import (
    APP_PACKAGES_ROOT,
    APP_ROOT,
    CONTROL_PLANE_ROOT,
    DATA_ROOT,
    LAYERS,
    OPS_ACCEPTANCE_ROOT,
    OPS_TEST_ROOT,
    ROOT,
    RUNTIME_ROOT,
    RUNTIME_TEST_ROOT,
    SERVICE_DOMAIN_ROOT,
    SERVICE_ROOT,
    contains_generated_bridge_marker,
    iter_canonical_files,
    evidence_path_is_canonical,
)

sys.dont_write_bytecode = True

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import object_path_map as opm  # noqa: E402


#: 端侧测试层顶层目录里**尚未对象化**的旧形态残留。
#:
#: 这不是白名单：`verify_app_unmigrated_residue(...)` 对 missing / empty /
#: remaining 三种状态全部 BLOCK。它只让门禁能输出可执行的存量路径，
#: 不把任何存量测试解释为 canonical evidence。集合只能随对象化搬迁
#: 单调收缩，新对象目录只能位于由 service contracts 派生的 ``service/`` 容器。
APP_UNMIGRATED_LAYER_DIRS = {
    "local_contract": set(),
    "api_integration": set(),
    "user_acceptance": set(),
}
APP_CROSS_OBJECT_JOURNEY_ROOT = "journeys"
APP_PATROL_RUNNER_ROOT = "patrol"
APP_PATROL_RUNNER_FILES = frozenset({"patrol_test_main.dart", "test_bundle.dart"})
APP_PATROL_IMPORT_URI = "package:patrol/patrol.dart"
APP_TEST_ROOT_DIRS = {*LAYERS, "support"}
DATA_TEST_ROOT_DIRS = {*LAYERS, "support"}
DATA_LAYER_DIRS = {
    "local_contract": {"core", "execution", "source", "homepage", "post", "governance", "release"},
    "api_integration": {"execution", "release"},
    "user_acceptance": {"journeys", "quality"},
}
OPS_TEST_ROOT_DIRS = {"local_contract", "acceptance", "support"}
OPS_ACCEPTANCE_DIRS = {"api_integration", "user_acceptance"}
SERVICE_TEST_DIRS = {"local_contract", "api_integration", "support"}
IGNORED_TEST_CACHE_DIRS = {"__pycache__", ".pytest_cache"}

TEST_SUFFIX_BY_LAYER = {
    ".dart": {
        "local_contract": "__local_contract_test.dart",
        "api_integration": "__api_integration_test.dart",
        "user_acceptance": "__user_acceptance_test.dart",
    },
    ".go": {
        "local_contract": "__local_contract_test.go",
        "api_integration": "__api_integration_test.go",
    },
    ".py": {
        "local_contract": "__local_contract_test.py",
        "api_integration": "__api_integration_test.py",
        "user_acceptance": "__user_acceptance_test.py",
    },
}
DATA_TEST_NAME_RE = re.compile(
    r"^test_[a-z0-9]+(?:_[a-z0-9]+)*__[a-z0-9]+(?:_[a-z0-9]+)*__"
    r"(functional|contract|reliability|availability|observability|experience|security|performance|data_consistency)"
    r"__(local_contract|api_integration|user_acceptance)_test\.py$"
)
APP_JOURNEY_DIR_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_DART_URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_SERVICE_DOMAIN_RE = re.compile(r"(?m)^domain:\s*['\"]?([a-z][a-z0-9_]*)['\"]?\s*$")
TEST_SUPPORT_BARREL_NAME_RE = re.compile(
    r"(?:mock|fake|fixture|double|reexports?|repository)",
    re.IGNORECASE,
)


class Failures:
    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, message: str) -> None:
        self.items.append(message)

    def exit_code(self) -> int:
        if not self.items:
            print("[verify] OK: physical test directory layout checked")
            return 0
        for item in self.items:
            print(f"[verify] FAIL: {item}", file=sys.stderr)
        return 1


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def expected_suffix(path: Path, layer: str) -> str | None:
    return TEST_SUFFIX_BY_LAYER.get(path.suffix, {}).get(layer)


def require_layer_suffix(path: Path, layer: str, failures: Failures) -> None:
    suffix = expected_suffix(path, layer)
    if suffix and not path.name.endswith(suffix):
        failures.add(f"{rel(path)} must end with {suffix!r}")


def iter_test_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and (
            path.name.endswith("_test.dart")
            or path.name.endswith("_test.go")
            or path.name.endswith("_test.py")
        )
    )


def iter_app_test_files(root: Path) -> list[Path]:
    """Return every runnable App Dart/Python test, independent of name prefix."""
    return [
        path
        for path in iter_test_files(root)
        if path.suffix in {".dart", ".py"}
    ]


def ensure_allowed_children(root: Path, allowed: set[str], failures: Failures, *, allow_files: set[str] | None = None) -> None:
    allow_files = allow_files or set()
    if not root.exists():
        failures.add(f"missing test root: {rel(root)}")
        return
    for child in sorted(root.iterdir()):
        if child.is_dir() and child.name in IGNORED_TEST_CACHE_DIRS:
            continue
        if child.is_dir() and child.name not in allowed:
            failures.add(f"{rel(child)} is not an allowed test directory")
        if child.is_file() and child.name not in allow_files:
            failures.add(f"{rel(child)} is not allowed at test root")


def verify_support_has_no_tests(root: Path, failures: Failures) -> None:
    if not root.exists():
        return
    for path in iter_test_files(root):
        failures.add(f"{rel(path)} is under support/; support may contain fixtures or harness only")


def verify_no_generated_bridges(root: Path, failures: Failures) -> None:
    if not root.exists():
        return
    for path in iter_test_files(root):
        if contains_generated_bridge_marker(path):
            failures.add(f"{rel(path)} contains generated bridge marker")


def app_object_roster() -> opm.ObjectRoster:
    """从 ContractGraph 读取端侧测试路径的唯一对象名册。

    这里返回完整 roster，后续不仅校验 domain 顶层，还必须用同一名册
    校验 ``domain/context/object`` 三段身份。
    """
    graph_path = opm.ROOT / opm.CONTRACT_GRAPH_PATH
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    return opm.ObjectRoster(graph)


def app_object_test_dirs(roster: opm.ObjectRoster | None = None) -> set[str]:
    """端侧测试层的 canonical 顶层目录，全部由名册派生。

    目标形态
    ``test/<layer>/service/<service>/<context>/<object>/`` 的首段只能是统一
    ``service`` 容器；不归属任何业务对象的横切测试落到
    `object_path_map.APP_CROSS_CUTTING_ROOTS` 的三个根。
    """
    roster = roster or app_object_roster()
    # 强制求值 service/context 派生，避免仅因顶层字面量正确而掩盖 owner 冲突。
    for record in roster.objects.values():
        opm.app_service_for_context(record["domain"], record["context"])
    return {opm.APP_SERVICE_ROOT_SEGMENT} | set(opm.APP_CROSS_CUTTING_ROOTS)


def allowed_app_layer_dirs(layer: str, object_dirs: set[str]) -> set[str]:
    allowed = object_dirs | APP_UNMIGRATED_LAYER_DIRS.get(layer, set())
    if layer in {"local_contract", "user_acceptance"}:
        allowed.add(APP_CROSS_OBJECT_JOURNEY_ROOT)
    if layer == "user_acceptance":
        allowed.add(APP_PATROL_RUNNER_ROOT)
    return allowed


def verify_app_patrol_runner_root(failures: Failures) -> None:
    """Patrol runner shell 不是 UAT owner；只允许 pubspec 绑定的两个精确入口。"""
    runner_root = APP_ROOT / "user_acceptance" / APP_PATROL_RUNNER_ROOT
    if not runner_root.exists():
        return
    actual = {
        path.relative_to(runner_root).as_posix()
        for path in runner_root.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    unexpected = sorted(actual - APP_PATROL_RUNNER_FILES)
    missing = sorted(APP_PATROL_RUNNER_FILES - actual)
    for name in unexpected:
        failures.add(
            f"{rel(runner_root / name)} is not a Patrol runner entry; "
            "move runnable UAT to a canonical object or Journey owner"
        )
    for name in missing:
        failures.add(f"{rel(runner_root / name)} is required by the Patrol runner shell")
    for directory in sorted(path for path in runner_root.rglob("*") if path.is_dir()):
        failures.add(
            f"{rel(directory)} is nested below the Patrol runner shell; "
            "only patrol_test_main.dart and test_bundle.dart are allowed"
        )


def verify_app_unmigrated_residue(layer: str, failures: Failures) -> None:
    """missing / empty / remaining 残留均 BLOCK，不允许 allowance 假绿。"""
    layer_root = APP_ROOT / layer
    for name in sorted(APP_UNMIGRATED_LAYER_DIRS.get(layer, set())):
        residue_root = layer_root / name
        if not residue_root.is_dir():
            failures.add(
                f"{rel(residue_root)} no longer exists; drop it from "
                "APP_UNMIGRATED_LAYER_DIRS instead of keeping a stale allowance"
            )
            continue
        tests = sorted(iter_app_test_files(residue_root))
        if not tests:
            failures.add(
                f"{rel(residue_root)} is an empty-shell legacy allowance with no "
                "Dart/Python tests; empty directories and non-test artifacts do not count "
                "as migrated test evidence"
            )
            continue
        for path in tests:
            failures.add(
                f"{rel(path)} remains under legacy test root {rel(residue_root)}; "
                "move it to a canonical object owner and remove the allowance"
            )


def require_app_object_test_path(
    path: Path,
    layer_root: Path,
    roster: opm.ObjectRoster,
    failures: Failures,
) -> None:
    """对每个对象测试精确校验 ``service/service/context/object`` 四段身份。"""
    parts = path.relative_to(layer_root).parts
    top_level = parts[0]
    if top_level in APP_UNMIGRATED_LAYER_DIRS.get(layer_root.name, set()):
        return
    if top_level in opm.APP_CROSS_CUTTING_ROOTS:
        return
    if top_level == APP_CROSS_OBJECT_JOURNEY_ROOT:
        if layer_root.name == "api_integration":
            failures.add(
                f"{rel(path)} is a cross-object Journey in api_integration; "
                "use test/local_contract/journeys for typed-double/Provider/Widget "
                "contracts or test/user_acceptance/journeys for production Remote journeys"
            )
        return
    if opm.derive_app_test_target_shape_identity(parts, roster) is None:
        failures.add(
            f"{rel(path)} must live under a ContractGraph-owned "
            f"test/{layer_root.name}/service/<service>/<context>/<object>/.../file"
        )


def _dart_source_tokens(source: str) -> list[tuple[str, str]]:
    """Lex the Dart shapes needed by the Journey boundary gate.

    Comments are discarded and string literals are emitted as opaque tokens, so
    neither can impersonate an import, Widget/Provider call, or local typed double.
    This deliberately stays smaller than a Dart parser while preserving the exact
    import URI literals needed for physical path resolution.
    """
    tokens: list[tuple[str, str]] = []
    index = 0
    length = len(source)
    while index < length:
        char = source[index]
        if char.isspace():
            index += 1
            continue
        if source.startswith("//", index):
            newline = source.find("\n", index + 2)
            index = length if newline < 0 else newline + 1
            continue
        if source.startswith("/*", index):
            depth = 1
            index += 2
            while index < length and depth:
                if source.startswith("/*", index):
                    depth += 1
                    index += 2
                elif source.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            continue
        if char in {"'", '"'}:
            delimiter = char * (3 if source.startswith(char * 3, index) else 1)
            index += len(delimiter)
            value: list[str] = []
            terminated = False
            while index < length:
                if source.startswith(delimiter, index):
                    index += len(delimiter)
                    terminated = True
                    break
                if source[index] == "\\" and index + 1 < length:
                    value.append(source[index + 1])
                    index += 2
                    continue
                value.append(source[index])
                index += 1
            if terminated:
                tokens.append(("string", "".join(value)))
            continue
        if char.isalpha() or char in {"_", "$"}:
            end = index + 1
            while end < length and (
                source[end].isalnum() or source[end] in {"_", "$"}
            ):
                end += 1
            tokens.append(("identifier", source[index:end]))
            index = end
            continue
        tokens.append(("punctuation", char))
        index += 1
    return tokens


def _dart_directive_uris(
    tokens: list[tuple[str, str]],
    directive: str,
) -> list[str]:
    """Return every URI from a Dart directive, including conditional branches."""
    uris: list[str] = []
    index = 0
    while index < len(tokens):
        if tokens[index] != ("identifier", directive):
            index += 1
            continue
        cursor = index + 1
        if (
            directive == "part"
            and cursor < len(tokens)
            and tokens[cursor] == ("identifier", "of")
        ):
            while cursor < len(tokens) and tokens[cursor] != ("punctuation", ";"):
                cursor += 1
            index = cursor + 1
            continue
        if cursor < len(tokens) and tokens[cursor] in {
            ("identifier", "r"),
            ("identifier", "R"),
        }:
            cursor += 1
        if cursor >= len(tokens) or tokens[cursor][0] != "string":
            index += 1
            continue
        directive_uris: list[str] = []
        while cursor < len(tokens) and tokens[cursor] != ("punctuation", ";"):
            if tokens[cursor][0] == "string":
                directive_uris.append(tokens[cursor][1])
            cursor += 1
        if cursor < len(tokens):
            uris.extend(directive_uris)
            index = cursor + 1
        else:
            index += 1
    return uris


def _dart_import_uris(tokens: list[tuple[str, str]]) -> list[str]:
    """Return URI literals from syntactic Dart import directives only."""
    return _dart_directive_uris(tokens, "import")


def _dart_export_uris(tokens: list[tuple[str, str]]) -> list[str]:
    """Return URI literals from syntactic Dart export directives only."""
    return _dart_directive_uris(tokens, "export")


def _dart_part_uris(tokens: list[tuple[str, str]]) -> list[str]:
    """Return URI literals from ``part '…'`` while excluding ``part of``."""
    return _dart_directive_uris(tokens, "part")


def _dart_part_of_targets(
    tokens: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Return ``part of`` URI/library-name targets without textual decoys."""
    targets: list[tuple[str, str]] = []
    index = 0
    while index < len(tokens) - 1:
        if not (
            tokens[index] == ("identifier", "part")
            and tokens[index + 1] == ("identifier", "of")
        ):
            index += 1
            continue
        cursor = index + 2
        if cursor < len(tokens) and tokens[cursor] in {
            ("identifier", "r"),
            ("identifier", "R"),
        }:
            cursor += 1
        if cursor < len(tokens) and tokens[cursor][0] == "string":
            targets.append(("uri", tokens[cursor][1]))
        else:
            name_parts: list[str] = []
            while cursor < len(tokens) and tokens[cursor] != ("punctuation", ";"):
                if tokens[cursor][0] == "identifier":
                    name_parts.append(tokens[cursor][1])
                elif tokens[cursor] == ("punctuation", "."):
                    name_parts.append(".")
                cursor += 1
            name = "".join(name_parts)
            if name:
                targets.append(("library", name))
        while index < len(tokens) and tokens[index] != ("punctuation", ";"):
            index += 1
        index += 1
    return targets


def _dart_library_names(tokens: list[tuple[str, str]]) -> set[str]:
    names: set[str] = set()
    index = 0
    while index < len(tokens):
        if tokens[index] != ("identifier", "library"):
            index += 1
            continue
        cursor = index + 1
        name_parts: list[str] = []
        while cursor < len(tokens) and tokens[cursor] != ("punctuation", ";"):
            if tokens[cursor][0] == "identifier":
                name_parts.append(tokens[cursor][1])
            elif tokens[cursor] == ("punctuation", "."):
                name_parts.append(".")
            cursor += 1
        name = "".join(name_parts)
        if name:
            names.add(name)
        index = cursor + 1
    return names


def _dart_library_sources(path: Path) -> list[Path]:
    """Resolve a Dart library's source+parts, including a part-of entry path."""
    queue = [path.resolve()]
    sources: set[Path] = set()
    while queue:
        source = queue.pop()
        if source in sources or not source.is_file() or source.suffix != ".dart":
            continue
        sources.add(source)
        tokens = _dart_source_tokens(
            source.read_text(encoding="utf-8", errors="ignore")
        )
        for uri in _dart_part_uris(tokens):
            if uri and "$" not in uri and not _DART_URI_SCHEME_RE.match(uri):
                queue.append((source.parent / uri).resolve())
        for kind, value in _dart_part_of_targets(tokens):
            if kind == "uri":
                if value and "$" not in value and not _DART_URI_SCHEME_RE.match(value):
                    queue.append((source.parent / value).resolve())
                continue
            for candidate in sorted(source.parent.glob("*.dart")):
                candidate_tokens = _dart_source_tokens(
                    candidate.read_text(encoding="utf-8", errors="ignore")
                )
                if value not in _dart_library_names(candidate_tokens):
                    continue
                declared_parts = {
                    (candidate.parent / uri).resolve()
                    for uri in _dart_part_uris(candidate_tokens)
                    if uri and "$" not in uri and not _DART_URI_SCHEME_RE.match(uri)
                }
                if source in declared_parts:
                    queue.append(candidate.resolve())
    return sorted(sources)


def app_support_path_identity(
    path: Path,
    support_root: Path,
    roster: opm.ObjectRoster,
) -> tuple[str, ...] | None:
    """Return the exact object/cross-cutting owner encoded by a support path."""
    try:
        parts = path.resolve().relative_to(support_root.resolve()).parts
    except ValueError:
        return None
    if not parts:
        return None
    if parts[0] == "runtime":
        return ("cross_cutting", "runtime")
    identity = opm.derive_app_test_target_shape_identity(parts, roster)
    if identity is None:
        return None
    return ("object", *identity)


def app_support_exports_are_forbidden(
    path: Path,
    support_root: Path,
    identity: tuple[str, ...] | None,
    exports: list[str],
) -> bool:
    """Allow only a cross-cutting barrel whose targets stay in that same root."""
    if not exports:
        return False
    if identity is None or identity[0] != "cross_cutting":
        return True
    if TEST_SUPPORT_BARREL_NAME_RE.search(path.name):
        return True
    cross_cutting_root = (support_root / identity[1]).resolve()
    for uri in exports:
        if not uri or "$" in uri or _DART_URI_SCHEME_RE.match(uri):
            return True
        export_path = Path(uri)
        if export_path.is_absolute():
            return True
        resolved = (path.parent / export_path).resolve()
        try:
            resolved.relative_to(cross_cutting_root)
        except ValueError:
            return True
    return False


def _relative_support_target(
    source: Path,
    support_root: Path,
    uri: str,
) -> Path | None:
    if not uri or "$" in uri or _DART_URI_SCHEME_RE.match(uri):
        return None
    candidate = Path(uri)
    if candidate.is_absolute():
        return None
    resolved = (source.parent / candidate).resolve()
    try:
        resolved.relative_to(support_root.resolve())
    except ValueError:
        return None
    return resolved


def app_support_authored_edge_is_forbidden(
    source_identity: tuple[str, ...] | None,
    target_identity: tuple[str, ...] | None,
) -> bool:
    """Keep object helpers object-local; only object helpers may use runtime harnesses."""
    if source_identity is None or target_identity is None:
        return True
    if source_identity == ("cross_cutting", "runtime"):
        return target_identity != source_identity
    if source_identity[0] == "object":
        return target_identity not in {
            source_identity,
            ("cross_cutting", "runtime"),
        }
    return True


def verify_app_support_layout(
    roster: opm.ObjectRoster,
    failures: Failures,
) -> None:
    """Require every App support artifact to encode one owner without a barrel."""
    support_root = APP_ROOT / "support"
    if not support_root.exists():
        return
    for path in sorted(support_root.rglob("*")):
        if not (path.is_file() or path.is_symlink()):
            continue
        identity = app_support_path_identity(path, support_root, roster)
        if identity is None:
            failures.add(
                f"{rel(path)} has no canonical support owner; business helpers must "
                "live under test/support/service/<service>/<context>/<object>/..., while only "
                "runtime/ may own cross-cutting support"
            )
        if path.suffix != ".dart":
            continue
        tokens = _dart_source_tokens(path.read_text(encoding="utf-8", errors="ignore"))
        exports = _dart_export_uris(tokens)
        if app_support_exports_are_forbidden(path, support_root, identity, exports):
            export_summary = ", ".join(exports[:3])
            if len(exports) > 3:
                export_summary += f", ... ({len(exports)} total)"
            failures.add(
                f"{rel(path)} is a support export barrel ({export_summary}); "
                "local tests must import the unique object-owned helper directly"
            )
        authored_uris = sorted(
            set(
                _dart_import_uris(tokens)
                + exports
                + _dart_part_uris(tokens)
                + [
                    value
                    for kind, value in _dart_part_of_targets(tokens)
                    if kind == "uri"
                ]
            )
        )
        for uri in authored_uris:
            target = _relative_support_target(path, support_root, uri)
            if target is None:
                continue
            target_identity = app_support_path_identity(target, support_root, roster)
            if app_support_authored_edge_is_forbidden(identity, target_identity):
                failures.add(
                    f"{rel(path)} has cross-owner support edge {uri!r}; object helpers "
                    "may use only their own object or runtime harness, and runtime "
                    "support may use only runtime support"
                )


def app_patrol_user_acceptance_targets(
    user_acceptance_root: Path | None = None,
) -> list[Path]:
    """Return canonical UAT files that syntactically import Patrol.

    The Dart lexer deliberately excludes comments and string contents, so text
    that merely mentions the import cannot enlist a non-Patrol test in a real
    device run.
    """
    root = user_acceptance_root or (APP_ROOT / "user_acceptance")
    if not root.is_dir():
        return []
    targets: list[Path] = []
    for path in sorted(root.rglob("*__user_acceptance_test.dart")):
        if not path.is_file():
            continue
        tokens = _dart_source_tokens(path.read_text(encoding="utf-8", errors="ignore"))
        if APP_PATROL_IMPORT_URI in _dart_import_uris(tokens):
            targets.append(path)
    return targets


def _dart_tokens_have_local_boundary(tokens: list[tuple[str, str]]) -> bool:
    """Recognize executable Widget/Provider/typed-double syntax, not text."""
    for index, token in enumerate(tokens):
        next_token = tokens[index + 1] if index + 1 < len(tokens) else None
        if token in {
            ("identifier", "testWidgets"),
            ("identifier", "ProviderScope"),
            ("identifier", "ProviderContainer"),
        } and next_token == ("punctuation", "("):
            return True
        if (
            token == ("punctuation", ".")
            and next_token
            in {
                ("identifier", "overrideWith"),
                ("identifier", "overrideWithValue"),
            }
            and index + 2 < len(tokens)
            and tokens[index + 2] == ("punctuation", "(")
        ):
            return True
        if token == ("identifier", "class") and next_token is not None:
            if next_token[0] != "identifier" or not next_token[1].startswith("_"):
                continue
            cursor = index + 2
            while cursor < len(tokens) and tokens[cursor] not in {
                ("punctuation", "{"),
                ("punctuation", ";"),
            }:
                if tokens[cursor] in {
                    ("identifier", "extends"),
                    ("identifier", "implements"),
                }:
                    return True
                cursor += 1
    return False


def _dart_imported_support_targets(
    path: Path,
    tokens: list[tuple[str, str]],
) -> list[tuple[str, Path]]:
    """Resolve support edges from the complete Dart library closure."""
    support_root = APP_ROOT / "support"
    targets: set[tuple[str, Path]] = set()
    sources = _dart_library_sources(path) or [path]
    for source in sources:
        source_tokens = (
            tokens
            if source.resolve() == path.resolve()
            else _dart_source_tokens(
                source.read_text(encoding="utf-8", errors="ignore")
            )
        )
        authored = (
            _dart_import_uris(source_tokens)
            + _dart_export_uris(source_tokens)
            + _dart_part_uris(source_tokens)
            + [
                value
                for kind, value in _dart_part_of_targets(source_tokens)
                if kind == "uri"
            ]
        )
        for uri in authored:
            target = _relative_support_target(source, support_root, uri)
            if target is not None:
                targets.add((uri, target))
    return sorted(targets, key=lambda item: (item[0], item[1].as_posix()))


def _dart_typed_double_declarations(
    tokens: list[tuple[str, str]],
) -> set[str]:
    names: set[str] = set()
    for index, token in enumerate(tokens):
        if token != ("identifier", "class") or index + 1 >= len(tokens):
            continue
        name = tokens[index + 1]
        if name[0] != "identifier":
            continue
        cursor = index + 2
        has_boundary = False
        while cursor < len(tokens) and tokens[cursor] not in {
            ("punctuation", "{"),
            ("punctuation", ";"),
        }:
            if tokens[cursor] in {
                ("identifier", "extends"),
                ("identifier", "implements"),
            }:
                has_boundary = True
            cursor += 1
        if has_boundary:
            names.add(name[1])
    return names


def _dart_non_directive_identifiers(
    tokens: list[tuple[str, str]],
) -> set[str]:
    identifiers: set[str] = set()
    index = 0
    while index < len(tokens):
        if tokens[index] in {
            ("identifier", "import"),
            ("identifier", "export"),
            ("identifier", "part"),
        }:
            while index < len(tokens) and tokens[index] != ("punctuation", ";"):
                index += 1
            index += 1
            continue
        if tokens[index][0] == "identifier":
            identifiers.add(tokens[index][1])
        index += 1
    return identifiers


def _app_local_journey_dart_boundary(
    path: Path,
    tokens: list[tuple[str, str]],
) -> tuple[bool, list[str]]:
    """Return executable local boundary and malformed support-import findings."""
    direct_boundary = _dart_tokens_have_local_boundary(tokens)
    references = _dart_non_directive_identifiers(tokens)
    valid_support_boundary = False
    findings: list[str] = []
    unreferenced_boundaries: list[str] = []
    for uri, target in _dart_imported_support_targets(path, tokens):
        if not target.is_file() or target.suffix != ".dart":
            findings.append(
                f"support import {uri!r} does not resolve to a Dart typed double"
            )
            continue
        declarations: set[str] = set()
        for support_source in _dart_library_sources(target):
            support_tokens = _dart_source_tokens(
                support_source.read_text(encoding="utf-8", errors="ignore")
            )
            declarations.update(_dart_typed_double_declarations(support_tokens))
        if not declarations:
            # Ordinary fixtures may accompany a real Widget/Provider/typed seam;
            # their import alone simply does not prove the Journey boundary.
            continue
        used = sorted(declarations & references)
        if not used:
            unreferenced_boundaries.append(
                f"support import {uri!r} is not referenced by executable test code"
            )
            continue
        valid_support_boundary = True
    has_boundary = direct_boundary or valid_support_boundary
    if not has_boundary:
        findings.extend(unreferenced_boundaries)
    return has_boundary, findings


def _python_local_journey_has_boundary(text: str) -> bool:
    """Use Python syntax, never comments/strings, as local Journey evidence."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ClassDef)
            and node.name.startswith("_")
            and bool(node.bases)
        ):
            return True
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in {
                "testWidgets",
                "ProviderScope",
                "ProviderContainer",
            }:
                return True
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in {"overrideWith", "overrideWithValue"}
            ):
                return True
    return False


def app_local_journey_has_test_boundary(path: Path) -> bool:
    """本地跨对象 Journey 必须显式使用 typed double、Provider 或 Widget。"""
    text = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix == ".dart":
        tokens = _dart_source_tokens(text)
        boundary, findings = _app_local_journey_dart_boundary(path, tokens)
        return boundary and not findings
    if path.suffix == ".py":
        return _python_local_journey_has_boundary(text)
    return False


def verify_app_user_acceptance_support_edges(
    roster: opm.ObjectRoster,
    failures: Failures,
) -> None:
    """UAT may use runtime harnesses, never object-owned fixture/double support."""
    root = APP_ROOT / "user_acceptance"
    support_root = APP_ROOT / "support"
    if not root.exists():
        return
    for path in sorted(root.rglob("*.dart")):
        if not path.is_file():
            continue
        tokens = _dart_source_tokens(path.read_text(encoding="utf-8", errors="ignore"))
        for uri, target in _dart_imported_support_targets(path, tokens):
            target_identity = app_support_path_identity(target, support_root, roster)
            if target_identity != ("cross_cutting", "runtime"):
                failures.add(
                    f"{rel(path)} imports object/unowned test support {uri!r}; "
                    "App user_acceptance must use production Remote composition"
                )


def verify_app_journeys(layer: str, failures: Failures) -> None:
    """锁定两种跨对象 Journey 的唯一物理形状与依赖真实度边界。"""
    root = APP_ROOT / layer / APP_CROSS_OBJECT_JOURNEY_ROOT
    if not root.exists():
        return
    if layer == "api_integration":
        failures.add(
            f"{rel(root)} is forbidden; cross-object Journey tests belong only to "
            "local_contract/journeys or user_acceptance/journeys"
        )
        return
    expected_suffix = TEST_SUFFIX_BY_LAYER[".dart"][layer]
    expected_python_suffix = (
        TEST_SUFFIX_BY_LAYER[".py"][layer] if layer == "local_contract" else None
    )
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            failures.add(
                f"{rel(child)} must live under journeys/<journey>/file"
            )
            continue
        if APP_JOURNEY_DIR_RE.fullmatch(child.name) is None:
            failures.add(f"{rel(child)} must use a snake_case journey directory")
        tests = sorted(
            path
            for path in child.iterdir()
            if path.is_file()
            and path.name.endswith(("_test.dart", "_test.py"))
        )
        if not tests:
            failures.add(f"{rel(child)} must contain a runnable {layer} test")
        for nested in sorted(path for path in child.rglob("*") if path.is_dir()):
            failures.add(
                f"{rel(nested)} is nested below journeys/<journey>; "
                "journey tests must be direct children"
            )
        for path in sorted(path for path in child.iterdir() if path.is_file()):
            allowed_suffixes = (
                (expected_suffix, expected_python_suffix)
                if expected_python_suffix is not None
                else (expected_suffix,)
            )
            if not path.name.endswith(allowed_suffixes):
                failures.add(
                    f"{rel(path)} must be a direct {layer} test with suffix "
                    + " or ".join(repr(item) for item in allowed_suffixes)
                )
                continue
            if layer == "local_contract":
                findings: list[str] = []
                if path.suffix == ".dart":
                    tokens = _dart_source_tokens(
                        path.read_text(encoding="utf-8", errors="ignore")
                    )
                    has_boundary, findings = _app_local_journey_dart_boundary(
                        path, tokens
                    )
                    for finding in findings:
                        failures.add(f"{rel(path)} {finding}")
                else:
                    has_boundary = app_local_journey_has_test_boundary(path)
                if not has_boundary and not findings:
                    failures.add(
                        f"{rel(path)} must exercise a test-tree typed double, Provider, "
                        "or Widget boundary; path placement alone is not execution evidence"
                    )


def verify_app_object_source_files(
    layer: str,
    layer_root: Path,
    roster: opm.ObjectRoster,
    failures: Failures,
) -> None:
    """Object test directories contain runnable tests; reusable code belongs in support."""
    if not layer_root.exists():
        return
    for path in sorted(layer_root.rglob("*")):
        if not path.is_file() or path.suffix not in {".dart", ".py"}:
            continue
        parts = path.relative_to(layer_root).parts
        if opm.derive_app_test_target_shape_identity(parts, roster) is None:
            continue
        suffix = expected_suffix(path, layer)
        if suffix is None or not path.name.endswith(suffix):
            failures.add(
                f"{rel(path)} is non-test source inside an object test directory; "
                "move reusable helpers/barrels to the unique test/support owner"
            )


def verify_app_python_evidence_boundaries(failures: Failures) -> None:
    """Only root App local_contract Python is executed by the canonical runner."""
    for layer in ("api_integration", "user_acceptance"):
        for path in sorted((APP_ROOT / layer).rglob("*.py")):
            if path.is_file():
                failures.add(
                    f"{rel(path)} is static App Python under {layer}; only root "
                    "test/local_contract Python is executable evidence"
                )
    if APP_PACKAGES_ROOT.exists():
        for path in sorted(APP_PACKAGES_ROOT.glob("*/test/**/*.py")):
            if path.is_file():
                failures.add(
                    f"{rel(path)} is package-local App Python without a canonical runner"
                )


def verify_app(failures: Failures) -> None:
    ensure_allowed_children(APP_ROOT, APP_TEST_ROOT_DIRS, failures)
    verify_support_has_no_tests(APP_ROOT / "support", failures)
    roster = app_object_roster()
    verify_app_support_layout(roster, failures)
    object_dirs = app_object_test_dirs(roster)
    for layer in sorted(LAYERS):
        layer_root = APP_ROOT / layer
        ensure_allowed_children(
            layer_root, allowed_app_layer_dirs(layer, object_dirs), failures
        )
        verify_app_unmigrated_residue(layer, failures)
        for path in sorted(iter_app_test_files(layer_root)):
            require_layer_suffix(path, layer, failures)
            require_app_object_test_path(path, layer_root, roster, failures)
        verify_app_object_source_files(layer, layer_root, roster, failures)
        for child in (sorted(layer_root.iterdir()) if layer_root.exists() else []):
            if child.is_file():
                failures.add(f"{rel(child)} must live under a test object directory")
    for layer in sorted(LAYERS):
        verify_app_journeys(layer, failures)
    verify_app_user_acceptance_support_edges(roster, failures)
    verify_app_python_evidence_boundaries(failures)
    verify_app_patrol_runner_root(failures)


def verify_data(failures: Failures) -> None:
    ensure_allowed_children(DATA_ROOT, DATA_TEST_ROOT_DIRS, failures, allow_files={"conftest.py"})
    verify_support_has_no_tests(DATA_ROOT / "support", failures)
    for layer in sorted(LAYERS):
        layer_root = DATA_ROOT / layer
        if not layer_root.exists():
            failures.add(f"missing data test layer: {rel(layer_root)}")
            continue
        ensure_allowed_children(layer_root, DATA_LAYER_DIRS[layer], failures)
        for path in sorted(layer_root.rglob("test_*.py")):
            require_layer_suffix(path, layer, failures)
            if not DATA_TEST_NAME_RE.fullmatch(path.name):
                failures.add(
                    f"{rel(path)} must use test_<subject>__<case>__<facet>__{layer}_test.py"
                )


def verify_ops(failures: Failures) -> None:
    ensure_allowed_children(OPS_TEST_ROOT, OPS_TEST_ROOT_DIRS, failures)
    verify_support_has_no_tests(OPS_TEST_ROOT / "support", failures)
    if OPS_ACCEPTANCE_ROOT.exists():
        ensure_allowed_children(OPS_ACCEPTANCE_ROOT, OPS_ACCEPTANCE_DIRS, failures)
    for path in sorted((OPS_TEST_ROOT / "local_contract").rglob("test_*.py")):
        require_layer_suffix(path, "local_contract", failures)
    for layer in sorted(OPS_ACCEPTANCE_DIRS):
        layer_root = OPS_ACCEPTANCE_ROOT / layer
        if not layer_root.exists():
            failures.add(f"missing ops acceptance layer: {rel(layer_root)}")
            continue
        for path in sorted(layer_root.rglob("test_*.py")):
            require_layer_suffix(path, layer, failures)


def service_object_test_roster(
    service_dir: Path,
    roster: opm.ObjectRoster,
) -> set[tuple[str, str]]:
    """Intersect the service's physical contracts with the ContractGraph roster."""
    domain_path = service_dir / "contracts" / "domain.yaml"
    if not domain_path.is_file():
        return set()
    match = _SERVICE_DOMAIN_RE.search(
        domain_path.read_text(encoding="utf-8", errors="ignore")
    )
    if match is None:
        return set()
    domain = match.group(1)
    objects: set[tuple[str, str]] = set()
    for graph_domain, context, object_name in sorted(roster.by_key):
        if graph_domain != domain:
            continue
        contract = service_dir / "contracts" / context / object_name / "object.yaml"
        if contract.is_file():
            objects.add((context, object_name))
    return objects


def verify_service_tests_dir(
    tests_root: Path,
    roster: opm.ObjectRoster,
    failures: Failures,
) -> None:
    ensure_allowed_children(tests_root, SERVICE_TEST_DIRS, failures, allow_files={"__init__.py"})
    verify_support_has_no_tests(tests_root / "support", failures)
    if (tests_root / "ops").exists():
        failures.add(f"{rel(tests_root / 'ops')} is retired; cross-environment tests belong to quwoquan_ops/tests/acceptance")
    object_roster = service_object_test_roster(tests_root.parent, roster)
    for layer in ("local_contract", "api_integration"):
        layer_root = tests_root / layer
        if not layer_root.exists():
            continue
        for path in sorted(layer_root.rglob("*_test.go")):
            require_layer_suffix(path, layer, failures)
            require_service_object_test_path(path, layer_root, object_roster, failures)
        for path in sorted(layer_root.rglob("*_test.py")):
            require_layer_suffix(path, layer, failures)
            require_service_object_test_path(path, layer_root, object_roster, failures)


def require_service_object_test_path(
    path: Path,
    layer_root: Path,
    object_roster: set[tuple[str, str]],
    failures: Failures,
) -> None:
    parts = path.relative_to(layer_root).parts
    if len(parts) < 3:
        failures.add(
            f"{rel(path)} must live under "
            "<context>/<object>/.../file"
        )
        return
    if any(part in {"internal", "cmd", "generated"} for part in parts[:2]):
        failures.add(
            f"{rel(path)} must use a business context/object owner before "
            "any optional Go package subpath"
        )
        return
    if (parts[0], parts[1]) not in object_roster:
        failures.add(
            f"{rel(path)} uses context/object {parts[0]}/{parts[1]} outside the "
            "owning service contracts and ContractGraph roster"
        )


def verify_service(failures: Failures) -> None:
    if not SERVICE_ROOT.exists():
        failures.add(f"missing service root: {rel(SERVICE_ROOT)}")
        return
    roster = app_object_roster()
    for owner_root in (SERVICE_ROOT, CONTROL_PLANE_ROOT):
        if not owner_root.exists():
            continue
        for service_dir in sorted(path for path in owner_root.iterdir() if path.is_dir()):
            tests_root = service_dir / "tests"
            if tests_root.exists():
                verify_service_tests_dir(tests_root, roster, failures)
            for path in sorted(service_dir.rglob("*_test.go")):
                rel_text = rel(path)
                if "/tests/local_contract/" in rel_text or "/tests/api_integration/" in rel_text:
                    continue
                failures.add(
                    f"{rel_text} is a service test outside canonical "
                    "tests/local_contract/<context>/<object> or "
                    "tests/api_integration/<context>/<object>"
                )
            for path in sorted(service_dir.rglob("*_test.py")):
                rel_text = rel(path)
                if "/tests/local_contract/" in rel_text or "/tests/api_integration/" in rel_text:
                    continue
                failures.add(
                    f"{rel_text} is a service test outside canonical "
                    "tests/local_contract/<context>/<object> or "
                    "tests/api_integration/<context>/<object>"
                )


def verify_runtime(failures: Failures) -> None:
    if not RUNTIME_ROOT.exists():
        failures.add(f"missing runtime root: {rel(RUNTIME_ROOT)}")
        return
    verify_runtime_tests_dir(RUNTIME_TEST_ROOT, failures)
    for path in sorted(RUNTIME_ROOT.rglob("*_test.go")):
        rel_text = rel(path)
        if (
            "/tests/local_contract/" in rel_text
            or "/tests/api_integration/" in rel_text
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "//go:build api_integration" in text:
            failures.add(
                f"{rel_text} is a runtime api_integration test outside canonical "
                "tests/api_integration/<package>"
            )


def verify_runtime_tests_dir(tests_root: Path, failures: Failures) -> None:
    ensure_allowed_children(
        tests_root,
        SERVICE_TEST_DIRS,
        failures,
        allow_files={"__init__.py"},
    )
    verify_support_has_no_tests(tests_root / "support", failures)
    for layer in ("local_contract", "api_integration"):
        layer_root = tests_root / layer
        if not layer_root.exists():
            continue
        for path in sorted(layer_root.rglob("*_test.go")):
            require_layer_suffix(path, layer, failures)
            parts = path.relative_to(layer_root).parts
            if len(parts) != 2:
                failures.add(
                    f"{rel(path)} must live directly under <runtime-package>/file"
                )
            elif parts[0] in {"internal", "cmd", "generated"}:
                failures.add(
                    f"{rel(path)} must not recreate a production source root "
                    "inside runtime tests/"
                )


def verify_all_canonical_files_recognized(failures: Failures) -> None:
    for _, path, layer in iter_canonical_files():
        if not evidence_path_is_canonical(rel(path)):
            failures.add(f"{rel(path)} is not recognized as canonical {layer} evidence")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        if argv != ["--list-patrol-user-acceptance-targets"]:
            print(f"[verify] FAIL: unsupported arguments: {' '.join(argv)}", file=sys.stderr)
            return 2
        for path in app_patrol_user_acceptance_targets():
            print(rel(path))
        return 0
    failures = Failures()
    verify_app(failures)
    verify_data(failures)
    verify_ops(failures)
    verify_service(failures)
    verify_runtime(failures)
    verify_no_generated_bridges(APP_ROOT, failures)
    verify_no_generated_bridges(DATA_ROOT, failures)
    verify_no_generated_bridges(OPS_TEST_ROOT, failures)
    verify_no_generated_bridges(SERVICE_ROOT, failures)
    verify_no_generated_bridges(CONTROL_PLANE_ROOT, failures)
    verify_no_generated_bridges(SERVICE_DOMAIN_ROOT / "internal", failures)
    verify_no_generated_bridges(SERVICE_DOMAIN_ROOT / "runtime", failures)
    verify_no_generated_bridges(SERVICE_DOMAIN_ROOT / "tools", failures)
    verify_all_canonical_files_recognized(failures)
    return failures.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
