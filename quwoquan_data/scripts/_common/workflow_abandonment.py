from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

ABANDON_SCOPE_ENTITY = "entity"
ABANDON_SCOPE_HOMEPAGE = "homepage"


def abandonment_scope(row: Mapping[str, Any]) -> str:
    scope = str(row.get("abandonScope") or row.get("scope") or "").strip().lower()
    if scope == ABANDON_SCOPE_HOMEPAGE:
        return ABANDON_SCOPE_HOMEPAGE
    return ABANDON_SCOPE_ENTITY


def abandonment_status(row: Mapping[str, Any]) -> str:
    status = str(row.get("status") or "abandoned").strip().lower()
    return status or "abandoned"


def is_terminal_abandonment(row: Mapping[str, Any]) -> bool:
    return abandonment_status(row) == "abandoned"


def abandoned_entity_name(row: Mapping[str, Any]) -> str:
    return str(row.get("entityId") or row.get("entity") or "").strip()


def abandoned_entity_ids(
    rows: Iterable[Any],
    *,
    scope: str = ABANDON_SCOPE_ENTITY,
) -> set[str]:
    out: set[str] = set()
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        if not is_terminal_abandonment(raw):
            continue
        row_scope = abandonment_scope(raw)
        if scope != "any" and row_scope != scope:
            continue
        name = abandoned_entity_name(raw)
        if name:
            out.add(name)
    return out
