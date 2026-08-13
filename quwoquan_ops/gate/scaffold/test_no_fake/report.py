"""失败聚合、canonical/api_integration/UAT 源码校验与 CLI main 入口。"""

from __future__ import annotations

import sys
from pathlib import Path

from test_directory_layout_lib import (
    ROOT,
    contains_generated_bridge_marker,
    iter_canonical_files,
)

from .fixtures import (
    _environment_class_names,
    _environment_data_names_for_file,
    _source_string_literals,
    app_local_fixture_environment_path_names,
    is_app_local_fixture_source,
    is_app_user_acceptance_source,
)
from .lexer import _c_style_tokens, _lexical_code_text
from .patterns import (
    DART_TEST_RE,
    FAKE_BUILD_TAG_RE,
    GO_TEST_ENTRYPOINT_RE,
    PLACEHOLDER_PATTERNS,
    PYTHON_TEST_RE,
    SKIP_PATTERNS,
)
from .snapshot import _read_text, scan_repository_files, scan_repository_snapshot
from .support_edges import (
    _dart_library_source_texts,
    first_party_substitute_support_imports,
    lexical_memory_modes,
    lexical_substitute_names,
    substitute_library_imports,
)


class Failures:
    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, message: str) -> None:
        if message not in self.items:
            self.items.append(message)

    def exit_code(self) -> int:
        if not self.items:
            print("[verify] OK: no fake canonical tests detected")
            return 0
        for item in self.items:
            print(f"[verify] FAIL: {item}", file=sys.stderr)
        return 1


def verify_canonical_files(
    failures: Failures,
    canonical_files: list[tuple[str, Path, str]] | None = None,
    text_cache: dict[Path, str] | None = None,
) -> None:
    cache = text_cache if text_cache is not None else {}
    inventory = (
        canonical_files
        if canonical_files is not None
        else iter_canonical_files()
    )
    for _, path, _ in inventory:
        text = _read_text(path, cache)
        code_text = _lexical_code_text(path, text)
        if contains_generated_bridge_marker(path, text):
            failures.add(f"{path.relative_to(ROOT)} contains generated bridge marker")
        for pattern in PLACEHOLDER_PATTERNS:
            if pattern.search(code_text):
                failures.add(f"{path.relative_to(ROOT)} contains placeholder pattern {pattern.pattern!r}")
        for pattern in SKIP_PATTERNS:
            if pattern.search(code_text):
                failures.add(f"{path.relative_to(ROOT)} contains skip pattern {pattern.pattern!r}")
        if (
            path.suffix == ".go"
            and "_support__" not in path.name
            and not GO_TEST_ENTRYPOINT_RE.search(code_text)
        ):
            failures.add(f"{path.relative_to(ROOT)} go canonical test lacks Test*/Benchmark*/TestMain entrypoint")
        if (
            path.suffix == ".py"
            and "importlib . util . spec_from_file_location" not in code_text
            and not PYTHON_TEST_RE.search(code_text)
        ):
            failures.add(f"{path.relative_to(ROOT)} python canonical test lacks real test body")
        if path.suffix == ".dart" and not DART_TEST_RE.search(code_text):
            failures.add(f"{path.relative_to(ROOT)} dart canonical test lacks test/testWidgets/patrolTest body")


