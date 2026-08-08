"""Read stable entity facts from versioned reference catalogs.

Providers may discover candidates, but aliases and administrative membership are
facts about entities. Keeping them here prevents provider policies from
accumulating task-specific URL and keyword exceptions.
"""
from __future__ import annotations

from functools import lru_cache

import yaml
from core.paths import REPO_DATA_ROOT

ENTITY_REFERENCE_ROOT = REPO_DATA_ROOT / "reference" / "travel" / "entities"


@lru_cache(maxsize=1)
def _aliases_by_name() -> dict[str, tuple[str, ...]]:
    aliases: dict[str, tuple[str, ...]] = {}
    for path in sorted(ENTITY_REFERENCE_ROOT.rglob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise TypeError(f"entity reference must be an object: {path}")
        for district in document.get("districts") or ():
            if not isinstance(district, dict):
                continue
            for leaf in district.get("leaves") or ():
                if not isinstance(leaf, dict):
                    continue
                name = str(leaf.get("name") or "").strip()
                canonical_name = str(leaf.get("canonicalName") or "").strip()
                values = leaf.get("aliases") or ()
                if not name or not canonical_name or not isinstance(values, list):
                    continue
                normalized = tuple(
                    value
                    for value in dict.fromkeys(
                        [name, canonical_name, *(str(item).strip() for item in values)]
                    )
                    if value
                )
                for lookup_name in (name, canonical_name):
                    aliases[lookup_name] = tuple(
                        value for value in normalized if value != lookup_name
                    )
    return aliases


def entity_aliases(name: str) -> tuple[str, ...]:
    """Return only aliases recorded as stable entity facts."""
    return _aliases_by_name().get(str(name or "").strip(), ())


__all__ = ["ENTITY_REFERENCE_ROOT", "entity_aliases"]
