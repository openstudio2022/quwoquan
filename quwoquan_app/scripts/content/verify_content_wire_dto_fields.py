#!/usr/bin/env python3
"""Compare typed content decoders with metadata fields.yaml / report fields.

Run from repo root: python3 scripts/verify_content_wire_dto_fields.py

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
FIELDS_POST = (
    ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
    / "content"
    / "post"
    / "fields.yaml"
)
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
SEARCH_DART = (
    ROOT
    / "quwoquan_app"
    / "lib"
    / "cloud"
    / "runtime"
    / "generated"
    / "content"
    / "post_search_item_view_dto.g.dart"
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


def _entity_field_names(data: dict, entity: str) -> list[str]:
    ent = data.get("entities", {}).get(entity)
    if not ent:
        raise SystemExit(f"entity {entity!r} not found in fields yaml")
    fields = ent.get("fields") or []
    out = []
    for row in fields:
        if isinstance(row, dict) and row.get("name"):
            out.append(str(row["name"]))
    return out


def _extract_factory_block(dart: str, factory_name: str) -> str:
    idx = dart.find(f"factory {factory_name}")
    if idx < 0:
        raise SystemExit(f"factory {factory_name} not found")
    brace = dart.find("{", idx)
    depth = 0
    i = brace
    while i < len(dart):
        c = dart[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return dart[brace : i + 1]
        i += 1
    raise SystemExit(f"unclosed factory {factory_name}")


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
    for m in re.finditer(r"(?:m|map)\[['\"]([^'\"]+)['\"]\]", block):
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


def _report_create_body_keys(report_yaml: dict) -> set[str]:
    names = {str(f["name"]) for f in (report_yaml.get("fields") or []) if f.get("name")}
    # CreateReport API body is subset (no server-only fields required in client wire).
    return names & {"targetId", "targetType", "reason", "description"}


def main() -> int:
    post = yaml.safe_load(FIELDS_POST.read_text(encoding="utf-8"))
    comment = yaml.safe_load(FIELDS_COMMENT.read_text(encoding="utf-8"))
    comment_projection = yaml.safe_load(
        COMMENT_PAGE_PROJECTION.read_text(encoding="utf-8")
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
    search_fields = set(_entity_field_names(post, "PostSearchItemView"))

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

    search_block = _extract_factory_block(
        SEARCH_DART.read_text(encoding="utf-8"),
        "PostSearchItemView.fromMap",
    )
    search_keys = _map_keys_in_block(search_block)
    extra_search_ok = {
        "id",
        "_id",
        "type",
        "body",
        "thumbnailUrl",
        "subAccountId",
        "authorDisplayNameSnapshot",
        "authorAvatarUrlSnapshot",
        "displayName",
        "avatarUrl",
    }
    unknown_s = search_keys - search_fields - extra_search_ok
    if unknown_s:
        print(
            "verify_content_wire_dto_fields: PostSearchItemView.fromMap unknown keys:\n  "
            + "\n  ".join(sorted(unknown_s)),
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
