"""Mutually-exclusive source-path classification."""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any


def _matches_marker(path: str, marker: str) -> bool:
    lowered = path.lower()
    token = str(marker).lower()
    if token.startswith("/") or token.endswith("/"):
        return token.strip("/") in lowered.split("/")
    return lowered.endswith(token) or token in lowered


def classify_path(path: str, policy: dict[str, Any]) -> str:
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
    lowered = normalized.lower()
    rules = policy["classification"]
    if any(_matches_marker(lowered, marker) for marker in rules["vendor_markers"]):
        return "vendor"
    if any(_matches_marker(lowered, marker) for marker in rules["generated_markers"]):
        return "generated"
    if any(_matches_marker(lowered, marker) for marker in rules["test_markers"]):
        return "test"
    if any(lowered.startswith(str(prefix).lower()) for prefix in rules["docs_prefixes"]):
        return "docs"
    if any(_matches_marker(lowered, marker) for marker in rules["contract_markers"]):
        return "contract-metadata"
    suffix = PurePosixPath(lowered).suffix
    if suffix in set(rules["config_extensions"]):
        return "config-data"
    if suffix in set(rules["source_extensions"]):
        return "handwritten-production"
    return "config-data"
