"""Source-identity guard for acquisition manifests."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.source_digest import (
    ExecutionBundleIdentity,
    SourceDefinitionSnapshot,
    content_source_revision,
)

from .pre_acquisition_handoff_document import (
    _identity_drift,
    _typed,
    load_pre_acquisition_handoff,
)


def guard_acquisition_source_identity(
    manifest: Mapping[str, Any],
    *,
    handoff_ref: Path | None,
    frozen_external_input: bool = False,
) -> dict[str, Any]:
    """Reject manifest/handoff drift without consulting a later live worktree."""
    if handoff_ref is None:
        raise _typed("HANDOFF_REQUIRED", "acquisition requires explicit handoffRef")
    manifest_source = str(manifest.get("sourceDigest") or "")
    manifest_bundle = manifest.get("executionBundle")
    catalog_digest = str(manifest.get("entityCatalogDigest") or "")
    manifest_revision = str(manifest.get("sourceRevision") or "")
    handoff = load_pre_acquisition_handoff(handoff_ref.expanduser().resolve())
    source = SourceDefinitionSnapshot.from_document(handoff.get("sourceDigest"))
    bundle = ExecutionBundleIdentity.from_document(handoff.get("executionBundle"))
    if manifest_source != source.digest and not frozen_external_input:
        raise _typed(
            "SOURCE_IDENTITY_DRIFT",
            "manifest sourceDigest differs from frozen handoff snapshot",
        )
    if (
        manifest_bundle is not None
        and manifest_bundle != bundle.to_document()
        and not frozen_external_input
    ):
        raise _typed(
            "SOURCE_IDENTITY_DRIFT",
            "manifest executionBundle differs from frozen handoff bundle",
        )
    if frozen_external_input:
        return handoff
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
