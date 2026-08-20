"""Portable source bindings for professional image acquisition rebinds."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.source.professional_image_discovery_binding import load_discovery_candidates

def _portable_archived_ref(
    raw_ref: object,
    *,
    source: Mapping[str, Any],
    source_manifest_path: Path,
    target_root: Path,
    label: str,
) -> str:
    """Resolve one mixed historical ref into the target acquisition root."""
    relative = Path(str(raw_ref or "").strip())
    if not str(relative) or relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"professional image {label} is unsafe")
    source_root = source_manifest_path.expanduser().resolve().parent.parent
    manifest_id = str(source.get("manifestId") or "").strip()
    manifest_part = Path(manifest_id)
    if (
        not manifest_id
        or manifest_part.is_absolute()
        or len(manifest_part.parts) != 1
        or manifest_part.name in {".", ".."}
    ):
        raise ValueError("professional image manifestId is unsafe for archive ref")
    resolved_target = target_root.expanduser().resolve()
    candidates = (
        source_root / relative,
        source_root.parent / relative,
        resolved_target / relative,
        source_root / manifest_part / relative,
    )
    resolved = next(
        (
            candidate.resolve()
            for candidate in candidates
            if candidate.resolve() != resolved_target
            and resolved_target in candidate.resolve().parents
            and not candidate.is_symlink()
            and candidate.is_file()
        ),
        None,
    )
    if resolved is None:
        raise ValueError(f"professional image archived {label} is missing")
    return resolved.relative_to(resolved_target).as_posix()


def _portable_discovery_plan_ref(
    source: Mapping[str, Any],
    *,
    source_manifest_path: Path,
    target_root: Path,
) -> str:
    """Resolve one archived plan into the acquisition root's single ref form."""
    portable = _portable_archived_ref(
        source.get("discoveryPlanRef"),
        source=source,
        source_manifest_path=source_manifest_path,
        target_root=target_root,
        label="discoveryPlanRef",
    )
    load_discovery_candidates(
        {**dict(source), "discoveryPlanRef": portable},
        output_root=target_root,
    )
    return portable


