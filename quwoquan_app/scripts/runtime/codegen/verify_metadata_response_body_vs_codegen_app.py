#!/usr/bin/env python3
"""
R-ID02 框架级 response_body 一致性门禁。

校验链路（单一真相源 = services/*/contracts/**/operations.yaml 的
api_routes[].response_body）：
  1. operation 的 response_body_kind ∈ {object, page, ack}；
  2. kind ∈ {object, page} 时 response_body 必填，且必须指向某 projection 的 read_model
     （或 client_projection.dart_class）；若该 projection 绑定 App Dart 类型，类型文件必须存在且定义对应 class；
  3. kind == ack 时禁止声明 response_body；
  4. 若 App CloudOperationContract 已填充 responseBody / responseBodyKind，则必须与
     metadata 一致。Legacy *_api_metadata.g.dart response maps 已退役。

任何漂移 FAIL，确保 response_body 是被 projection 与 App 契约真实消费的活字段。
"""
# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/metadata-driven-client-data-contract/spec.md#gwt-001
from __future__ import annotations

import re
import sys
from pathlib import Path

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import REPO_ROOT

try:
    import yaml
except ImportError:
    print("FAIL: PyYAML required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)


ROOT = REPO_ROOT
SERVICE_DIR = ROOT / "quwoquan_service"
APP_LIB_DIR = ROOT / "quwoquan_app" / "lib"
OPERATION_CONTRACTS = (
    ROOT
    / "quwoquan_app"
    / "packages"
    / "quwoquan_cloud_contracts"
    / "lib"
    / "src"
    / "generated"
    / "operation_contracts.g.dart"
)

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


def parse_app_response_contracts(
    dart_path: Path,
) -> dict[str, dict[str, dict[str, str]]]:
    """domain -> {localOperationId -> {body, kind}} for non-empty App fields."""

    text = dart_path.read_text(encoding="utf-8")
    by_domain: dict[str, dict[str, dict[str, str]]] = {}
    for match in re.finditer(
        r'"[^"]+": CloudOperationContract\(\n(?P<body>.*?)(?=\n  "[^"]+": CloudOperationContract\(|\n\};)',
        text,
        re.S,
    ):
        body = match.group("body")
        domain_match = re.search(r'domain: "([^"]+)"', body)
        local_match = re.search(r'localOperationId: "([^"]+)"', body)
        response_body = re.search(r'responseBody: "([^"]*)"', body)
        response_kind = re.search(r'responseBodyKind: "([^"]*)"', body)
        if not domain_match or not local_match:
            continue
        kind = response_kind.group(1) if response_kind else ""
        model = response_body.group(1) if response_body else ""
        if not kind and not model:
            continue
        by_domain.setdefault(domain_match.group(1), {})[local_match.group(1)] = {
            "body": model,
            "kind": kind,
        }
    return by_domain


def main() -> int:
    if not SERVICE_DIR.is_dir() or not OPERATION_CONTRACTS.is_file():
        print(
            "FAIL: missing service contracts or App operation_contracts.g.dart",
            file=sys.stderr,
        )
        return 1

    projection_index = collect_projection_index()
    decls_by_domain = collect_response_decls()
    app_by_domain = parse_app_response_contracts(OPERATION_CONTRACTS)
    errors: list[str] = []
    checked_ops = 0

    for domain, ops in sorted(decls_by_domain.items()):
        app_ops = app_by_domain.get(domain, {})
        for op, decl in sorted(ops.items()):
            checked_ops += 1
            body, kind = decl["body"], decl["kind"]
            src = decl["source"]

            if kind not in VALID_KINDS:
                errors.append(
                    f"{domain}.{op}: invalid response_body_kind {kind!r} ({src})"
                )
                continue

            if kind == "ack":
                if body:
                    errors.append(
                        f"{domain}.{op}: kind=ack must not declare response_body "
                        f"(got {body!r})"
                    )
                continue

            if not body:
                errors.append(
                    f"{domain}.{op}: kind={kind} requires response_body read model "
                    f"reference ({src})"
                )
                continue
            resolved = projection_index.get(body)
            if resolved is None:
                errors.append(
                    f"{domain}.{op}: response_body {body!r} is not a known "
                    "projection read_model/dart_class"
                )
                continue
            dart_class, output_path, external_path = resolved
            if not dart_class:
                continue
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
                    errors.append(
                        f"{domain}.{op}: Dart contract file missing: {source}"
                    )
                elif not re.search(
                    rf"\bclass {re.escape(dart_class)}\b",
                    dto_file.read_text(encoding="utf-8"),
                ):
                    source = external_path or output_path
                    errors.append(
                        f"{domain}.{op}: Dart contract {source} does not define "
                        f"class {dart_class}"
                    )

            app_decl = app_ops.get(op)
            if app_decl is None:
                continue
            if app_decl["kind"] and app_decl["kind"] != kind:
                errors.append(
                    f"{domain}.{op}: response_body_kind metadata={kind!r} "
                    f"app={app_decl['kind']!r}"
                )
            if app_decl["body"] and app_decl["body"] not in {body, dart_class}:
                errors.append(
                    f"{domain}.{op}: response_body metadata={body!r}/"
                    f"{dart_class!r} app={app_decl['body']!r}"
                )

    if checked_ops == 0:
        errors.append(
            "zero response_body operations were checked; canonical service "
            "contracts must never produce an empty green gate"
        )

    if errors:
        print("verify_metadata_response_body_vs_codegen_app: FAIL", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print(
        "verify_metadata_response_body_vs_codegen_app: OK "
        f"({checked_ops} response_body operations cross-checked "
        "metadata↔App contracts↔projection)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