def verify_test_artifacts(failures: Failures) -> None:
    test_artifacts = ROOT / ".qwq_output" / "env" / "repo" / "runs" / "tests"
    if not test_artifacts.exists():
        return
    for path in sorted(test_artifacts.rglob("report.json")):
        # Disposable pytest isolation roots are deleted after the suite; ignore
        # any leftover incomplete reports instead of treating them as evidence.
        if any(part.startswith("data-local-contract.") for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if '"exit_code"' not in text or '"case_results"' not in text:
            failures.add(f"{path.relative_to(ROOT)} report.json missing exit_code or case_results")


def verify_app_local_fixture_naming(
    failures: Failures,
    all_files: list[Path] | None = None,
    text_cache: dict[Path, str] | None = None,
) -> None:
    """Environment names in local doubles/fixtures cannot impersonate evidence."""
    cache = text_cache if text_cache is not None else {}
    paths = all_files if all_files is not None else scan_repository_files()
    for path in paths:
        if not is_app_local_fixture_source(path):
            continue
        if all_files is None and not path.is_file():
            continue
        path_names = app_local_fixture_environment_path_names(path)
        if path_names:
            failures.add(
                f"{path.relative_to(ROOT)} uses deployment-environment path names "
                f"{path_names} for an ordinary fixture/double/golden"
            )
        if path.suffix not in {".dart", ".py", ".go", ".ts", ".json", ".yaml", ".yml", ".txt"}:
            continue
        text = _read_text(path, cache)
        class_names = (
            _environment_class_names(path, text)
            if path.suffix in {".dart", ".py"}
            else []
        )
        data_names = _environment_data_names_for_file(path, text)
        if class_names:
            failures.add(
                f"{path.relative_to(ROOT)} uses deployment-environment class names "
                f"{class_names} for an ordinary fixture/typed double"
            )
        if data_names:
            failures.add(
                f"{path.relative_to(ROOT)} uses deployment-environment fixture data "
                f"names {data_names}; use object/behavior fixture identities"
            )


def _app_user_acceptance_single_source_markers(
    path: Path,
    text: str,
    support_cache: dict[Path, bool] | None = None,
    source_texts: dict[Path, str] | None = None,
    snapshot_files: frozenset[Path] | None = None,
) -> list[str]:
    tokens = _c_style_tokens(text)
    identifiers = {value for kind, value in tokens if kind == "identifier"}
    markers: set[str] = set()
    call_names = {
        tokens[index][1]
        for index in range(len(tokens) - 1)
        if tokens[index][0] == "identifier"
        and tokens[index + 1] == ("punctuation", "(")
    }
    if "ProviderScope" in call_names:
        markers.add("ProviderScope")
    if "pumpWidget" in call_names:
        markers.add("pumpWidget")
    for index in range(len(tokens) - 2):
        if (
            tokens[index] == ("punctuation", ".")
            and tokens[index + 1][0] == "identifier"
            and tokens[index + 1][1] in {"overrideWith", "overrideWithValue"}
            and tokens[index + 2] == ("punctuation", "(")
        ):
            markers.add(tokens[index + 1][1])
        if (
            tokens[index] == ("identifier", "HttpOverrides")
            and tokens[index + 1] == ("punctuation", ".")
            and tokens[index + 2] == ("identifier", "global")
        ):
            markers.add("HttpOverrides.global")
    markers.update(lexical_substitute_names(path, text))
    markers.update(substitute_library_imports(path, text))
    markers.update(
        first_party_substitute_support_imports(
            path,
            text,
            support_cache,
            source_texts,
            snapshot_files,
        )
    )
    for identifier in {
        "buildAlphaCloudOverrides",
        "providerScopeOverrides",
        "repository_mock_reexports",
        "sourceEvidence",
        "requiredCaseIds",
    }:
        if identifier in identifiers:
            markers.add(identifier)
    if any(
        "coverage evidence is declared" in value
        for value in _source_string_literals(path, text)
    ):
        markers.add("coverage evidence is declared")
    return sorted(markers)


def app_user_acceptance_local_injection_markers(
    path: Path,
    text: str,
    support_cache: dict[Path, bool] | None = None,
    source_texts: dict[Path, str] | None = None,
    snapshot_files: frozenset[Path] | None = None,
) -> list[str]:
    """Inspect a UAT's complete Dart library closure from one source snapshot."""
    markers: set[str] = set()
    sources = _dart_library_source_texts(
        path,
        text,
        source_texts,
        snapshot_files,
    )
    for source, source_text in sources:
        markers.update(
            _app_user_acceptance_single_source_markers(
                source,
                source_text,
                support_cache,
                source_texts,
                snapshot_files,
            )
        )
    return sorted(markers)


def verify_all_test_sources(
    failures: Failures,
    all_files: list[Path] | None = None,
    text_cache: dict[Path, str] | None = None,
    snapshot_files: frozenset[Path] | None = None,
) -> None:
    cache = text_cache if text_cache is not None else {}
    paths = all_files if all_files is not None else scan_repository_files()
    support_cache: dict[Path, bool] = {}
    for path in paths:
        name = path.name
        is_canonical_test_source = (
            name.endswith(("_test.go", "_test.py", "_test.dart", "_test.ts"))
            or (name.startswith("test_") and name.endswith(".py"))
        )
        is_api_integration_source = (
            "api_integration" in path.parts
            and path.suffix in {".go", ".py", ".dart", ".ts"}
        )
        if is_api_integration_source:
            text = _read_text(path, cache)
            code_text = _lexical_code_text(path, text)
            for module in substitute_library_imports(path, text):
                failures.add(
                    f"{path.relative_to(ROOT)} imports in-process substitute "
                    f"library {module!r}"
                )
            for module in first_party_substitute_support_imports(
                path,
                text,
                support_cache,
                cache,
                snapshot_files,
            ):
                failures.add(
                    f"{path.relative_to(ROOT)} imports first-party substitute "
                    f"support {module!r} into api_integration"
                )
            for substitute_name in lexical_substitute_names(path, text):
                failures.add(
                    f"{path.relative_to(ROOT)} uses in-process substitute "
                    f"{substitute_name!r} in api_integration"
                )
            for marker in lexical_memory_modes(path, text):
                failures.add(
                    f"{path.relative_to(ROOT)} uses fake integration dependency "
                    f"{marker!r}"
                )
            if FAKE_BUILD_TAG_RE.search(text):
                failures.add(
                    f"{path.relative_to(ROOT)} is gated by a fake/mock/stub "
                    "build constraint"
                )
            for pattern in SKIP_PATTERNS:
                if pattern.search(code_text):
                    failures.add(
                        f"{path.relative_to(ROOT)} contains skip pattern "
                        f"{pattern.pattern!r}"
                    )
        if is_app_user_acceptance_source(path):
            text = _read_text(path, cache)
            for marker in app_user_acceptance_local_injection_markers(
                path,
                text,
                support_cache,
                cache,
                snapshot_files,
            ):
                failures.add(
                    f"{path.relative_to(ROOT)} injects local/mock state into App "
                    f"user-acceptance evidence {marker!r}"
                )
        if not is_canonical_test_source:
            continue
        text = _read_text(path, cache)
        code_text = _lexical_code_text(path, text)
        for pattern in SKIP_PATTERNS:
            if pattern.search(code_text):
                failures.add(
                    f"{path.relative_to(ROOT)} contains skip pattern {pattern.pattern!r}"
                )


def main() -> int:
    failures = Failures()
    all_files, text_cache = scan_repository_snapshot()
    snapshot_files = frozenset(path.resolve() for path in all_files)
    canonical_files = iter_canonical_files(all_files)
    verify_canonical_files(failures, canonical_files, text_cache)
    verify_all_test_sources(
        failures,
        all_files,
        text_cache,
        snapshot_files,
    )
    verify_app_local_fixture_naming(failures, all_files, text_cache)
    verify_test_artifacts(failures)
    return failures.exit_code()
