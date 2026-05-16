#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY_PATH = WORKSPACE_ROOT / "deploy" / "shared" / "media_slice_registry.json"


def load_registry(path: str | Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    registry_path = Path(path)
    return json.loads(registry_path.read_text(encoding="utf-8"))


def normalize_object_key(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if "://" in raw:
        split = urlsplit(raw)
        raw = split.path
    return raw.lstrip("/").split("?", 1)[0]


def extract_slice_id(object_key: str) -> str:
    parts = normalize_object_key(object_key).split("/")
    for index, part in enumerate(parts[:-1]):
        if part == "s" and index + 1 < len(parts):
            return parts[index + 1].strip()
    return ""


def registry_slices_by_id(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("sliceId")): item
        for item in registry.get("slices", [])
        if str(item.get("sliceId", "")).strip()
    }


def resolve_slice_entry(registry: dict[str, Any], object_key: str) -> dict[str, Any] | None:
    normalized = normalize_object_key(object_key)
    if not normalized:
        return None
    by_id = registry_slices_by_id(registry)
    explicit = extract_slice_id(normalized)
    if explicit:
        return by_id.get(explicit)
    for item in registry.get("slices", []):
        for prefix in item.get("legacyPrefixes", []):
            if normalized.startswith(str(prefix)):
                return item
    return None


def resolve_local_file(
    registry: dict[str, Any],
    object_key: str,
    workspace_root: str | Path = WORKSPACE_ROOT,
) -> Path | None:
    entry = resolve_slice_entry(registry, object_key)
    if not entry or str(entry.get("originType", "")) != "local_root":
        return None
    local_root = str(entry.get("localRoot", "")).strip()
    if not local_root:
        return None
    root = Path(workspace_root)
    base = (root / local_root).resolve()
    target = (base / normalize_object_key(object_key)).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return None
    return target


def allocate_object_key(
    registry: dict[str, Any],
    media_family: str,
    domain: str,
    asset_kind: str,
    owner_type: str,
    owner_id: str,
    asset_id: str,
    variant: str,
    ext: str,
) -> dict[str, str]:
    writable = ((registry.get("allocation") or {}).get("writableSlices") or {})
    slice_id = str(writable.get(media_family, "")).strip()
    if not slice_id:
        raise ValueError(f"no writable slice configured for media family: {media_family}")
    entry = registry_slices_by_id(registry).get(slice_id)
    if entry is None:
        raise ValueError(f"writable slice not found in registry: {slice_id}")
    template = str(entry.get("objectKeyTemplate") or "{domain}/{assetKind}/s/{sliceId}/{ownerType}/{ownerId}/{assetId}_{variant}.{ext}")
    object_key = (
        template.replace("{domain}", sanitize_part(domain, "media"))
        .replace("{assetKind}", sanitize_part(asset_kind, "asset"))
        .replace("{sliceId}", sanitize_part(slice_id, "slice-unknown"))
        .replace("{ownerType}", sanitize_part(owner_type, "owner"))
        .replace("{ownerId}", sanitize_part(owner_id, "unknown"))
        .replace("{assetId}", sanitize_part(asset_id, "asset"))
        .replace("{variant}", sanitize_part(variant, "origin"))
        .replace("{ext}", sanitize_ext(ext))
    )
    return {
        "sliceId": slice_id,
        "objectKey": object_key,
    }


def build_runtime_media_plan_entry(
    registry: dict[str, Any],
    media_family: str,
    domain: str,
    asset_kind: str,
    owner_type: str,
    owner_id: str,
    asset_id: str,
    variant: str,
    ext: str,
    source_refs: list[str],
    source_url: str = "",
) -> dict[str, Any]:
    allocation = allocate_object_key(
        registry=registry,
        media_family=media_family,
        domain=domain,
        asset_kind=asset_kind,
        owner_type=owner_type,
        owner_id=owner_id,
        asset_id=asset_id,
        variant=variant,
        ext=ext,
    )
    return {
        "assetId": asset_id,
        "mediaFamily": media_family,
        "sliceId": allocation["sliceId"],
        "objectKey": allocation["objectKey"],
        "ownerType": owner_type,
        "ownerId": owner_id,
        "variant": variant,
        "sourceRefs": source_refs,
        "sourceUrl": source_url,
        "ingestMode": "runtime_media_ingest_required",
    }


def sanitize_part(value: str, fallback: str) -> str:
    cleaned = (value or "").strip().strip("/")
    if not cleaned:
        return fallback
    return cleaned.replace(" ", "-").replace(":", "-")


def sanitize_ext(value: str) -> str:
    cleaned = (value or "").strip().strip(".")
    if not cleaned:
        return "bin"
    return cleaned.lower()

