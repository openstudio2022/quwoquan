"""Canonical source fingerprint for one first-party service image.

Service images are built from the ``quwoquan_service`` Go/Python build context.
Hashing only the service owner directory is insufficient because compiled
services also consume the shared runtime, generated ContractGraph bindings and
platform packages.  This module keeps that transitive build boundary explicit
and reusable by packaging tests.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable


SHARED_IMAGE_INPUTS = (
    "quwoquan_service/generated",
    "quwoquan_service/internal",
    "quwoquan_service/runtime",
    "quwoquan_service/go.mod",
    "quwoquan_service/go.sum",
)


def service_image_build_inputs(
    repo_root: Path,
    owner_relative: str,
) -> tuple[Path, ...]:
    """Return the single declared source set used to identify an image build."""

    root = repo_root.resolve()
    owner = (root / owner_relative).resolve()
    inputs = (owner, *(root / item for item in SHARED_IMAGE_INPUTS))
    for item in inputs:
        try:
            item.relative_to(root)
        except ValueError as exc:
            raise ValueError("service image build input escapes repository root") from exc
        if not item.exists():
            raise FileNotFoundError(f"service image build input is missing: {item}")
    return inputs


def service_image_build_input_digest(
    repo_root: Path,
    owner_relative: str,
) -> tuple[str, int, tuple[str, ...]]:
    """Hash owner plus shared compiler inputs using repository-relative paths."""

    root = repo_root.resolve()
    inputs = service_image_build_inputs(root, owner_relative)
    files = sorted(
        _unique_files(inputs),
        key=lambda item: item.relative_to(root).as_posix(),
    )
    accumulator = hashlib.sha256()
    for item in files:
        relative = item.relative_to(root).as_posix().encode("utf-8")
        content = item.read_bytes()
        accumulator.update(len(relative).to_bytes(8, "big"))
        accumulator.update(relative)
        accumulator.update(len(content).to_bytes(8, "big"))
        accumulator.update(content)
    declared = tuple(item.relative_to(root).as_posix() for item in inputs)
    return "sha256:" + accumulator.hexdigest(), len(files), declared


def _unique_files(inputs: Iterable[Path]) -> set[Path]:
    files: set[Path] = set()
    for item in inputs:
        if item.is_file():
            files.add(item)
            continue
        files.update(path for path in item.rglob("*") if path.is_file())
    return files
