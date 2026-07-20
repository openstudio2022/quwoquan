#!/usr/bin/env python3
"""Compare typed content decoders with metadata fields.yaml / report fields.

Run from repo root:
  python3 quwoquan_app/scripts/content/verify_content_wire_dto_fields.py

新端点或新 JSON 响应：先在 contracts/metadata/content/post/projections/ 补 client_projection
YAML，再执行 quwoquan_service 下 make codegen-app，最后改 ContentRepository；门禁盘点见
specs/gates/content_domain_dynamic_map_inventory.yaml。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
FIELDS_REPORT = (
    ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
    / "content"
    / "report"
    / "fields.yaml"
)
FIELDS_COMMENT = (
    ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
    / "content"
    / "comment"
    / "fields.yaml"
)
COMMENT_PAGE_PROJECTION = (
    ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
    / "content"
    / "comment"
    / "projections"
    / "comment_page_slice.yaml"
)
POST_DETAIL_PROJECTION = (
    ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
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
    / "comment_contracts.dart"
)
POST_READER_DART = (
    ROOT
    / "quwoquan_app"
    / "packages"
    / "quwoquan_cloud_contracts"
    / "lib"
    / "src"
    / "content"
    / "post_reader_queries.dart"
)
REPORT_DART = (
    ROOT
    / "quwoquan_app"
    / "lib"
    / "cloud"
    / "runtime"
    / "generated"
    / "content"
    / "report_create_request_wire.g.dart"
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


def _report_create_body_keys(report_yaml: dict) -> set[str]:
    names = {str(f["name"]) for f in (report_yaml.get("fields") or []) if f.get("name")}
    # CreateReport API body is subset (no server-only fields required in client wire).
    return names & {"targetId", "targetType", "reason", "description"}


def main() -> int:
    comment = yaml.safe_load(FIELDS_COMMENT.read_text(encoding="utf-8"))
    comment_projection = yaml.safe_load(
        COMMENT_PAGE_PROJECTION.read_text(encoding="utf-8")
    )
    post_detail_projection = yaml.safe_load(
        POST_DETAIL_PROJECTION.read_text(encoding="utf-8")
    )
    comment_fields = {
        str(field["name"])
        for field in (comment.get("fields") or [])
        if isinstance(field, dict) and field.get("name")
    }
    comment_fields.update(
        str(field)
        for field in (comment_projection.get("fields") or [])
        if str(field).strip()
    )
    comment_block = _extract_function_block(
        COMMENT_DART.read_text(encoding="utf-8"),
        "_decodeCommentListItem(",
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
        _extract_function_block(post_reader, "decodeContentPostDetailSlice(")
    )
    post_detail_keys.update(
        _map_keys_in_block(
            _extract_function_block(post_reader, "_decodeContentPostProjection(")
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
    report_match = re.search(
        r"(?:CloudJsonMap|Map<String,\s*dynamic>)\s+toMap\(\)\s*=>\s*<String,\s*dynamic>\{([\s\S]*?)\};",
        report_dart,
    )
    if not report_match:
        print(
            "verify_content_wire_dto_fields: CreateReportRequestWire.toMap signature not found",
            file=sys.stderr,
        )
        return 1
    tomap_keys = set(re.findall(r"'([a-zA-Z0-9_]+)'\s*:", report_match.group(1)))
    if not report_body <= tomap_keys:
        print(
            "verify_content_wire_dto_fields: CreateReportRequestWire.toMap missing keys:\n  "
            + "\n  ".join(sorted(report_body - tomap_keys)),
            file=sys.stderr,
        )
        return 1

    print("verify_content_wire_dto_fields: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
