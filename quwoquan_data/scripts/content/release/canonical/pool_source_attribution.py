"""按唯一 SourceAttribution schema 严格校验入池来源归属。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.source_attribution import canonical_source_attribution


def source_attribution_complete(document: Mapping[str, Any]) -> bool:
    attribution = document.get("sourceAttribution")
    if not isinstance(attribution, Mapping):
        return False
    try:
        canonical_source_attribution(attribution)
    except ValueError:
        return False
    return True


__all__ = ["source_attribution_complete"]
