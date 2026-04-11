#!/usr/bin/env python3
"""Compare content wire DTO Dart fromMap keys with metadata fields.yaml / report fields.

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

ROOT = Path(__file__).resolve().parents[1]
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
COMMENT_DART = (
    ROOT
    / "quwoquan_app"
    / "lib"
    / "cloud"
    / "runtime"
    / "generated"
    / "content"
    / "comment_dto.g.dart"
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


def _map_keys_in_block(block: str) -> set[str]:
    keys: set[str] = set()
    for m in re.finditer(r"(?:m|map)\[['\"]([^'\"]+)['\"]\]", block):
        keys.add(m.group(1))
    return keys


def _report_create_body_keys(report_yaml: dict) -> set[str]:
    names = {str(f["name"]) for f in (report_yaml.get("fields") or []) if f.get("name")}
    # CreateReport API body is subset (no server-only fields required in client wire).
    return names & {"targetId", "targetType", "reason", "description"}


def main() -> int:
    post = yaml.safe_load(FIELDS_POST.read_text(encoding="utf-8"))
    comment_fields = set(_entity_field_names(post, "Comment"))
    search_fields = set(_entity_field_names(post, "PostSearchItemView"))

    comment_block = _extract_factory_block(COMMENT_DART.read_text(encoding="utf-8"), "CommentDto.fromMap")
    comment_keys = _map_keys_in_block(comment_block)

    # Wire-only aliases consumed by CommentDto but not Post entity field names.
    extra_comment_ok = {
        "id",
        "subAccountId",
        "authorId",
        "displayName",
        "avatarUrl",
        "isAuthor",
        "replyToDisplayName",
    }
    unknown = comment_keys - comment_fields - extra_comment_ok
    if unknown:
        print(
            "verify_content_wire_dto_fields: CommentDto.fromMap uses unknown keys:\n  "
            + "\n  ".join(sorted(unknown)),
            file=sys.stderr,
        )
        return 1

    missing = []
    for name in sorted(comment_fields):
        if name == "profileSubjectId" and "profileSubjectId" not in comment_keys:
            if "authorId" in comment_keys:
                continue
        if name not in comment_keys and name != "_id":
            missing.append(name)
        if name == "_id" and "_id" not in comment_keys and "id" not in comment_keys:
            missing.append("_id")
    if missing:
        print(
            "verify_content_wire_dto_fields: Comment entity fields missing from fromMap keys:\n  "
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
        "profileSubjectId",
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
    tomap = report_dart.split("Map<String, dynamic> toMap()")[1]
    tomap_keys = set(re.findall(r"'([a-zA-Z0-9_]+)'\s*:", tomap.split("};")[0]))
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
