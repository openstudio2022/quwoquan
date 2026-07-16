"""Deterministic minimum tags for materialized content."""
from __future__ import annotations

from typing import Any, Mapping


def resolved_content_tag_refs(brief: Mapping[str, Any], carrier: str) -> list[str]:
    refs = [str(item) for item in (brief.get("tagRefs") or []) if str(item).strip()]
    defaults = (
        ["Topic/旅行/玩法/摄影旅拍", "Format/内容载体/图文/图集"]
        if carrier == "image"
        else ["Topic/旅行/玩法/观光游览", "Format/内容角度/攻略"]
    )
    if not any(ref.startswith("Topic/旅行") for ref in refs):
        refs.append(defaults[0])
    if not any(ref.startswith("Format/") for ref in refs):
        refs.append(defaults[1])
    return list(dict.fromkeys(refs))
