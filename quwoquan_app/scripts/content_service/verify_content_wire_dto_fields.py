#!/usr/bin/env python3
"""Compare typed content decoders with metadata fields.yaml / report fields.

Run from repo root:
  python3 quwoquan_app/scripts/content_service/verify_content_wire_dto_fields.py

新端点或新 JSON 响应：先在 quwoquan_service/services/content-service/contracts/content/post/projections/ 补 client_projection
YAML，再执行 quwoquan_service 下 make codegen-app，最后改 ContentRepository；开放缺口记录在
metadata-driven-client-data-contract Story，本脚本直接校验代码与 metadata。
"""
from __future__ import annotations


import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import REPO_ROOT

import re

import yaml

ROOT = REPO_ROOT

FIELDS_REPORT = (
    ROOT
    / "quwoquan_service"
    / "services"
    / "content-service"
    / "contracts"
    / "trust_safety"
    / "report"
    / "fields.yaml"
)
FIELDS_COMMENT = (
    ROOT
    / "quwoquan_service"
    / "services"
    / "content-service"
    / "contracts"
    / "content"
    / "comment"
    / "fields.yaml"
)
POST_DETAIL_PROJECTION = (
    ROOT
    / "quwoquan_service"
    / "services"
    / "content-service"
    / "contracts"
    / "content"
    / "post"
    / "projections"
    / "content_post_detail_slice.yaml"
)
COMMENT_DART = (
    ROOT
    / "quwoquan_app"
    / "packages"
    / "quwoquan_cloud_contracts"
    / "lib"
    / "src"
    / "content"
    / "content_operation_contracts.g.dart"
)
POST_READER_DART = (
    ROOT
    / "quwoquan_app"
    / "packages"
    / "quwoquan_cloud_contracts"
    / "lib"
    / "src"
    / "content"
    / "content_operation_contracts.g.dart"
)
REPORT_DART = (
    ROOT
    / "quwoquan_app"
    / "packages"
    / "quwoquan_cloud_contracts"
    / "lib"
    / "src"
    / "generated"
    / "requests"
    / "content"
    / "content_operation_contracts.g.requests.g.dart"
)


def _extract_function_block(dart: str, function_name: str) -> str:
    idx = dart.find(function_name)
    if idx < 0:
        raise SystemExit(f"function {function_name} not found")
    brace = dart.find("{", idx)
    depth = 0
    for i in range(brace, len(dart)):
        if dart[i] == "{":
            depth += 1
        elif dart[i] == "}":
            depth -= 1
            if depth == 0:
                return dart[brace : i + 1]
    raise SystemExit(f"unclosed function {function_name}")


def _map_keys_in_block(block: str) -> set[str]:
    keys: set[str] = set()
    for m in re.finditer(r"(?:m|map|root|item)\[['\"]([^'\"]+)['\"]\]", block):
        keys.add(m.group(1))
    # Pure contracts use typed accessors instead of direct dynamic-map reads.
    # Keep the gate coupled to the decoder's declared wire keys without
    # requiring the implementation to regress to `map['field']` access.
    for m in re.finditer(
        r"_(?:string|optionalString|integer|optionalInteger|boolean|optionalBoolean|timestamp|optionalTimestamp|stringList|objectList|status|reactionValue)"
        r"\(\s*map\s*,\s*['\"]([^'\"]+)['\"]",
        block,
    ):
        keys.add(m.group(1))
    return keys


def _projection_field_names(data: dict) -> set[str]:
    fields = data.get("fields") or []
    names: set[str] = set()
    for field in fields:
        if isinstance(field, str) and field.strip():
            names.add(field.strip())
        elif isinstance(field, dict):
            name = str(field.get("name") or "").strip()
            if name:
                names.add(name)
    return names


def _typed_field_names(data: dict, type_name: str) -> set[str]:
    types = data.get("types") or {}
    definition = types.get(type_name) if isinstance(types, dict) else None
    if not isinstance(definition, dict):
        return set()
    return _projection_field_names(definition)


def _report_create_body_keys(report_yaml: dict) -> set[str]:
    names = {str(f["name"]) for f in (report_yaml.get("fields") or []) if f.get("name")}
    # CreateReport API body is subset (no server-only fields required in client wire).
    return names & {"targetId", "targetType", "reason", "description"}


def main() -> int:
    comment = yaml.safe_load(FIELDS_COMMENT.read_text(encoding="utf-8"))
    post_detail_projection = yaml.safe_load(
        POST_DETAIL_PROJECTION.read_text(encoding="utf-8")
    )
    comment_fields = _typed_field_names(comment, "CommentListItem")
    if not comment_fields:
        print(
            "verify_content_wire_dto_fields: CommentListItem metadata must declare fields",
            file=sys.stderr,
        )
        return 1
    comment_block = _extract_function_block(
        COMMENT_DART.read_text(encoding="utf-8"),
        "factory CommentListItem.fromWire(",
    )
    comment_keys = _map_keys_in_block(comment_block)

    unknown = comment_keys - comment_fields
    if unknown:
        print(
            "verify_content_wire_dto_fields: ContentCommentListItem decoder uses unknown keys:\n  "
            + "\n  ".join(sorted(unknown)),
            file=sys.stderr,
        )
        return 1

    missing = []
    for name in sorted(comment_fields):
        if name not in comment_keys:
            missing.append(name)
    if missing:
        print(
            "verify_content_wire_dto_fields: Comment fields missing from strict decoder:\n  "
            + "\n  ".join(missing),
            file=sys.stderr,
        )
        return 1

    post_detail_fields = _projection_field_names(post_detail_projection)
    if not post_detail_fields:
        print(
            "verify_content_wire_dto_fields: ContentPostDetailSlice metadata must declare fields",
            file=sys.stderr,
        )
        return 1
    post_reader = POST_READER_DART.read_text(encoding="utf-8")
    post_detail_keys = _map_keys_in_block(
        _extract_function_block(
            post_reader,
            "factory ContentPostDetailSlice.fromWire(",
        )
    )
    unknown_post_detail = post_detail_keys - post_detail_fields
    if unknown_post_detail:
        print(
            "verify_content_wire_dto_fields: ContentPostDetailSlice decoder uses fields "
            "absent from metadata:\n  "
            + "\n  ".join(sorted(unknown_post_detail)),
            file=sys.stderr,
        )
        return 1

    report = yaml.safe_load(FIELDS_REPORT.read_text(encoding="utf-8"))
    report_body = _report_create_body_keys(report)
    report_dart = REPORT_DART.read_text(encoding="utf-8")
    try:
        report_encoder = _extract_function_block(
            report_dart,
            "encodeContentReportCreateReportGeneratedRequest(",
        )
    except SystemExit:
        print(
            "verify_content_wire_dto_fields: generated CreateReport encoder not found",
            file=sys.stderr,
        )
        return 1
    tomap_keys = set(
        re.findall(r'["\']([a-zA-Z0-9_]+)["\']\s*:', report_encoder)
    )
    if not report_body <= tomap_keys:
        print(
            "verify_content_wire_dto_fields: generated CreateReport encoder missing keys:\n  "
            + "\n  ".join(sorted(report_body - tomap_keys)),
            file=sys.stderr,
        )
        return 1

    print("verify_content_wire_dto_fields: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
