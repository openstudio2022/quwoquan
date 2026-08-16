#!/usr/bin/env python3
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-005
"""Gate the generated-operation runtime path and Cloud dependency direction."""

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

from _common.paths import REPO_ROOT

ROOT = REPO_ROOT
APP = ROOT / "quwoquan_app"
RUNTIME_ROOT = APP / "lib/runtime"
GENERATED_ROOT = RUNTIME_ROOT / "transport/generated"
CONTRACTS_ROOT = APP / "packages/quwoquan_cloud_contracts/lib"
GENERATED_OPERATION_CONTRACTS = (
    CONTRACTS_ROOT / "src/generated/operation_contracts.g.dart"
)
FOUNDATION_FILES = (
    RUNTIME_ROOT / "transport/executor/generated_cloud_operation_executor.dart",
    RUNTIME_ROOT / "transport/http/cloud_http_client.dart",
    RUNTIME_ROOT / "transport/cloud_json_transport.dart",
    RUNTIME_ROOT / "errors/cloud_error_mapper.dart",
)
STRICT_DECODER_FILES = (
    RUNTIME_ROOT / "codec/cloud_response_decoder.dart",
    APP / "lib/service/entity_service/entity_homepage/homepage/adapters/homepage_wire_codec.dart",
)
EXECUTION_RUNTIME_DIRS = (
    RUNTIME_ROOT / "codec",
    RUNTIME_ROOT / "config",
    RUNTIME_ROOT / "context",
    RUNTIME_ROOT / "transport/executor",
    RUNTIME_ROOT / "transport/http",
    RUNTIME_ROOT / "transport/models",
)
EXECUTION_RUNTIME_FILES = (
    RUNTIME_ROOT / "auth/cloud_auth_token_provider.dart",
    RUNTIME_ROOT / "auth/realtime_connection_credential.dart",
    RUNTIME_ROOT / "errors/cloud_error_mapper.dart",
    RUNTIME_ROOT / "errors/cloud_exception.dart",
    RUNTIME_ROOT / "errors/cloud_transport_failure.dart",
    RUNTIME_ROOT / "errors/domain_error_code.dart",
    RUNTIME_ROOT / "observability/cloud_operation_telemetry.dart",
    RUNTIME_ROOT / "transport/cloud_api_query_defaults.dart",
    RUNTIME_ROOT / "transport/cloud_json_transport.dart",
    RUNTIME_ROOT / "transport/cloud_request_headers.dart",
    RUNTIME_ROOT / "transport/cloud_retry_policy.dart",
)

