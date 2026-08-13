"""端侧 test/support 唯一 owner、UAT 依赖真实度与跨对象 Journey 边界校验。"""

from __future__ import annotations

import ast
from pathlib import Path

from test_directory_layout_lib import APP_ROOT

from quwoquan_ops.gate import object_path_map as opm

from .common import Failures, rel
from .constants import (
    APP_CROSS_OBJECT_JOURNEY_ROOT,
    APP_JOURNEY_DIR_RE,
    APP_PATROL_IMPORT_URI,
    TEST_SUFFIX_BY_LAYER,
    TEST_SUPPORT_BARREL_NAME_RE,
    _DART_URI_SCHEME_RE,
)
from .dart_lexer import (
    _dart_export_uris,
    _dart_import_uris,
    _dart_library_sources,
    _dart_part_of_targets,
    _dart_part_uris,
    _dart_source_tokens,
)


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
