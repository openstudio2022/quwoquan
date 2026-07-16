"""Small reference normalization helpers shared by homepage build stages."""
from __future__ import annotations


def dedupe_nonempty(values: list[str]) -> list[str]:
    return [value for value in dict.fromkeys(value for value in values if value)]


def source_unit_from_ref(ref: str) -> str:
    raw = str(ref or "").replace("\\", "/").strip()
    return raw.rsplit("/", 1)[0] if raw.endswith("/source.md") else raw


def same_source_unit(left_ref: str, right_ref: str) -> bool:
    left = source_unit_from_ref(left_ref)
    right = source_unit_from_ref(right_ref)
    return bool(left and right and left == right)


def safe_ref(domain: str, entity_type: str, name: str) -> str:
    return f"{domain}__{entity_type}__{name}".replace("/", "_")
