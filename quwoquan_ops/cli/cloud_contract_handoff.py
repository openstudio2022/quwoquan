#!/usr/bin/env python3
"""内容寻址 ContractGraph 到 App-only emitter 的交接门。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GRAPH = ROOT / "quwoquan_service/generated/contract_graph.json"
DEFAULT_POLICY = ROOT / "quwoquan_ops/policies/cloud_contract_ownership.json"
DEFAULT_LOCK = ROOT / "quwoquan_app/tool/cloud_codegen/contract_graph.lock.json"
DEFAULT_REPORT = (
    ROOT / "quwoquan_app/tool/cloud_codegen/contract_graph.breaking.json"
)
GENERATOR = "app-cloud-handoff"


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"缺少交接输入: {path.relative_to(ROOT)}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 无法解析: {path.relative_to(ROOT)}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON 根必须是对象: {path.relative_to(ROOT)}")
    return value


def atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_bytes(value)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def compiler_digest() -> str:
    roots = (
        ROOT / "quwoquan_service/internal/metadata/ast",
        ROOT / "quwoquan_service/internal/metadata/compiler",
        ROOT / "quwoquan_service/internal/metadata/graph",
        ROOT / "quwoquan_service/internal/metadata/load",
        ROOT / "quwoquan_service/internal/metadata/validate",
    )
    entries: list[tuple[str, str]] = []
    for directory in roots:
        for path in sorted(directory.rglob("*.go")):
            entries.append((relative(path), sha256_bytes(path.read_bytes())))
    if not entries:
        raise ValueError("ContractGraph compiler 输入为空")
    return f"sha256:{sha256_bytes(canonical_bytes(entries))}"


def validate_graph(graph: dict[str, Any]) -> None:
    for retired_field in ("version", "schema", "registryRevision"):
        if retired_field in graph:
            raise ValueError(f"ContractGraph 禁止退休字段: {retired_field}")
    if not isinstance(graph.get("businessObjectMaps"), list):
        raise ValueError("ContractGraph.businessObjectMaps 必须是数组")
    for key in ("objects", "operations", "projections", "sources", "documents"):
        if not isinstance(graph.get(key), list):
            raise ValueError(f"ContractGraph.{key} 必须是数组")
    operation_ids = [
        str(item.get("id", "")).strip()
        for item in graph["operations"]
        if isinstance(item, dict)
    ]
    if not operation_ids or any(not value for value in operation_ids):
        raise ValueError("ContractGraph operation canonical id 不完整")
    if len(operation_ids) != len(set(operation_ids)):
        raise ValueError("ContractGraph canonical operation id 不唯一")
    for source in graph["sources"]:
        if not isinstance(source, dict):
            raise ValueError("ContractGraph source 必须是对象")
        digest = str(source.get("sha256", ""))
        if len(digest) != 64:
            raise ValueError(f"source digest 非 SHA256: {source.get('path')}")


def source_digest_set_sha(graph: dict[str, Any]) -> str:
    sources = sorted(
        (
            str(item["path"]),
            str(item["sha256"]),
        )
        for item in graph["sources"]
    )
    return sha256_bytes(canonical_bytes(sources))


def document_index(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in graph["documents"]:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", ""))
        content = item.get("content")
        if path and isinstance(content, dict):
            result[path] = content
    return result


def auth_mode(route: dict[str, Any]) -> str:
    security = route.get("security")
    if isinstance(security, dict):
        mode = str(security.get("auth_mode", "")).strip().lower()
        if mode in {"public", "optional", "required"}:
            return mode
    declared_mode = str(route.get("auth", "")).strip().lower()
    if declared_mode in {"public", "optional", "required"}:
        return declared_mode
    required = route.get("auth_required")
    if isinstance(required, bool):
        return "required" if required else "public"
    return "required"


def route_index(
    graph: dict[str, Any],
) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    result: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for source_path, content in document_index(graph).items():
        routes = content.get("api_routes")
        if not isinstance(routes, list):
            continue
        for route in routes:
            if not isinstance(route, dict):
                continue
            key = (
                source_path,
                str(route.get("operation", "")).strip(),
                str(route.get("method", "")).strip().upper(),
                str(route.get("path", "")).strip(),
            )
            if all(key):
                result[key] = route
    return result


def resolve_exposures(
    graph: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    documents = document_index(graph)
    ui = documents.get("_shared/ui_surfaces.yaml", {})
    surfaces = ui.get("surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        raise ValueError("ContractGraph 缺少 App ui_surfaces 显式 exposure")

    operations = [
        item for item in graph["operations"] if isinstance(item, dict)
    ]
    by_local: dict[str, list[dict[str, Any]]] = {}
    for operation in operations:
        local_id = str(operation.get("localId", "")).strip()
        if local_id:
            by_local.setdefault(local_id, []).append(operation)

    resolved: dict[str, dict[str, Any]] = {}
    unresolved: list[dict[str, str]] = []
    for surface in surfaces:
        if not isinstance(surface, dict):
            continue
        surface_id = str(surface.get("id", "")).strip()
        owner = str(surface.get("owner", "")).strip()
        operation_ids = surface.get("operation_ids")
        if not isinstance(operation_ids, list):
            continue
        for local_id_value in operation_ids:
            local_id = str(local_id_value).strip()
            candidates = by_local.get(local_id, [])
            owned = [
                item for item in candidates if str(item.get("domain", "")) == owner
            ]
            selected = owned if len(owned) == 1 else candidates
            if len(selected) != 1:
                unresolved.append(
                    {
                        "surfaceId": surface_id,
                        "owner": owner,
                        "localOperationId": local_id,
                        "candidateCanonicalIds": ",".join(
                            sorted(str(item.get("id", "")) for item in candidates)
                        ),
                    }
                )
                continue
            canonical_id = str(selected[0]["id"])
            entry = resolved.setdefault(
                canonical_id,
                {
                    "canonicalOperationId": canonical_id,
                    "localOperationId": local_id,
                    "surfaceIds": [],
                },
            )
            entry["surfaceIds"].append(surface_id)

    for entry in resolved.values():
        entry["surfaceIds"] = sorted(set(entry["surfaceIds"]))
    return (
        sorted(resolved.values(), key=lambda item: item["canonicalOperationId"]),
        sorted(
            unresolved,
            key=lambda item: (item["surfaceId"], item["localOperationId"]),
        ),
    )


def operation_snapshots(
    graph: dict[str, Any],
    exposures: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {
        str(item["id"]): item
        for item in graph["operations"]
        if isinstance(item, dict)
    }
    routes = route_index(graph)
    result: list[dict[str, Any]] = []
    for exposure in exposures:
        canonical_id = exposure["canonicalOperationId"]
        operation = by_id[canonical_id]
        route = routes.get(
            (
                str(operation.get("sourcePath", "")),
                str(operation.get("localId", "")),
                str(operation.get("method", "")).upper(),
                str(operation.get("pathTemplate", "")),
            ),
            {},
        )
        result.append(
            {
                **exposure,
                "domain": str(operation.get("domain", "")),
                "objectId": str(operation.get("objectId", "")),
                "kind": str(operation.get("kind", "")),
                "facet": str(operation.get("facet", "")),
                "facadeMethod": str(operation.get("facadeMethod", "")),
                "aggregateOwner": str(
                    operation.get("aggregateOwner", "")
                ),
                "mutationTarget": str(
                    operation.get("mutationTarget", "")
                ),
                "invariantTarget": str(
                    operation.get("invariantTarget", "")
                ),
                "method": str(operation.get("method", "")).upper(),
                "pathTemplate": str(operation.get("pathTemplate", "")),
                "actorRequirement": str(
                    operation.get("actorRequirement", "")
                ),
                "authMode": auth_mode(route),
                "principal": str(operation.get("principal", "")),
                "scopes": list(operation.get("scopes", [])),
                "permissions": list(operation.get("permissions", [])),
                "ownershipPolicy": str(
                    operation.get("ownershipPolicy", "")
                ),
                "commercial": operation.get("commercial", {}),
                "reliability": operation.get("reliability", {}),
                "concurrency": operation.get("concurrency", {}),
                "errorCodes": list(operation.get("errorCodes", [])),
                "privacy": operation.get("privacy", {}),
                "telemetry": operation.get("telemetry", {}),
                "slo": operation.get("slo", {}),
                "clientContract": operation.get("clientContract"),
                "requestEntity": str(operation.get("requestEntity", "")),
                "requestBodyKind": str(
                    operation.get("requestBodyKind", "")
                ),
                "responseEntity": str(operation.get("responseEntity", "")),
                "responseBody": str(operation.get("responseBody", "")),
                "responseBodyKind": str(
                    operation.get("responseBodyKind", "")
                ),
                "sourcePath": str(operation.get("sourcePath", "")),
            }
        )
    return result


def compare_operations(
    previous: list[dict[str, Any]],
    current: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    previous_by_id = {
        str(item.get("canonicalOperationId", "")): item for item in previous
    }
    current_by_id = {
        str(item.get("canonicalOperationId", "")): item for item in current
    }
    changes: list[dict[str, Any]] = []
    breaking: list[dict[str, Any]] = []
    for operation_id in sorted(previous_by_id.keys() - current_by_id.keys()):
        change = {"kind": "removed", "canonicalOperationId": operation_id}
        changes.append(change)
        breaking.append(change)
    for operation_id in sorted(current_by_id.keys() - previous_by_id.keys()):
        changes.append({"kind": "added", "canonicalOperationId": operation_id})
    compared_fields = (
        "method",
        "pathTemplate",
        "kind",
        "facet",
        "facadeMethod",
        "aggregateOwner",
        "mutationTarget",
        "invariantTarget",
        "actorRequirement",
        "authMode",
        "principal",
        "scopes",
        "permissions",
        "ownershipPolicy",
        "commercial",
        "reliability",
        "concurrency",
        "errorCodes",
        "privacy",
        "telemetry",
        "slo",
        "clientContract",
        "requestEntity",
        "requestBodyKind",
        "responseEntity",
        "responseBody",
        "responseBodyKind",
    )
    for operation_id in sorted(previous_by_id.keys() & current_by_id.keys()):
        before = previous_by_id[operation_id]
        after = current_by_id[operation_id]
        for field in compared_fields:
            if before.get(field) == after.get(field):
                continue
            change = {
                "kind": "changed",
                "canonicalOperationId": operation_id,
                "field": field,
                "before": before.get(field),
                "after": after.get(field),
            }
            changes.append(change)
            breaking.append(change)
    return changes, breaking


@dataclass
class Lease:
    path: Path
    token: str

    @classmethod
    def acquire(
        cls,
        policy: dict[str, Any],
        *,
        owner: str,
        resource: str,
        ttl_minutes: int,
    ) -> "Lease":
        resources = {
            str(item.get("id", "")): item
            for item in policy.get("resources", [])
            if isinstance(item, dict)
        }
        descriptor = resources.get(resource)
        if descriptor is None:
            raise ValueError(f"ownership policy 未登记 resource: {resource}")
        expected_owner = str(descriptor.get("owner", ""))
        if owner != expected_owner:
            raise ValueError(
                f"resource {resource} owner 必须是 {expected_owner}，收到 {owner}"
            )

        lease_root = ROOT / str(policy.get("leaseRoot", ""))
        lease_root.mkdir(parents=True, exist_ok=True)
        path = lease_root / f"{resource}.lock"
        now = datetime.now(UTC)
        if path.exists():
            active = read_json(path)
            expires_at = datetime.fromisoformat(str(active["expiresAt"]))
            if expires_at > now:
                raise ValueError(
                    f"resource {resource} 已被 {active.get('owner')} 租用至 "
                    f"{active.get('expiresAt')}"
                )
            path.unlink()

        token = secrets.token_hex(16)
        payload = {
            "resource": resource,
            "owner": owner,
            "pid": os.getpid(),
            "token": token,
            "acquiredAt": now.isoformat(),
            "expiresAt": (now + timedelta(minutes=ttl_minutes)).isoformat(),
            "writePaths": descriptor.get("writePaths", []),
        }
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            fd = os.open(path, flags, 0o600)
        except FileExistsError as exc:
            raise ValueError(f"resource {resource} 租约竞争失败") from exc
        with os.fdopen(fd, "wb") as handle:
            handle.write(canonical_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        return cls(path=path, token=token)

    def release(self) -> None:
        if not self.path.exists():
            return
        active = read_json(self.path)
        if active.get("token") != self.token:
            raise ValueError(f"拒绝释放非本进程租约: {relative(self.path)}")
        self.path.unlink()


def build_lock(
    graph_path: Path,
    graph: dict[str, Any],
    report_path: Path,
    report_sha: str,
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    graph_sha = sha256_bytes(graph_path.read_bytes())
    return {
        "generator": GENERATOR,
        "contractGraph": {
            "path": relative(graph_path),
            "sha256": graph_sha,
            "sourceDigestSetSha256": source_digest_set_sha(graph),
            "compilerHash": compiler_digest(),
        },
        "breakingReport": {
            "path": relative(report_path),
            "sha256": report_sha,
        },
        "appExposedOperations": operations,
    }


def accept(args: argparse.Namespace) -> int:
    graph_path = args.graph.resolve()
    lock_path = args.lock.resolve()
    report_path = args.report.resolve()
    graph = read_json(graph_path)
    validate_graph(graph)
    exposures, unresolved = resolve_exposures(graph)
    if unresolved:
        detail = "; ".join(
            f"{item['surfaceId']}:{item['localOperationId']}=>"
            f"{item['candidateCanonicalIds'] or '<missing>'}"
            for item in unresolved
        )
        raise ValueError(f"App exposure 绑定不完整，禁止推断: {detail}")
    operations = operation_snapshots(graph, exposures)

    previous = read_json(lock_path) if lock_path.exists() else {}
    if previous:
        for retired_field in ("version", "schema", "registryRevision"):
            if retired_field in previous:
                raise ValueError(
                    f"现有 App handoff lock 含退休字段 {retired_field}；"
                    "单轨切换必须先删除旧 lock，不允许作为 breaking baseline"
                )
        if previous.get("generator") != GENERATOR:
            raise ValueError("现有 App handoff lock 不是唯一当前 handoff 产物")
    previous_operations = previous.get("appExposedOperations", [])
    if not isinstance(previous_operations, list):
        previous_operations = []
    changes, breaking = compare_operations(previous_operations, operations)
    graph_sha = sha256_bytes(graph_path.read_bytes())
    report = {
        "generator": GENERATOR,
        "previousGraphSha256": (
            previous.get("contractGraph", {}).get("sha256")
            if isinstance(previous.get("contractGraph"), dict)
            else None
        ),
        "graphSha256": graph_sha,
        "baselineEstablished": not bool(previous),
        "changes": changes,
        "breakingChanges": breaking,
        "decision": "approved" if not breaking or args.approve_breaking else "blocked",
    }
    if breaking and not args.approve_breaking:
        raise ValueError(
            f"发现 {len(breaking)} 个 breaking change；"
            "需上游提供已审批报告后显式 --approve-breaking"
        )

    policy = read_json(args.policy.resolve())
    lease = Lease.acquire(
        policy,
        owner=args.owner,
        resource="app-cloud-handoff",
        ttl_minutes=args.lease_ttl_minutes,
    )
    try:
        atomic_write_json(report_path, report)
        report_sha = sha256_bytes(report_path.read_bytes())
        lock = build_lock(
            graph_path,
            graph,
            report_path,
            report_sha,
            operations,
        )
        atomic_write_json(lock_path, lock)
    finally:
        lease.release()
    print(
        "PASS: accepted ContractGraph "
        f"{graph_sha} with {len(operations)} App-exposed operations"
    )
    return 0


def verify(args: argparse.Namespace) -> int:
    graph_path = args.graph.resolve()
    lock_path = args.lock.resolve()
    report_path = args.report.resolve()
    graph = read_json(graph_path)
    validate_graph(graph)
    lock = read_json(lock_path)
    report = read_json(report_path)
    report_sha = sha256_bytes(report_path.read_bytes())
    exposures, unresolved = resolve_exposures(graph)
    if unresolved:
        raise ValueError(f"App exposure 仍有 {len(unresolved)} 个未解析绑定")
    operations = operation_snapshots(graph, exposures)
    expected = build_lock(
        graph_path,
        graph,
        report_path,
        report_sha,
        operations,
    )
    if lock != expected:
        raise ValueError(
            "App ContractGraph lock 与当前 bundle/compiler/exposure 不一致；"
            "必须重新执行 accept"
        )
    if report.get("graphSha256") != expected["contractGraph"]["sha256"]:
        raise ValueError("breaking report graphSha256 与 lock 不一致")
    if report.get("decision") != "approved":
        raise ValueError("breaking report 未获批准")
    print(
        "PASS: ContractGraph handoff lock "
        f"{expected['contractGraph']['sha256']}"
    )
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    subparsers = result.add_subparsers(dest="command", required=True)
    for command in ("accept", "verify"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
        sub.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
        sub.add_argument("--report", type=Path, default=DEFAULT_REPORT)
        sub.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    accept_parser = subparsers.choices["accept"]
    accept_parser.add_argument("--owner", default="app-cloud-governance")
    accept_parser.add_argument("--lease-ttl-minutes", type=int, default=10)
    accept_parser.add_argument("--approve-breaking", action="store_true")
    lease_acquire = subparsers.add_parser("lease-acquire")
    lease_acquire.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    lease_acquire.add_argument("--resource", required=True)
    lease_acquire.add_argument("--owner", required=True)
    lease_acquire.add_argument("--lease-ttl-minutes", type=int, default=30)
    lease_release = subparsers.add_parser("lease-release")
    lease_release.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    lease_release.add_argument("--resource", required=True)
    lease_release.add_argument("--token", required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.command == "accept":
        return accept(args)
    if args.command == "lease-acquire":
        policy = read_json(args.policy.resolve())
        lease = Lease.acquire(
            policy,
            owner=args.owner,
            resource=args.resource,
            ttl_minutes=args.lease_ttl_minutes,
        )
        print(lease.token)
        return 0
    if args.command == "lease-release":
        policy = read_json(args.policy.resolve())
        lease_root = ROOT / str(policy.get("leaseRoot", ""))
        Lease(
            path=lease_root / f"{args.resource}.lock",
            token=args.token,
        ).release()
        print(f"PASS: released {args.resource}")
        return 0
    return verify(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1)
