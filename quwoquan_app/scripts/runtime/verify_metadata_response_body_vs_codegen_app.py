#!/usr/bin/env python3
"""
R-ID02 框架级 response_body 一致性门禁。

校验链路（单一真相源 = services/*/contracts/**/operations.yaml 的
api_routes[].response_body）：
  1. operation 的 response_body_kind ∈ {object, page, ack}；
  2. kind ∈ {object, page} 时 response_body 必填，且必须指向某 projection 的 read_model
     （或 client_projection.dart_class）；若该 projection 绑定 App Dart 类型，类型文件必须存在且定义对应 class；
  3. kind == ack 时禁止声明 response_body；
  4. 生成产物 *_api_metadata.g.dart 的 operationToResponseModel / operationToResponseKind
     必须与 metadata 完全一致（无缺失、无多余、无错配）——防止「声明了没人消费」的死字段。

任何漂移 FAIL，确保 response_body 是被 codegen 真实消费且端云对齐的活字段。
"""
# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/metadata-driven-client-data-contract/spec.md#gwt-001
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: PyYAML required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)


ROOT = Path(__file__).resolve().parents[3]
SERVICE_DIR = ROOT / "quwoquan_service"
GEN_DIR = ROOT / "quwoquan_app" / "lib" / "cloud" / "runtime" / "generated"
APP_LIB_DIR = ROOT / "quwoquan_app" / "lib"

VALID_KINDS = {"object", "page", "ack"}


