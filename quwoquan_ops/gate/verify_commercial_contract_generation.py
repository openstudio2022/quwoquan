#!/usr/bin/env python3
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-002
"""Verify one Graph drives fail-closed Go guards and typed Dart clients."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "quwoquan_service/generated/contract_graph.json"
LOCK = ROOT / "quwoquan_app/tool/cloud_codegen/contract_graph.lock.json"
GO_DESCRIPTORS = (
    ROOT
    / "quwoquan_service/generated/operationsecurity/descriptors.g.go"
)
DART_CLIENT = (
    ROOT
    / "quwoquan_app/packages/quwoquan_cloud_contracts/lib/src/generated/"
    "operation_contracts.g.dart"
)
SERVICE_ROOT = ROOT / "quwoquan_app/lib/service"


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.relative_to(ROOT)} root must be an object")
    return value


def _method_name(operation_id: str) -> str:
    parts = [part for part in re.split(r"[._-]+", operation_id) if part]
    if not parts:
        return ""
    return parts[0].lower() + "".join(
        part[:1].upper() + part[1:] for part in parts[1:]
    )


def _qualified_symbol_pattern(symbol: str) -> str:
    """Match a generated symbol with its optional domain import qualifier."""

    return rf"(?:[A-Za-z][A-Za-z0-9_]*\.)?{re.escape(symbol)}"


def _has_typed_method(
    source: str,
    *,
    response_type: str,
    method_name: str,
    transport: str,
) -> bool:
    return_type = "Stream" if transport == "sse" else "Future"
    return re.search(
        rf"\b{re.escape(return_type)}<{_qualified_symbol_pattern(response_type)}>\s+"
        rf"{re.escape(method_name)}\s*\(",
        source,
    ) is not None


def _has_response_decoder(source: str, decoder: str) -> bool:
    return re.search(
        rf"\bresponseDecoder:\s*{_qualified_symbol_pattern(decoder)}\b",
        source,
    ) is not None


def _has_typed_upgrade_descriptor(
    source: str,
    *,
    request_type: str,
    method_name: str,
    request_encoder: str,
) -> bool:
    qualified_request = _qualified_symbol_pattern(request_type)
    qualified_encoder = _qualified_symbol_pattern(request_encoder)
    return re.search(
        rf"\bstatic\s+final\s+CloudOperationUpgradeDescriptor<"
        rf"{qualified_request}>\s+{re.escape(method_name)}\s*=\s*"
        rf"CloudOperationUpgradeDescriptor<{qualified_request}>\s*\("
        rf"[\s\S]*?\boperation:\s*appCloudOperationContracts\["
        rf"AppCloudOperationIds\.{re.escape(method_name)}\]!\s*,"
        rf"[\s\S]*?\brequestEncoder:\s*{qualified_encoder}\s*,"
        rf"[\s\S]*?\)\s*;",
        source,
    ) is not None


def _generated_request_encoder_name(method_name: str) -> str:
    if not method_name:
        return ""
    return "encode" + method_name[:1].upper() + method_name[1:] + "GeneratedRequest"


def main() -> int:
    failures: list[str] = []
    for path in (GRAPH, LOCK, GO_DESCRIPTORS, DART_CLIENT):
        if not path.is_file():
            failures.append(f"missing generated artifact: {path.relative_to(ROOT)}")
    if failures:
        for failure in failures:
            print(f"[commercial-contract] FAIL: {failure}")
        return 1

    graph = _read_json(GRAPH)
    lock = _read_json(LOCK)
    graph_bytes = GRAPH.read_bytes()
    graph_sha = hashlib.sha256(graph_bytes).hexdigest()
    locked_graph = lock.get("contractGraph")
    if not isinstance(locked_graph, dict) or locked_graph.get("sha256") != graph_sha:
        failures.append("ContractGraph lock hash differs from generated bundle")

    raw_operations = graph.get("operations")
    if not isinstance(raw_operations, list):
        failures.append("ContractGraph.operations must be a list")
        raw_operations = []
    operations = [
        item for item in raw_operations if isinstance(item, dict)
    ]
    graph_ids = {
        str(item.get("id", "")).strip()
        for item in operations
        if str(item.get("id", "")).strip()
    }
    if len(graph_ids) != len(operations):
        failures.append("ContractGraph operation IDs are missing or duplicated")

    go_source = GO_DESCRIPTORS.read_text(encoding="utf-8")
    if f'const ContractGraphSHA256 = "{graph_sha}"' not in go_source:
        failures.append("Go security descriptor Graph hash is stale")
    go_ids = set(
        re.findall(r'CanonicalOperationID:\s+"([^"]+)"', go_source)
    )
    if go_ids != graph_ids:
        failures.append(
            "Go descriptor operation set differs from ContractGraph: "
            f"missing={sorted(graph_ids - go_ids)}, "
            f"orphan={sorted(go_ids - graph_ids)}"
        )

    lock_operations = lock.get("appExposedOperations")
    if not isinstance(lock_operations, list):
        failures.append("App lock appExposedOperations must be a list")
        lock_operations = []
    exposed = {
        str(item.get("canonicalOperationId", "")): item
        for item in lock_operations
        if isinstance(item, dict)
    }
    dart_source = DART_CLIENT.read_text(encoding="utf-8")
    if f"// ContractGraph SHA256: {graph_sha}" not in dart_source:
        failures.append("Dart operation client Graph hash is stale")
    for forbidden in (
        "Future<TResponse> execute<TResponse>",
        " as TResponse",
        ".execute<",
    ):
        if forbidden in dart_source:
            failures.append(f"Dart generated client retains raw ABI: {forbidden}")

    typed_exposed = 0
    ready_exposed = 0
    for operation in operations:
        operation_id = str(operation.get("id", ""))
        commercial = operation.get("commercial")
        status = (
            str(commercial.get("status", ""))
            if isinstance(commercial, dict)
            else ""
        )
        if status == "blocked":
            reason = str(commercial.get("blockReason", "")).strip()
            if not reason:
                failures.append(f"{operation_id}: blocked without blockReason")
        elif status == "ready":
            if operation_id in exposed:
                ready_exposed += 1
        else:
            failures.append(f"{operation_id}: invalid commercial status {status!r}")
        if operation_id not in exposed:
            continue
        typed_exposed += 1
        client = operation.get("clientContract")
        if not isinstance(client, dict):
            failures.append(f"{operation_id}: App operation lacks clientContract")
            continue
        method_name = _method_name(operation_id)
        response_body_kind = str(operation.get("responseBodyKind", "")).strip()
        if response_body_kind == "upgrade":
            request_type = str(operation.get("requestEntity", "")).strip()
            request_encoder = _generated_request_encoder_name(method_name)
            if not request_type:
                failures.append(f"{operation_id}: upgrade requestEntity is empty")
            elif not _has_typed_upgrade_descriptor(
                dart_source,
                request_type=request_type,
                method_name=method_name,
                request_encoder=request_encoder,
            ):
                failures.append(f"{operation_id}: typed upgrade descriptor missing")
            response_type = str(client.get("responseType", "")).strip() or "void"
            if _has_typed_method(
                dart_source,
                response_type=response_type,
                method_name=method_name,
                transport="json",
            ):
                failures.append(
                    f"{operation_id}: upgrade must not expose a JSON Future method"
                )
            continue
        response_type = str(client.get("responseType", "")).strip()
        if not response_type:
            failures.append(f"{operation_id}: responseType is empty")
            continue
        if not _has_typed_method(
            dart_source,
            response_type=response_type,
            method_name=method_name,
            transport=str(operation.get("transport", "")).strip(),
        ):
            failures.append(f"{operation_id}: typed Dart method missing")
        decoder = str(client.get("responseDecoder", "")).strip()
        if not decoder:
            failures.append(f"{operation_id}: responseDecoder is empty")
            continue
        if not _has_response_decoder(dart_source, decoder):
            failures.append(f"{operation_id}: response decoder not wired")
        response_body = str(operation.get("responseBody", "")).strip()
        if response_body and response_body_kind not in {"object", "page", "ack"}:
            failures.append(
                f"{operation_id}: responseBody requires explicit object/page/ack "
                f"responseBodyKind, got {response_body_kind!r}"
            )

    orphan_exposures = sorted(set(exposed) - graph_ids)
    if orphan_exposures:
        failures.append(
            f"App lock exposes operations absent from ContractGraph: {orphan_exposures}"
        )
    if typed_exposed != len(exposed):
        failures.append(
            "not every App-exposed operation was checked for a typed client: "
            f"checked={typed_exposed}, exposed={len(exposed)}"
        )
    if typed_exposed == 0:
        failures.append("no App-exposed operation has a typed client")

    for source_path in sorted(
        SERVICE_ROOT.glob("*_service/*/*/adapters/**/*.dart")
    ):
        source = source_path.read_text(encoding="utf-8")
        if re.search(r"\bGeneratedCloudOperationClient\b[\s\S]*?\.execute<", source):
            failures.append(
                f"{source_path.relative_to(ROOT)} uses retired generic execute<T>"
            )

    if failures:
        for failure in failures:
            print(f"[commercial-contract] FAIL: {failure}")
        return 1
    print(
        "[commercial-contract] OK: "
        f"graph={graph_sha}, operations={len(graph_ids)}, "
        f"App-exposed={len(exposed)}, typed={typed_exposed}, "
        f"commercial-ready={ready_exposed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
