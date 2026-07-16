#!/usr/bin/env python3
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
REMOTE_ROOT = ROOT / "quwoquan_app/lib/cloud/services"


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
            continue
        if status != "ready":
            failures.append(f"{operation_id}: invalid commercial status {status!r}")
            continue
        if operation_id not in exposed:
            continue
        ready_exposed += 1
        client = operation.get("clientContract")
        if not isinstance(client, dict):
            failures.append(f"{operation_id}: ready App operation lacks clientContract")
            continue
        method_name = _method_name(operation_id)
        response_type = str(client.get("responseType", ""))
        signature = f"Future<{response_type}> {method_name}("
        if signature not in dart_source:
            failures.append(f"{operation_id}: typed Dart method missing")
        decoder = str(client.get("responseDecoder", ""))
        if f"responseDecoder: {decoder}" not in dart_source:
            failures.append(f"{operation_id}: response decoder not wired")
        response_body = str(operation.get("responseBody", "")).strip()
        response_body_kind = str(operation.get("responseBodyKind", "")).strip()
        if response_body and response_body_kind not in {"object", "page", "ack"}:
            failures.append(
                f"{operation_id}: responseBody requires explicit object/page/ack "
                f"responseBodyKind, got {response_body_kind!r}"
            )

    if ready_exposed == 0:
        failures.append("no commercial-ready App operation has a typed client")

    for source_path in sorted(REMOTE_ROOT.rglob("*.dart")):
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
        f"App-exposed={len(exposed)}, typed-ready={ready_exposed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
