"""Pure member-root binding validation for homepage/article source-ready rows."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any


def source_ready_member_binding(
    binding: Mapping[str, Any], *, candidate_id: str
) -> tuple[str, str]:
    root_text = str(binding.get("evidenceRootRef") or "").strip()
    root_ref = Path(root_text)
    if not root_text or root_ref.is_absolute() or ".." in root_ref.parts:
        raise ValueError(f"{candidate_id} source-ready evidence root ref is unsafe")
    capsule_text = str(binding.get("ref") or "").strip()
    capsule_ref = Path(capsule_text)
    if not capsule_text or capsule_ref.is_absolute() or ".." in capsule_ref.parts:
        raise ValueError(f"{candidate_id} source-ready capsule ref is unsafe")
    if root_text == ".":
        return ".", capsule_ref.as_posix()
    try:
        member_ref = capsule_ref.relative_to(root_ref)
    except ValueError as exc:
        raise ValueError(
            f"{candidate_id} source-ready capsule escapes its member root"
        ) from exc
    if not member_ref.parts:
        raise ValueError(f"{candidate_id} source-ready capsule ref is empty")
    return root_ref.as_posix(), member_ref.as_posix()


__all__ = ["source_ready_member_binding"]
