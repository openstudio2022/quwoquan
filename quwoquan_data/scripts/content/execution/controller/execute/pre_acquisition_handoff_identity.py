"""Source-identity guard for acquisition manifests."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from core import paths
from core.source_digest import SourceDigest, content_source_revision

from .pre_acquisition_handoff_document import (
    _identity_drift,
    _typed,
    load_pre_acquisition_handoff,
)


def guard_acquisition_source_identity(
    manifest: Mapping[str, Any],
    *,
    handoff_ref: Path | None,
    repo_root: Path | None = None,
    source_digest_resolver: Callable[..., SourceDigest],
) -> dict[str, Any]:
    """Reject stale manifest/handoff identity before any receipt or CAS write."""
    if handoff_ref is None:
        raise _typed("HANDOFF_REQUIRED", "acquisition requires explicit handoffRef")
    source = source_digest_resolver(
        repo_root=(repo_root or paths.REPO_ROOT).expanduser().resolve()
    )
    manifest_source = str(manifest.get("sourceDigest") or "")
    catalog_digest = str(manifest.get("entityCatalogDigest") or "")
    manifest_revision = str(manifest.get("sourceRevision") or "")
    if manifest_source != source.digest:
        raise _typed(
            "SOURCE_IDENTITY_DRIFT",
            "manifest sourceDigest differs from current_source_digest",
        )
    expected_revision = content_source_revision(
        source_digest=source.digest,
        entity_catalog_digest=catalog_digest,
    )
    if manifest_revision != expected_revision:
        raise _typed(
            "SOURCE_IDENTITY_DRIFT",
            "manifest sourceRevision does not match sourceDigest + "
            "entityCatalogDigest",
        )
    handoff = load_pre_acquisition_handoff(handoff_ref.expanduser().resolve())
    drift = _identity_drift(
        handoff,
        source_revision=manifest_revision,
        source_digest=manifest_source,
        entity_catalog_digest=catalog_digest,
    )
    if drift:
        raise _typed(
            "SOURCE_IDENTITY_DRIFT",
            "manifest differs from handoff identity: " + ", ".join(drift),
        )
    return handoff