IMPORT_RE = re.compile(r"^\s*import\s+['\"]([^'\"]+)['\"]", re.MULTILINE)
EMPTY_CATCH_RE = re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}", re.MULTILINE)
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
REMOTE_CONSTRUCTION_RE = re.compile(
    r"\b(Remote[A-Za-z0-9_]*)\s*\("
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


class GeneratedMethodMetadata(NamedTuple):
    canonical_operation_id: str
    domain: str
    transport: str


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _is_reverse_import(target: str) -> bool:
    if target == "dart:io":
        return True
    if target.startswith(
        (
            "package:flutter",
            "package:hive",
            "package:shared_preferences/",
            "package:livekit_client/",
            "package:path_provider/",
            "package:connectivity_plus/",
            "package:permission_handler/",
            "package:flutter_secure_storage/",
            "package:sqflite/",
        )
    ):
        return True
    return target.startswith(
        (
            "package:quwoquan_app/ui/",
            "package:quwoquan_app/app/",
            "package:quwoquan_app/core/",
            "package:quwoquan_app/l10n/",
        )
    )


def _is_execution_runtime_import_allowed(source_path: Path, target: str) -> bool:
    if target.startswith("dart:"):
        return target != "dart:io"
    if _is_reverse_import(target):
        return False
    if target.startswith(
        (
            "package:quwoquan_app/cloud/remote/",
            "package:quwoquan_app/cloud/services/",
        )
    ):
        return False
    if target.startswith("package:quwoquan_app/runtime/"):
        return True
    if target.startswith("package:quwoquan_app/cloud/"):
        return target.startswith(
            "package:quwoquan_app/cloud/runtime/generated/"
        ) or bool(
            re.fullmatch(
                r"package:quwoquan_app/cloud/[a-z_]+/generated/[^/]+\.g\.dart",
                target,
            )
        )
    if target.startswith("package:"):
        return True
    resolved = (source_path.parent / target).resolve()
    return resolved.is_relative_to(RUNTIME_ROOT.resolve())


def _check_execution_runtime_import_dag(failures: list[str]) -> None:
    """Runtime execution foundation only depends inward or on pure packages."""
    observed_paths: set[Path] = set()
    for directory in EXECUTION_RUNTIME_DIRS:
        if not directory.is_dir():
            failures.append(
                f"execution runtime directory missing: {_relative(directory)}"
            )
            continue
        observed_paths.update(directory.rglob("*.dart"))
    for source_path in EXECUTION_RUNTIME_FILES:
        if not source_path.is_file():
            failures.append(
                f"execution runtime source missing: {_relative(source_path)}"
            )
            continue
        observed_paths.add(source_path)
    for source_path in sorted(observed_paths):
        source = source_path.read_text(encoding="utf-8")
        for target in IMPORT_RE.findall(source):
            if not _is_execution_runtime_import_allowed(source_path, target):
                failures.append(
                    "execution runtime import escapes DAG: "
                    f"{_relative(source_path)} -> {target}"
                )


def _is_generated_import_allowed(source_path: Path, target: str) -> bool:
    if target.startswith("dart:"):
        return True
    if target == "package:quwoquan_app/runtime/codec/cloud_wire_json_types.dart":
        return True
    if target.startswith("package:quwoquan_app/cloud/runtime/generated/"):
        return True
    if target.startswith("package:quwoquan_cloud_contracts/"):
        # Generated runtime payloads may reuse enums and value objects from the
        # pure generated-contract package.  Duplicating those definitions would
        # create a second wire truth source.
        return True
    if target.startswith("package:"):
        return False
    resolved = (source_path.parent / target).resolve()
    return resolved.is_relative_to(GENERATED_ROOT.resolve())


def _check_generated_purity(failures: list[str]) -> None:
    generated_files = sorted(GENERATED_ROOT.rglob("*.g.dart"))
    if not generated_files:
        failures.append("no generated Cloud Dart artifacts found")
    for source_path in generated_files:
        source = source_path.read_text(encoding="utf-8")
        header = "\n".join(source.splitlines()[:3]).lower()
        if "generated" not in header or "do not edit" not in header:
            failures.append(f"{_relative(source_path)} lacks generated provenance")
        for target in IMPORT_RE.findall(source):
            if not _is_generated_import_allowed(source_path, target):
                failures.append(
                    f"generated Cloud artifact imports non-runtime owner: "
                    f"{_relative(source_path)} -> {target}"
                )

    for source_path in sorted(CONTRACTS_ROOT.rglob("*.dart")):
        source = source_path.read_text(encoding="utf-8")
        for target in IMPORT_RE.findall(source):
            if target.startswith("dart:"):
                continue
            if target.startswith("package:"):
                failures.append(
                    f"pure contracts package imports external package: "
                    f"{_relative(source_path)} -> {target}"
                )
                continue
            resolved = (source_path.parent / target).resolve()
            if not resolved.is_relative_to(CONTRACTS_ROOT.resolve()):
                failures.append(
                    f"pure contracts import escapes package: "
                    f"{_relative(source_path)} -> {target}"
                )

    if not GENERATED_OPERATION_CONTRACTS.is_file():
        failures.append("generated operation contracts are missing")
        return
    operation_contracts = GENERATED_OPERATION_CONTRACTS.read_text(
        encoding="utf-8"
    )
    client_start = operation_contracts.find(
        "final class GeneratedCloudOperationClient"
    )
    contracts_start = operation_contracts.find(
        "const appCloudOperationContracts"
    )
    if client_start < 0 or contracts_start <= client_start:
        failures.append("generated typed operation client boundary is malformed")
        return
    client_source = operation_contracts[client_start:contracts_start]
    try:
        generated_methods, generated_upgrades, _ = _parse_generated_surface(
            operation_contracts
        )
    except ValueError as error:
        failures.append(str(error))
        generated_methods = frozenset()
        generated_upgrades = frozenset()
    upgrade_identifier_hits = re.findall(
        r"^\s+static final CloudOperationUpgradeDescriptor<[^>]+>\s+"
        r"([A-Za-z][A-Za-z0-9_]*)\s*=",
        operation_contracts,
        re.MULTILINE,
    )
    upgrade_contract_count = len(
        re.findall(
            r'^\s+responseBodyKind:\s+"upgrade",',
            operation_contracts,
            re.MULTILINE,
        )
    )
    if len(upgrade_identifier_hits) != len(generated_upgrades):
        failures.append("generated upgrade descriptor identifiers are duplicated")
    if upgrade_contract_count != len(generated_upgrades):
        failures.append(
            "generated upgrade descriptor count does not match upgrade "
            f"contracts: descriptors={len(generated_upgrades)}, "
            f"contracts={upgrade_contract_count}"
        )
    overlap = generated_methods & generated_upgrades
    if overlap:
        failures.append(
            "upgrade operation was also emitted as a JSON client method: "
            + ", ".join(sorted(overlap))
        )
    method_count = len(generated_methods)
    encoder_count = client_source.count("requestEncoder:")
    if method_count == 0:
        failures.append("generated typed operation client has no ready methods")
    if encoder_count != method_count:
        failures.append(
            "every generated typed operation method must pass its encoder "
            f"into the executor: methods={method_count}, encoders={encoder_count}"
        )
    if "final payload =" in client_source:
        failures.append(
            "generated typed client executes request encoder outside executor"
        )
    upgrade_descriptors_start = operation_contracts.find(
        "abstract final class AppCloudOperationUpgradeDescriptors"
    )
    upgrade_descriptors_source = (
        operation_contracts[upgrade_descriptors_start:]
        if upgrade_descriptors_start >= 0
        else ""
    )
    upgrade_encoder_count = upgrade_descriptors_source.count("requestEncoder:")
    if upgrade_encoder_count != len(generated_upgrades):
        failures.append(
            "every generated upgrade descriptor must retain its typed encoder: "
            f"descriptors={len(generated_upgrades)}, "
            f"encoders={upgrade_encoder_count}"
        )
    executor_start = operation_contracts.find(
        "abstract interface class CloudOperationExecutor"
    )
    generated_client_start = operation_contracts.find(
        "final class GeneratedCloudOperationClient"
    )
    if executor_start < 0 or generated_client_start <= executor_start:
        failures.append("generated operation executor ABI is malformed")
        return
    executor_contract = operation_contracts[
        executor_start:generated_client_start
    ]
    if "required CloudOperationRequestEncoder requestEncoder" not in executor_contract:
        failures.append("generated executor ABI does not require typed encoder")
    for retired_raw_argument in (
        "Map<String, String> pathParameters",
        "Map<String, String> queryParameters",
        "Object? body",
    ):
        if retired_raw_argument in executor_contract:
            failures.append(
                "generated executor ABI retains raw request argument: "
                f"{retired_raw_argument}"
            )


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


def _analyze_method_owners(
    app_root: Path,
    generated_methods: Iterable[str],
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
        missing=frozenset(without_canonical - legacy_methods),
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


def _parse_generated_surface(
    source: str,
) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    client_start = source.find("final class GeneratedCloudOperationClient")
    contracts_start = source.find("const appCloudOperationContracts")
    if client_start < 0 or contracts_start <= client_start:
        raise ValueError("generated typed operation client boundary is malformed")
    client_source = source[client_start:contracts_start]
    methods = frozenset(
        re.findall(
            r"^\s+(?:Future|Stream)<[^\n]+>\s+"
            r"([A-Za-z][A-Za-z0-9_]*)\(",
            client_source,
            re.MULTILINE,
        )
    )
    upgrade_identifiers = re.findall(
        r"^\s+static final CloudOperationUpgradeDescriptor<[^>]+>\s+"
        r"([A-Za-z][A-Za-z0-9_]*)\s*=",
        source,
        re.MULTILINE,
    )
    upgrades = frozenset(upgrade_identifiers)
    domains = frozenset(
        re.findall(r'^\s+domain:\s+"([a-z][a-z0-9_]*)",', source, re.MULTILINE)
    )
    if not methods:
        raise ValueError("generated typed operation client has no ready methods")
    if not domains:
        raise ValueError("generated operation contracts expose no App domains")
    return methods, upgrades, domains


def _parse_generated_method_metadata(
    source: str, generated_methods: Iterable[str]
) -> dict[str, GeneratedMethodMetadata]:
    canonical_to_identifier = {
        canonical: identifier
        for identifier, canonical in re.findall(
            r'^\s+static const String ([A-Za-z][A-Za-z0-9_]*) = "([^"]+)";', source, re.MULTILINE
        )
    }
    ready_methods = frozenset(generated_methods)
    result: dict[str, GeneratedMethodMetadata] = {}
    for match in re.finditer(
        r'^  "(?P<canonical>[^"]+)": CloudOperationContract\(\n'
        r'(?P<body>.*?)(?=\n  "[^"]+": CloudOperationContract\(|\n\};)',
        source, re.MULTILINE | re.DOTALL,
    ):
        canonical_id = match.group("canonical")
        identifier = canonical_to_identifier.get(canonical_id)
        if identifier not in ready_methods:
            continue
        body = match.group("body")
        fields = tuple(re.search(rf'{name}: "([^"]+)"', body) for name in ("domain", "transport"))
        if any(field is None for field in fields):
            raise ValueError(
                f"generated method metadata is incomplete: {canonical_id}"
            )
        domain, transport = (field.group(1) for field in fields if field is not None)
        result[identifier] = GeneratedMethodMetadata(canonical_id, domain, transport)
    missing = ready_methods - frozenset(result)
    if missing:
        raise ValueError("generated methods have no operation metadata: " + ", ".join(sorted(missing)))
    return result


def _check_graphql_method_owners(
    app_root: Path, metadata: dict[str, GeneratedMethodMetadata], failures: list[str]
) -> int:
    graphql_methods = {
        key: value for key, value in metadata.items() if value.transport == "graphql"
    }
    generated_files = tuple(sorted((app_root / "lib/runtime/transport/graphql_read/generated").rglob("*.g.dart")))
    adapter_paths = _canonical_adapter_paths(app_root)
    owned = 0
    for identifier, item in sorted(graphql_methods.items()):
        descriptor_files = tuple(
            path for path in generated_files
            if item.canonical_operation_id in path.read_text(encoding="utf-8")
        )
        if len(descriptor_files) != 1:
            failures.append(
                "GraphQL operation must have exactly one specialized generated "
                f"descriptor: {identifier} -> {_format_paths(descriptor_files)}"
            )
            continue
        generated_source = descriptor_files[0].read_text(encoding="utf-8")
        client_classes = tuple(
            sorted(set(re.findall(
                r"\bfinal class (Generated[A-Za-z0-9_]*GraphQLClient)\b",
                generated_source,
            )))
        )
        if len(client_classes) != 1:
            failures.append(
                "GraphQL descriptor must define exactly one generated client: "
                f"{identifier} -> {_display_path(descriptor_files[0])}"
            )
            continue
        client_class = client_classes[0]
        owners = tuple(
            path for path in adapter_paths if client_class in path.read_text(encoding="utf-8")
        )
        if len(owners) != 1:
            failures.append(
                "GraphQL generated client must have exactly one canonical adapter "
                f"owner: {identifier} -> {_format_paths(owners)}"
            )
            continue
        owned += 1
    return owned


def _format_paths(paths: Iterable[Path]) -> str:
    return ", ".join(_display_path(path) for path in paths)


def _check_adapter_owners(report: OwnerReport, failures: list[str]) -> None:
    forbidden = (
        "CloudHttpClient",
        "CloudRequestHeaders",
        "CloudRuntimeConfig",
        "appCloudOperationContracts",
        ".execute<",
        ".send<",
        "catch (",
        "catch(",
    )
    canonical_owner_paths = {
        path for paths in report.canonical_owners.values() for path in paths
    }
    if not report.canonical_paths:
        failures.append("canonical object adapter tree contains no Dart sources")
    if not report.canonical_owners:
        failures.append("canonical object adapters contain no generated method owners")
    for source_path in sorted(canonical_owner_paths):
        code = _without_dart_non_code(source_path.read_text(encoding="utf-8"))
        for token in forbidden:
            if token in code:
                failures.append(
                    f"{_display_path(source_path)} retains retired runtime token "
                    f"{token}"
                )

    for source_path in report.legacy_paths:
        failures.append(
            "legacy Cloud path must migrate to its canonical object adapter: "
            f"{_display_path(source_path)}"
        )
    for method, owner_paths in report.duplicates.items():
        failures.append(
            f"typed method has multiple canonical adapter owners: {method} -> "
            f"{_format_paths(owner_paths)}"
        )
    for method in sorted(report.missing):
        failures.append(
            f"generated method has no canonical or legacy adapter reference: {method}"
        )
    for method in sorted(report.legacy_only):
        failures.append(
            f"generated method is referenced only from a legacy Cloud path: "
            f"{method} -> {_format_paths(report.legacy_references[method])}"
        )
    for method in sorted(report.legacy_overlap):
        failures.append(
            f"generated method retains a legacy reference beside its canonical "
            f"owner: {method} -> {_format_paths(report.legacy_references[method])}"
        )
    for method in sorted(report.non_ready):
        failures.append(
            f"canonical adapter references non-ready generated method: {method}"
        )
    for method in sorted(report.legacy_non_ready):
        failures.append(
            f"legacy Cloud path references non-ready generated method: {method}"
        )


def _check_upgrade_owners(
    report: UpgradeOwnerReport,
    failures: list[str],
) -> None:
    for identifier, owner_paths in report.duplicates.items():
        failures.append(
            "upgrade descriptor has multiple canonical adapter owners: "
            f"{identifier} -> {_format_paths(owner_paths)}"
        )
    for identifier in sorted(report.missing):
        failures.append(
            "generated upgrade descriptor has no canonical or legacy adapter "
            f"owner: {identifier}"
        )
    for identifier in sorted(report.legacy_only):
        failures.append(
            "generated upgrade descriptor is owned only by a legacy Cloud path: "
            f"{identifier} -> {_format_paths(report.legacy_references[identifier])}"
        )
    for identifier in sorted(report.legacy_overlap):
        failures.append(
            "generated upgrade descriptor retains a legacy reference beside its "
            f"canonical owner: {identifier} -> "
            f"{_format_paths(report.legacy_references[identifier])}"
        )
    for identifier, owner_paths in report.canonical_owners.items():
        for source_path in owner_paths:
            code = _without_dart_non_code(
                source_path.read_text(encoding="utf-8")
            )
            uses_descriptor = "AppCloudOperationUpgradeDescriptors" in code
            uses_canonical_contract = all(
                token in code
                for token in (
                    "appCloudOperationContracts",
                    "pathTemplate",
                    "responseBodyKind",
                )
            )
            if not uses_descriptor and not uses_canonical_contract:
                failures.append(
                    "upgrade owner does not consume its generated descriptor or "
                    "canonical operation contract: "
                    f"{identifier} -> {_display_path(source_path)}"
                )
    for identifier in sorted(report.missing_executors):
        failures.append(
            "generated upgrade descriptor has no protocol-specific WebSocket "
            f"executor beside its canonical owner: {identifier}"
        )


def _domain_class_prefix(domain: str) -> str:
    return "".join(part.capitalize() for part in domain.split("_"))


def _check_domain_compositions(
    app_root: Path,
    generated_domains: Iterable[str],
    failures: list[str],
) -> tuple[int, int]:
    domains = tuple(sorted(set(generated_domains)))
    present = 0
    for domain in domains:
        composition_path = (
            app_root / "lib/runtime/di" / f"{domain}_dependencies.dart"
        )
        if not composition_path.is_file():
            failures.append(
                f"App-exposed domain composition missing: "
                f"{_display_path(composition_path)}"
            )
            continue
        present += 1
        code = _without_dart_non_code(
            composition_path.read_text(encoding="utf-8")
        )
        class_name = f"{_domain_class_prefix(domain)}ProductionComposition"
        if not re.search(rf"\bclass\s+{re.escape(class_name)}\b", code):
            failures.append(
                f"domain composition lacks canonical {class_name}: "
                f"{_display_path(composition_path)}"
            )
        if "GeneratedCloudOperationClient" not in code:
            failures.append(
                f"domain composition does not inject generated client: "
                f"{_display_path(composition_path)}"
            )
    return len(domains), present


def _collect_provider_remote_constructions(
    app_root: Path,
) -> dict[Path, tuple[tuple[str, int], ...]]:
    constructions: dict[Path, tuple[tuple[str, int], ...]] = {}
    di_root = app_root / "lib/runtime/di"
    for source_path in sorted(di_root.glob("app_providers*.dart")):
        code = _without_dart_non_code(source_path.read_text(encoding="utf-8"))
        observed = tuple(
            (match.group(1), code.count("\n", 0, match.start()) + 1)
            for match in REMOTE_CONSTRUCTION_RE.finditer(code)
        )
        if observed:
            constructions[source_path] = observed
    return constructions


def _check_provider_composition_ownership(
    constructions: dict[Path, tuple[tuple[str, int], ...]],
    failures: list[str],
) -> None:
    for source_path, observed in constructions.items():
        for symbol, line in observed:
            failures.append(
                "central Provider constructs Remote outside domain composition: "
                f"{_display_path(source_path)}:{line} -> {symbol}"
            )


def _check_runtime_foundation(failures: list[str]) -> None:
    foundation_sources: dict[Path, str] = {}
    for source_path in FOUNDATION_FILES:
        if not source_path.is_file():
            failures.append(f"runtime foundation missing: {_relative(source_path)}")
            continue
        source = source_path.read_text(encoding="utf-8")
        foundation_sources[source_path] = source
        if EMPTY_CATCH_RE.search(source):
            failures.append(f"{_relative(source_path)} contains an empty catch")

    executor = foundation_sources.get(FOUNDATION_FILES[0])
    if executor is not None:
        for marker in (
            "operation.timeoutMilliseconds",
            "context.cancellation",
            "operation.maxAttempts",
            "operation.idempotency",
            "requestEncoder()",
            "payload.pathParameters",
            "payload.queryParameters",
            "refreshAuthorization",
            "retryReason",
            "recoveryAction",
            "disruptionLevel",
            "responseDecoder(response)",
        ):
            if marker not in executor:
                failures.append(
                    f"generated executor missing runtime marker: {marker}"
                )
        if "Future<TResponse> execute<TResponse>" in executor:
            failures.append("generated executor restored retired execute<T> ABI")
        if "operation.commercialStatus != 'ready'" in executor:
            failures.append(
                "generated executor treats release evidence as a runtime feature flag"
            )

    transport = foundation_sources.get(FOUNDATION_FILES[2])
    if (
        transport is not None
        and "CloudErrorMapper.invalidResponse" not in transport
    ):
        failures.append("generated transport can bypass structured RuntimeFailure")

    http_client = foundation_sources.get(FOUNDATION_FILES[1])
    if http_client is not None:
        for marker in ("AbortableRequest", "_sameOrigin", "'authorization'"):
            if marker not in http_client:
                failures.append(
                    f"Cloud HTTP client missing security marker: {marker}"
                )

    for decoder_path in STRICT_DECODER_FILES:
        if not decoder_path.is_file():
            failures.append(f"strict Cloud decoder missing: {_relative(decoder_path)}")
            continue
        decoder = decoder_path.read_text(encoding="utf-8")
        if "CloudErrorMapper.invalidResponse" not in decoder:
            failures.append(
                f"{_relative(decoder_path)} can bypass structured RuntimeFailure"
            )
        if "continue;" in decoder:
            failures.append(
                f"{_relative(decoder_path)} silently skips malformed wire elements"
            )


def main() -> int:
    failures: list[str] = []
    generated_methods: frozenset[str] = frozenset()
    generated_upgrades: frozenset[str] = frozenset()
    generated_domains: frozenset[str] = frozenset()
    generated_method_metadata: dict[str, GeneratedMethodMetadata] = {}
    try:
        generated_source = GENERATED_OPERATION_CONTRACTS.read_text(encoding="utf-8")
        generated_methods, generated_upgrades, generated_domains = (
            _parse_generated_surface(generated_source)
        )
        generated_method_metadata = _parse_generated_method_metadata(
            generated_source,
            generated_methods,
        )
    except (OSError, ValueError) as error:
        failures.append(str(error))
    _check_execution_runtime_import_dag(failures)
    _check_generated_purity(failures)
    graphql_methods = frozenset(
        key for key, value in generated_method_metadata.items() if value.transport == "graphql"
    )
    json_methods = generated_methods - graphql_methods
    owner_report = _analyze_method_owners(APP, json_methods)
    _check_adapter_owners(owner_report, failures)
    graphql_owned_methods = _check_graphql_method_owners(APP, generated_method_metadata, failures)
    upgrade_report = _analyze_upgrade_owners(APP, generated_upgrades)
    _check_upgrade_owners(upgrade_report, failures)
    graphql_domains = {
        value.domain for value in generated_method_metadata.values()
        if value.transport == "graphql"
    }
    non_graphql_domains = {
        value.domain for value in generated_method_metadata.values()
        if value.transport != "graphql"
    }
    composition_domains = generated_domains - (graphql_domains - non_graphql_domains)
    composition_expected, composition_present = _check_domain_compositions(
        APP,
        composition_domains,
        failures,
    )
    provider_constructions = _collect_provider_remote_constructions(APP)
    _check_provider_composition_ownership(provider_constructions, failures)
    _check_runtime_foundation(failures)

    canonical_owner_references = sum(map(len, owner_report.canonical_owners.values()))
    canonical_owned_methods = len(frozenset(owner_report.canonical_owners) & json_methods)
    canonical_upgrade_owner_references = sum(map(len, upgrade_report.canonical_owners.values()))
    canonical_owned_upgrades = len(
        frozenset(upgrade_report.canonical_owners) & generated_upgrades
    )
    legacy_method_references = sum(map(len, owner_report.legacy_references.values()))
    provider_construction_count = sum(map(len, provider_constructions.values()))
    print(
        "[cloud-runtime-single-path] OWNER_MASS: "
        f"generated={len(generated_methods) + len(generated_upgrades)}, "
        f"json_methods={len(json_methods)}, "
        f"graphql_methods={len(graphql_methods)}, "
        f"upgrade_descriptors={len(generated_upgrades)}, "
        f"canonical_adapter_files={len(owner_report.canonical_paths)}, "
        f"canonical_owner_references="
        f"{canonical_owner_references + canonical_upgrade_owner_references}, "
        f"canonical_owned="
        f"{canonical_owned_methods + graphql_owned_methods + canonical_owned_upgrades}, "
        f"missing={len(owner_report.missing) + len(upgrade_report.missing)}, "
        f"duplicates="
        f"{len(owner_report.duplicates) + len(upgrade_report.duplicates)}, "
        f"upgrade_executors={len(upgrade_report.executors)}, "
        f"legacy_paths={len(owner_report.legacy_paths)}, "
        f"legacy_method_references={legacy_method_references}, "
        f"legacy_only={len(owner_report.legacy_only)}, "
        f"legacy_overlap={len(owner_report.legacy_overlap)}, "
        f"composition={composition_present}/{composition_expected}, "
        f"provider_remote_constructions={provider_construction_count}"
    )

    if failures:
        for failure in failures:
            print(f"[cloud-runtime-single-path] FAIL: {failure}")
        return 1
    print(
        "[cloud-runtime-single-path] OK: "
        "deadline/cancel/retry/error/telemetry markers, generated purity, "
        "canonical object adapters, domain composition, and execution-runtime "
        "import DAG verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