def domain_contract_roots() -> dict[str, list[Path]]:
    roots: dict[str, list[Path]] = {}
    for path in sorted(SERVICE_DIR.glob("**/contracts/domain.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        domain = str(data.get("domain") or "").strip()
        if not domain:
            continue
        roots.setdefault(domain, []).append(path.parent)
    return roots


def collect_projection_index() -> dict[str, tuple[str, str, str]]:
    """全契约 read_model/dart_class -> App Dart binding，支持显式跨域读模型。"""
    index: dict[str, tuple[str, str, str]] = {}
    for contract_roots in domain_contract_roots().values():
        projection_paths = sorted(
            path
            for contract_root in contract_roots
            for path in contract_root.rglob("projections/*.yaml")
        )
        for path in projection_paths:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            client_projection = data.get("client_projection")
            read_model = str(data.get("read_model") or "").strip()
            if not read_model:
                continue
            dart_class = ""
            output_path = ""
            external_path = ""
            if isinstance(client_projection, dict):
                dart_class = str(client_projection.get("dart_class") or "").strip()
                output_path = str(client_projection.get("output_path") or "").strip()
                external_path = str(
                    client_projection.get("external_dart_path") or ""
                ).strip()
            binding = (dart_class, output_path, external_path)
            previous = index.get(read_model)
            if previous is not None and previous != binding:
                raise SystemExit(
                    f"FAIL: conflicting projection binding for {read_model!r}: "
                    f"{previous!r} vs {binding!r} ({path.relative_to(ROOT)})"
                )
            index[read_model] = binding
            if dart_class:
                previous = index.get(dart_class)
                if previous is not None and previous != binding:
                    raise SystemExit(
                        f"FAIL: conflicting Dart projection binding for {dart_class!r}: "
                        f"{previous!r} vs {binding!r} ({path.relative_to(ROOT)})"
                    )
                index[dart_class] = binding
    return index


def collect_response_decls() -> dict[str, dict[str, dict[str, str]]]:
    """domain -> {operation -> {body, kind}}（仅含声明了任一字段的 operation）。"""
    by_domain: dict[str, dict[str, dict[str, str]]] = {}
    for domain, contract_roots in domain_contract_roots().items():
        bucket = by_domain.setdefault(domain, {})
        operation_paths = sorted(
            path
            for contract_root in contract_roots
            for path in contract_root.rglob("operations.yaml")
        )
        for path in operation_paths:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            routes = data.get("api_routes")
            if not isinstance(routes, list):
                continue
            for route in routes:
                if not isinstance(route, dict):
                    continue
                op = str(route.get("operation") or "").strip()
                body = str(route.get("response_body") or "").strip()
                kind = str(route.get("response_body_kind") or "").strip()
                if not op or (not body and not kind):
                    continue
                bucket[op] = {
                    "body": body,
                    "kind": kind,
                    "source": str(path.relative_to(ROOT)),
                }
    return by_domain


def parse_dart_map(text: str, name: str) -> dict[str, str]:
    m = re.search(
        rf"static const Map<String, String> {name} = <String, String>\{{([\s\S]*?)\}};",
        text,
    )
    if not m:
        return {}
    return {mo.group(1): mo.group(2) for mo in re.finditer(r"'([^']+)':\s*'([^']+)'", m.group(1))}


def main() -> int:
    if not SERVICE_DIR.is_dir() or not GEN_DIR.is_dir():
        print("FAIL: missing service contracts or generated dir", file=sys.stderr)
        return 1

    projection_index = collect_projection_index()
    decls_by_domain = collect_response_decls()
    errors: list[str] = []
    checked_ops = 0

    for domain, ops in sorted(decls_by_domain.items()):
        dart_path = GEN_DIR / domain / f"{domain}_api_metadata.g.dart"
        if not dart_path.is_file():
            errors.append(f"{domain}: declared response_body but missing {dart_path.relative_to(ROOT)}")
            continue
        text = dart_path.read_text(encoding="utf-8")
        dart_model = parse_dart_map(text, "operationToResponseModel")
        dart_kind = parse_dart_map(text, "operationToResponseKind")

        for op, decl in sorted(ops.items()):
            checked_ops += 1
            body, kind = decl["body"], decl["kind"]
            src = decl["source"]

            if kind not in VALID_KINDS:
                errors.append(f"{domain}.{op}: invalid response_body_kind {kind!r} ({src})")
                continue

            # kind ↔ dart operationToResponseKind 必须一致
            if dart_kind.get(op) != kind:
                errors.append(
                    f"{domain}.{op}: response_body_kind metadata={kind!r} "
                    f"dart operationToResponseKind={dart_kind.get(op)!r}"
                )

            if kind == "ack":
                if body:
                    errors.append(f"{domain}.{op}: kind=ack must not declare response_body (got {body!r})")
                if op in dart_model:
                    errors.append(f"{domain}.{op}: kind=ack must not appear in operationToResponseModel")
                continue

            # object | page：必须指向存在 projection；仅显式绑定 App 类型的投影进入 Dart 映射。
            if not body:
                errors.append(f"{domain}.{op}: kind={kind} requires response_body read model reference ({src})")
                continue
            resolved = projection_index.get(body)
            if resolved is None:
                errors.append(f"{domain}.{op}: response_body {body!r} is not a known projection read_model/dart_class")
                continue
            dart_class, output_path, external_path = resolved
            if not dart_class:
                if op in dart_model:
                    errors.append(
                        f"{domain}.{op}: operationToResponseModel must not expose unbound projection {body!r}"
                    )
                continue
            if dart_model.get(op) != dart_class:
                errors.append(
                    f"{domain}.{op}: operationToResponseModel metadata->{dart_class!r} "
                    f"dart={dart_model.get(op)!r}"
                )
            if output_path or external_path:
                if external_path:
                    external = Path(external_path)
                    dto_file = (
                        ROOT / external
                        if external.parts and external.parts[0] == "quwoquan_app"
                        else APP_LIB_DIR / external
                    )
                else:
                    dto_file = APP_LIB_DIR / output_path
                if not dto_file.is_file():
                    source = external_path or output_path
                    errors.append(f"{domain}.{op}: Dart contract file missing: {source}")
                elif not re.search(rf"\bclass {re.escape(dart_class)}\b", dto_file.read_text(encoding="utf-8")):
                    source = external_path or output_path
                    errors.append(f"{domain}.{op}: Dart contract {source} does not define class {dart_class}")

        # 反向：dart 映射只允许来自显式 App 类型绑定的 metadata operation（无孤儿/手改残留）。
        for op in sorted(set(dart_model) | set(dart_kind)):
            if op not in ops:
                errors.append(
                    f"{domain}.{op}: present in {dart_path.name} response maps but not declared "
                    f"in metadata service.yaml (stale codegen or hand-edit?)"
                )
                continue
            if op not in dart_model:
                continue
            body = ops[op]["body"]
            resolved = projection_index.get(body)
            if resolved is None or not resolved[0]:
                errors.append(
                    f"{domain}.{op}: response map exposes {body!r} without an explicit App Dart type binding"
                )

    if checked_ops == 0:
        errors.append(
            "zero response_body operations were checked; canonical service contracts must never produce an empty green gate"
        )

    if errors:
        print("verify_metadata_response_body_vs_codegen_app: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(
        f"verify_metadata_response_body_vs_codegen_app: OK "
        f"({checked_ops} response_body operations cross-checked metadata↔codegen↔projection)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
