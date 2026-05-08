from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from common import TREES_ROOT, read_yaml, ref_exists, rel_ref, tree_files

TREE_NAMES = ("entities", "content", "tags")


def _validate_string_field(
    errors: list[str], payload: dict[str, Any], field: str, path_ref: str
) -> None:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path_ref} 缺少 {field}")


def _validate_string_list(
    errors: list[str], payload: dict[str, Any], field: str, path_ref: str
) -> None:
    value = payload.get(field)
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        errors.append(f"{path_ref} 的 {field} 必须是非空字符串数组")


def validate_entity_file(path: Path) -> list[str]:
    path_ref = rel_ref(path)
    payload = read_yaml(path)
    errors: list[str] = []
    parts = path.relative_to(TREES_ROOT / "entities").parts
    if len(parts) != 2:
        errors.append(f"{path_ref} 必须位于 trees/entities/{{大类}}/{{实例}}.yaml")
        return errors
    for field in ("entity_id", "name", "kind", "summary", "city", "address_text"):
        _validate_string_field(errors, payload, field, path_ref)
    for field in (
        "aliases",
        "scene_tag_refs",
        "category_tag_refs",
        "media_refs",
        "evidence_refs",
        "search_terms",
    ):
        value = payload.get(field)
        if not isinstance(value, list):
            errors.append(f"{path_ref} 的 {field} 必须是数组")
    geo = payload.get("geo")
    if geo is not None:
        if not isinstance(geo, dict):
            errors.append(f"{path_ref} 的 geo 必须是对象或 null")
        else:
            if "latitude" not in geo or "longitude" not in geo:
                errors.append(f"{path_ref} 的 geo 需要包含 latitude 和 longitude")
    for ref in payload.get("scene_tag_refs", []) + payload.get("category_tag_refs", []):
        if not ref_exists(ref):
            errors.append(f"{path_ref} 引用了不存在的标签: {ref}")
    return errors


def validate_content_file(path: Path) -> list[str]:
    path_ref = rel_ref(path)
    payload = read_yaml(path)
    errors: list[str] = []
    parts = path.relative_to(TREES_ROOT / "content").parts
    if len(parts) != 2:
        errors.append(f"{path_ref} 必须位于 trees/content/{{分组}}/{{模板}}.yaml")
        return errors
    for field in (
        "template_id",
        "label",
        "summary",
        "content_type",
        "content_identity",
    ):
        _validate_string_field(errors, payload, field, path_ref)
    for field in ("required_post_fields", "optional_post_fields", "semantic_fields"):
        _validate_string_list(errors, payload, field, path_ref)
    if payload.get("content_type") not in {"image", "article", "micro"}:
        errors.append(f"{path_ref} 的 content_type 只允许 image/article/micro")
    return errors


def validate_tag_file(path: Path) -> list[str]:
    path_ref = rel_ref(path)
    payload = read_yaml(path)
    errors: list[str] = []
    parts = path.relative_to(TREES_ROOT / "tags").parts
    if len(parts) != 2:
        errors.append(f"{path_ref} 必须位于 trees/tags/{{维度}}/{{标签}}.yaml")
        return errors
    for field in ("tag_id", "label", "summary"):
        _validate_string_field(errors, payload, field, path_ref)
    parent_ref = payload.get("parent_tag_ref")
    if parent_ref and not ref_exists(parent_ref):
        errors.append(f"{path_ref} 引用了不存在的 parent_tag_ref: {parent_ref}")
    return errors


def validate_tree(tree_name: str) -> tuple[list[str], int]:
    files = tree_files(tree_name)
    errors: list[str] = []
    validator = {
        "entities": validate_entity_file,
        "content": validate_content_file,
        "tags": validate_tag_file,
    }[tree_name]
    for path in files:
        errors.extend(validator(path))
    return errors, len(files)


def handle_validate(args) -> int:
    names = TREE_NAMES if args.tree == "all" else (args.tree,)
    total = 0
    all_errors: list[str] = []
    for name in names:
        errors, count = validate_tree(name)
        total += count
        all_errors.extend(errors)
    if all_errors:
        for error in all_errors:
            print(f"[tree validate] FAIL: {error}", file=sys.stderr)
        return 1
    print(f"[tree validate] OK: trees={','.join(names)} files={total}")
    return 0
