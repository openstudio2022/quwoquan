"""Narrow structural checks for immutable sealed release artifacts."""
from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from content.release.canonical.object_transaction_contract import ObjectTransactionError
from core.schema import assert_valid

_REQUIRED_KINDS = ("creators", "entities", "posts", "tags")


def _safe_ref(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise ObjectTransactionError(f"DATA.RELEASE.SEALED_REF_INVALID: {label}")
    ref = PurePosixPath(value)
    if (
        not value
        or "\x00" in value
        or ref.is_absolute()
        or value != ref.as_posix()
        or any(part in {"", ".", ".."} for part in ref.parts)
    ):
        raise ObjectTransactionError(f"DATA.RELEASE.SEALED_REF_INVALID: {label}={value!r}")
    return value


def _assert_no_symlink(path: Path, *, label: str, regular: bool = True) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    try:
        for part in absolute.parts[1:]:
            current = current / part
            if stat.S_ISLNK(os.lstat(current).st_mode):
                raise ObjectTransactionError(
                    f"DATA.RELEASE.SEALED_ARTIFACT_SYMLINK: {label}={path}"
                )
    except FileNotFoundError as exc:
        raise ObjectTransactionError(
            f"DATA.RELEASE.SEALED_ARTIFACT_MISSING: {label}={path}"
        ) from exc
    if regular and not absolute.is_file():
        raise ObjectTransactionError(f"DATA.RELEASE.SEALED_ARTIFACT_INVALID: {label}")
    if not regular and not absolute.is_dir():
        raise ObjectTransactionError(f"DATA.RELEASE.SEALED_ARTIFACT_INVALID: {label}")
    return absolute


def validate_sealed_release_structure(
    *, release_dir: Path, desired: Mapping[str, Any]
) -> None:
    """Verify desired/index/sample equality and every declared object marker."""

    try:
        assert_valid(
            desired,
            "release",
            "release_desired_state",
            label="sealed release desired state",
        )
    except (TypeError, ValueError) as exc:
        raise ObjectTransactionError("DATA.RELEASE.SEALED_DESIRED_INVALID") from exc
    desired_refs = desired.get("desiredRefs")
    if not isinstance(desired_refs, Mapping) or set(desired_refs) != set(_REQUIRED_KINDS):
        raise ObjectTransactionError("DATA.RELEASE.SEALED_DESIRED_INVALID")
    normalized: dict[str, list[str]] = {}
    for kind in _REQUIRED_KINDS:
        refs = desired_refs.get(kind)
        if (
            not isinstance(refs, list)
            or refs != sorted(refs)
            or len(refs) != len(set(refs))
            or any(not isinstance(ref, str) or not ref for ref in refs)
        ):
            raise ObjectTransactionError(f"DATA.RELEASE.SEALED_DESIRED_INVALID: {kind}")
        normalized[kind] = [
            _safe_ref(ref, label=f"desiredRefs.{kind}") for ref in refs
        ]

    expected = {"schema": "quwoquan_data.release_object_index", **normalized}
    expected_sample = {"schema": "quwoquan_data.release_sample_bundle", **normalized}
    from content.release.canonical.object_transaction_contract import _read_json

    index_path = release_dir / "payload/index/objects.json"
    sample_path = release_dir / "payload/sample_bundle.json"
    index_path = _assert_no_symlink(index_path, label="release object index")
    sample_path = _assert_no_symlink(sample_path, label="release sample bundle")
    if _read_json(index_path) != expected:
        raise ObjectTransactionError("DATA.RELEASE.SEALED_INDEX_DRIFT")
    if _read_json(sample_path) != expected_sample:
        raise ObjectTransactionError("DATA.RELEASE.SEALED_SAMPLE_DRIFT")

    objects_root = release_dir / "payload/objects"
    for kind, refs in normalized.items():
        marker = "_creator.json" if kind == "creators" else ("_definition.json" if kind == "tags" else "manifest.json")
        for ref in refs:
            path = objects_root / kind / ref / marker
            try:
                _assert_no_symlink(path, label=f"{kind}/{ref}/{marker}")
            except ObjectTransactionError as exc:
                raise ObjectTransactionError(
                    f"DATA.RELEASE.SEALED_OBJECT_MARKER_MISSING: {kind}/{ref}/{marker}"
                ) from exc


__all__ = ["validate_sealed_release_structure"]
