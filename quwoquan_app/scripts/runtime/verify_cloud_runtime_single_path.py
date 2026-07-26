#!/usr/bin/env python3
"""Gate the generated-operation runtime path and Cloud dependency direction."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "quwoquan_app"
POLICY_PATH = ROOT / "quwoquan_ops/policies/gates/cloud_runtime_single_path_policy.json"
CLOUD_ROOT = APP / "lib/cloud"
GENERATED_ROOT = CLOUD_ROOT / "runtime/generated"
CONTRACTS_ROOT = APP / "packages/quwoquan_cloud_contracts/lib"
GENERATED_OPERATION_CONTRACTS = (
    CONTRACTS_ROOT / "src/generated/operation_contracts.g.dart"
)
FOUNDATION_FILES = (
    CLOUD_ROOT / "runtime/executor/generated_cloud_operation_executor.dart",
    CLOUD_ROOT / "runtime/http/cloud_http_client.dart",
    CLOUD_ROOT / "runtime/transport/cloud_json_transport.dart",
    CLOUD_ROOT / "runtime/errors/cloud_error_mapper.dart",
)
STRICT_DECODER_FILES = (
    CLOUD_ROOT / "runtime/codec/cloud_response_decoder.dart",
    CLOUD_ROOT / "runtime/codec/homepage_wire_codec.dart",
)
EXECUTION_RUNTIME_DIRS = (
    CLOUD_ROOT / "runtime/auth",
    CLOUD_ROOT / "runtime/codec",
    CLOUD_ROOT / "runtime/config",
    CLOUD_ROOT / "runtime/context",
    CLOUD_ROOT / "runtime/errors",
    CLOUD_ROOT / "runtime/executor",
    CLOUD_ROOT / "runtime/generated",
    CLOUD_ROOT / "runtime/http",
    CLOUD_ROOT / "runtime/observability",
    CLOUD_ROOT / "runtime/transport",
)

IMPORT_RE = re.compile(r"^\s*import\s+['\"]([^'\"]+)['\"]", re.MULTILINE)
EMPTY_CATCH_RE = re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}", re.MULTILINE)


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _read_policy() -> dict[str, object]:
    value = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("cloud runtime policy root must be an object")
    return value


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
    if target.startswith("package:quwoquan_app/cloud/services/"):
        return False
    if target.startswith("package:quwoquan_app/cloud/"):
        return target.startswith("package:quwoquan_app/cloud/runtime/") or bool(
            re.fullmatch(
                r"package:quwoquan_app/cloud/[a-z_]+/generated/[^/]+\.g\.dart",
                target,
            )
        )
    if target.startswith("package:"):
        return True
    resolved = (source_path.parent / target).resolve()
    return resolved.is_relative_to((CLOUD_ROOT / "runtime").resolve())


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
    if target == (
        "package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart"
    ):
        return True
    if target.startswith("package:quwoquan_app/cloud/runtime/generated/"):
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
    method_count = len(re.findall(r"^\s+Future<", client_source, re.MULTILINE))
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


def _check_migrated_adapters(
    policy: dict[str, object],
    failures: list[str],
) -> None:
    raw_roots = policy.get("adapter_roots")
    if not isinstance(raw_roots, list) or not raw_roots:
        failures.append("policy.adapter_roots must be a non-empty list")
        return
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
    adapter_paths: set[Path] = set()
    for root_value in raw_roots:
        if not isinstance(root_value, str):
            failures.append(f"invalid adapter root: {root_value!r}")
            continue
        root = ROOT / root_value
        if not root.is_dir():
            failures.append(f"adapter root missing: {root_value}")
            continue
        adapter_paths.update(root.rglob("*.dart"))

    governed_methods: set[str] = set()
    adapter_method_re = re.compile(r"\bclient\.([A-Za-z][A-Za-z0-9_]*)\(")
    for source_path in sorted(adapter_paths):
        source = source_path.read_text(encoding="utf-8")
        methods = adapter_method_re.findall(source)
        if not methods:
            continue
        path_value = _relative(source_path)
        if "GeneratedCloudOperationClient" not in source:
            failures.append(f"{path_value} does not inject generated client")
        for token in forbidden:
            if token in source:
                failures.append(
                    f"{path_value} retains retired runtime token {token}"
                )
        for method in methods:
            if method in governed_methods:
                failures.append(f"typed method has multiple adapter owners: {method}")
            governed_methods.add(method)

    if not governed_methods:
        failures.append("adapter roots contain no generated typed method owners")

    if GENERATED_OPERATION_CONTRACTS.is_file():
        operation_contracts = GENERATED_OPERATION_CONTRACTS.read_text(
            encoding="utf-8"
        )
        client_start = operation_contracts.find(
            "final class GeneratedCloudOperationClient"
        )
        contracts_start = operation_contracts.find(
            "const appCloudOperationContracts"
        )
        client_source = operation_contracts[client_start:contracts_start]
        generated_methods = set(
            re.findall(
                r"^\s+Future<[^\n]+>\s+([A-Za-z][A-Za-z0-9_]*)\(",
                client_source,
                re.MULTILINE,
            )
        )
        for method in sorted(generated_methods - governed_methods):
            failures.append(
                f"commercial-ready generated method has no migrated adapter owner: "
                f"{method}"
            )
        for method in sorted(governed_methods - generated_methods):
            failures.append(
                f"migrated adapter policy references non-ready generated method: "
                f"{method}"
            )


def _check_runtime_foundation(failures: list[str]) -> None:
    for source_path in FOUNDATION_FILES:
        if not source_path.is_file():
            failures.append(f"runtime foundation missing: {_relative(source_path)}")
            continue
        source = source_path.read_text(encoding="utf-8")
        if EMPTY_CATCH_RE.search(source):
            failures.append(f"{_relative(source_path)} contains an empty catch")

    executor = FOUNDATION_FILES[0].read_text(encoding="utf-8")
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
            failures.append(f"generated executor missing runtime marker: {marker}")
    if "Future<TResponse> execute<TResponse>" in executor:
        failures.append("generated executor restored retired execute<T> ABI")

    transport = FOUNDATION_FILES[2].read_text(encoding="utf-8")
    if "CloudErrorMapper.invalidResponse" not in transport:
        failures.append("generated transport can bypass structured RuntimeFailure")

    http_client = FOUNDATION_FILES[1].read_text(encoding="utf-8")
    for marker in ("AbortableRequest", "_sameOrigin", "'authorization'"):
        if marker not in http_client:
            failures.append(f"Cloud HTTP client missing security marker: {marker}")

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
    try:
        policy = _read_policy()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"[cloud-runtime-single-path] FAIL: {error}")
        return 1

    _check_execution_runtime_import_dag(failures)
    _check_generated_purity(failures)
    _check_migrated_adapters(policy, failures)
    _check_runtime_foundation(failures)

    if failures:
        for failure in failures:
            print(f"[cloud-runtime-single-path] FAIL: {failure}")
        return 1
    print(
        "[cloud-runtime-single-path] OK: "
        "deadline/cancel/retry/error/telemetry markers, generated purity, "
        "migrated adapters, and execution-runtime import DAG verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
