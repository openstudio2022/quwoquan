"""Canonical manifest evidence for mixed-terminal reconciliation."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from core.io import read_json

from content.execution.campaign.submission_reconciliation_contract import (
    file_digest,
    typed,
)


def _safe_ref(value: object, *, label: str) -> str:
    text = str(value or "").strip().strip("/")
    ref = PurePosixPath(text)
    if not text or ref.is_absolute() or ".." in ref.parts:
        raise typed("EXECUTION_EVIDENCE_INVALID", f"{label} is unsafe")
    return ref.as_posix()


def canonical_manifests(
    publish: Mapping[str, Any],
    *,
    carrier: str,
    execution_id: str,
    source_digest: Mapping[str, Any],
    publish_root: Path,
) -> list[dict[str, Any]]:
    refs = publish.get("publishedRefs")
    if not isinstance(refs, Mapping):
        raise typed("EXECUTION_EVIDENCE_INVALID", f"{carrier} publish refs are invalid")
    expected_kind = "entities" if carrier == "homepage" else "posts"
    forbidden_kind = "posts" if expected_kind == "entities" else "entities"
    selected = list(refs.get(expected_kind) or [])
    if len(selected) != 1 or list(refs.get(forbidden_kind) or []):
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            f"{carrier} publish refs are not one exact carrier object",
        )
    rows: list[dict[str, Any]] = []
    for raw in selected:
        object_ref = _safe_ref(raw, label=f"{carrier} canonical object ref")
        manifest_path = publish_root / expected_kind / object_ref / "manifest.json"
        manifest = read_json(manifest_path)
        if (
            not isinstance(manifest, Mapping)
            or manifest.get("executionId") != execution_id
            or manifest.get("sourceDigest") != source_digest
            or (expected_kind == "posts" and manifest.get("contentType") != carrier)
        ):
            raise typed(
                "EXECUTION_EVIDENCE_INVALID",
                f"{carrier} canonical manifest is missing or identity-drifted",
            )
        rows.append(
            {
                "objectKind": expected_kind,
                "objectRef": object_ref,
                "canonicalManifestRef": manifest_path.relative_to(
                    publish_root
                ).as_posix(),
                "canonicalManifestSha256": file_digest(manifest_path),
            }
        )
    return rows


__all__ = ["canonical_manifests"]
