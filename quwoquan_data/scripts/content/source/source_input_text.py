"""Text rendering and rights-mode constants for source plan inputs."""

from __future__ import annotations

import re
from typing import Any

SOURCE_USE_LICENSED_ADAPTATION = "licensed_adaptation"
SOURCE_USE_FACTUAL_REFERENCE = "factual_reference_only"
SOURCE_USE_BLOCKED = "blocked"
VALID_SOURCE_USE_MODES = {
    SOURCE_USE_LICENSED_ADAPTATION,
    SOURCE_USE_FACTUAL_REFERENCE,
    SOURCE_USE_BLOCKED,
}
def source_frontmatter(source: dict[str, Any], entity_id: str) -> str:
    """来源 frontmatter：只记录真实抓取元信息，source.md 正文不再允许 task body 冒充。"""
    use_mode = str(source.get("sourceUseMode") or SOURCE_USE_FACTUAL_REFERENCE)
    allowed_use = (
        "licensed_adaptation"
        if use_mode == SOURCE_USE_LICENSED_ADAPTATION
        else "facts_only"
    )
    return (
        f"---\n"
        f"url: {source.get('url', '')}\n"
        f"platform: {source.get('platform', 'web')}\n"
        f"sourceUseMode: {use_mode}\n"
        f"license: {source.get('license') or 'reference-only'}\n"
        f"allowedUse: {allowed_use}\n"
        f"credit: {source.get('credit', '')}\n"
        f"termsUrl: {source.get('termsUrl', '')}\n"
        f"licenseSnapshot: {source.get('licenseSnapshot', '')}\n"
        f"authorizationProof: {source.get('authorizationProof', '')}\n"
        f"entity: {entity_id}\n"
        f"retained: false\n"
        f"taskProvidedBody: {'true' if str(source.get('body') or '').strip() else 'false'}\n"
        f"---\n\n"
    )


def manual_body_note(source: dict[str, Any], *, max_chars: int = 180) -> str:
    """task/source_plan 里的 body 仅作为人工计划备注，不得充当 source.md 正文。"""
    body = re.sub(r"\s+", " ", str(source.get("body") or "")).strip()
    if not body:
        return ""
    clipped = body[:max_chars]
    if len(body) > max_chars:
        clipped += "..."
    return f"manual_source_plan_note: {clipped}"
