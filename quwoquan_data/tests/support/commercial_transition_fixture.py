"""Reusable four-environment commercial-transition evidence fixture."""
from __future__ import annotations

from pathlib import Path

from content.release.canonical.commercial_transition_evidence import (
    write_commercial_transition_cleanup_receipt,
    write_commercial_transition_evidence,
    write_commercial_transition_readback_receipt,
)
from core.release_layout import payload_digest


def write_cleanup_evidence(
    output_root: Path,
    *,
    research_release: Path,
    commercial_release: Path,
) -> Path:
    research_digest = payload_digest(research_release)
    commercial_digest = payload_digest(commercial_release)
    environment_receipts: list[tuple[Path, Path]] = []
    for environment in ("alpha", "beta", "gamma", "prod"):
        _cleanup_document, cleanup_path = (
            write_commercial_transition_cleanup_receipt(
                environment=environment,
                run_id="cleanup-1",
                research_release_id="research-release",
                research_manifest_digest=research_digest,
                commercial_release_id="commercial-release",
                commercial_manifest_digest=commercial_digest,
                cache_purged=True,
                media_copies_purged=True,
                signed_urls_revoked=True,
                output_root=output_root,
            )
        )
        _readback_document, readback_path = (
            write_commercial_transition_readback_receipt(
                environment=environment,
                run_id="readback-1",
                research_release_id="research-release",
                research_manifest_digest=research_digest,
                commercial_release_id="commercial-release",
                commercial_manifest_digest=commercial_digest,
                unauthorized_readback_count=0,
                unauthorized_asset_ids=[],
                output_root=output_root,
            )
        )
        environment_receipts.append((cleanup_path, readback_path))
    _document, path = write_commercial_transition_evidence(
        evidence_id="evidence-1",
        research_release_id="research-release",
        research_manifest_digest=research_digest,
        commercial_release_id="commercial-release",
        commercial_manifest_digest=commercial_digest,
        environment_receipts=environment_receipts,
        output_root=output_root,
    )
    return path


__all__ = ["write_cleanup_evidence"]
