"""Portable refs for governed dependency paths.

A frozen document may travel between the process that wrote it and the process
that consumes it, so every path it names is stored relative to a governed root
and resolved back the same way on both sides. Keeping the two directions in one
module is what makes that round trip decidable instead of a per-caller default.
"""

from __future__ import annotations

from pathlib import Path

from core import paths


def resolve_dependency_path(value: object) -> Path:
    text = str(value or "").strip()
    if not text:
        raise ValueError("dependency ref is empty")
    candidate = Path(text).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    if candidate.parts and candidate.parts[0] == "data":
        return (paths.OUTPUT_ROOT / candidate).resolve()
    if candidate.parts and candidate.parts[0] in {
        "quwoquan_data",
        ".qwq_output",
    }:
        return (paths.REPO_ROOT / candidate).resolve()
    return candidate.resolve()


def canonical_dependency_ref(path: Path) -> str:
    resolved = path.resolve()
    for root in (paths.OUTPUT_ROOT.resolve(), paths.REPO_ROOT.resolve()):
        if resolved == root:
            return "."
        if root in resolved.parents:
            return resolved.relative_to(root).as_posix()
    raise ValueError(f"dependency is outside governed roots: {resolved}")


__all__ = ["canonical_dependency_ref", "resolve_dependency_path"]
