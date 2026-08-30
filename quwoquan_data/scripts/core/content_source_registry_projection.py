"""Canonical content source registry 的只读行投影。"""
from __future__ import annotations

from typing import Any, Mapping


def registry_sources(
    data: Mapping[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    common = data.get("common") if isinstance(data.get("common"), dict) else {}
    for bucket, items in common.items():
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict):
                rows.append((f"common.{bucket}", item))
    verticals = (
        data.get("verticals") if isinstance(data.get("verticals"), dict) else {}
    )
    for vertical, lanes in verticals.items():
        if not isinstance(lanes, dict):
            continue
        for lane, items in lanes.items():
            for item in items if isinstance(items, list) else []:
                if isinstance(item, dict):
                    rows.append((f"verticals.{vertical}.{lane}", item))
    return rows


__all__ = ["registry_sources"]
