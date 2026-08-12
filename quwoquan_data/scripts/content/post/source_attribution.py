"""Project immutable source-unit attribution into Article/Image manifests."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.io import read_json
from core.paths import execution_root
from core.source_attribution import canonical_source_attribution


def _safe_source_meta(execution_id: str, source_ref: object) -> dict[str, Any]:
    raw = str(source_ref or "").replace("\\", "/").strip()
    relative = Path(raw)
    if (
        not raw
        or relative.is_absolute()
        or ".." in relative.parts
        or relative.name not in {"source.md", "source.clean.md"}
    ):
        raise ValueError("sourceAttribution sourceRef is not a safe source document")
    root = execution_root(execution_id).resolve()
    current = root
    try:
        for part in relative.parent.parts:
            current = current / part
            if current.is_symlink() or not current.is_dir():
                raise OSError("symlink or non-directory")
    except OSError as exc:
        raise ValueError("sourceAttribution source-unit meta is unavailable") from exc
    unresolved_meta = current / "meta.json"
    meta_path = unresolved_meta.resolve()
    if (
        unresolved_meta.is_symlink()
        or root not in meta_path.parents
        or not meta_path.is_file()
    ):
        raise ValueError("sourceAttribution source-unit meta is unavailable")
    value = read_json(meta_path)
    if not isinstance(value, dict):
        raise ValueError("sourceAttribution source-unit meta must be one object")
    return value


def _source_refs(
    content_type: str,
    compose_payload: Mapping[str, Any],
    assets: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    if content_type == "article":
        return (str(compose_payload.get("baseSourceRef") or ""),)
    refs = {
        str(asset.get("sourceRef") or "").strip()
        for asset in assets
        if str(asset.get("sourceRef") or "").strip()
    }
    if len(refs) != 1:
        raise ValueError("image sourceAttribution requires exactly one source unit")
    return tuple(refs)


def source_unit_attribution(
    execution_id: str,
    content_type: str,
    *,
    compose_payload: Mapping[str, Any],
    assets: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Load attribution only when the frozen source unit explicitly carries it."""

    if content_type not in {"article", "image"}:
        raise ValueError(f"unsupported sourceAttribution content type: {content_type}")
    refs = _source_refs(content_type, compose_payload, assets)
    meta = _safe_source_meta(execution_id, refs[0])
    if "sourceAttribution" not in meta:
        return None
    attribution = canonical_source_attribution(meta["sourceAttribution"])
    source_urls = {
        str(value).strip()
        for value in compose_payload.get("sourceUrls") or []
        if str(value).strip()
    }
    source_post_url = str(attribution["sourcePostUrl"])
    if source_urls and source_post_url not in source_urls:
        raise ValueError("sourceAttribution sourcePostUrl drifts from compose sources")
    return attribution


__all__ = ["source_unit_attribution"]
