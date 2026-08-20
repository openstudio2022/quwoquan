# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001.t3
"""Commercial transition cleanup, readback, and replacement receipt contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.local_contract.release.test_research_scale_and_commercial_transition__receipt__contract__local_contract_test import (
    CommercialTransitionError,
    CommercialTransitionEvidenceError,
    _commercial_release,
    _transition_research_release,
    _write,
    content_source_revision,
    payload_digest,
    source_identity_set,
    write_commercial_transition,
    write_commercial_transition_cleanup_receipt,
    write_commercial_transition_evidence,
    write_commercial_transition_readback_receipt,
)

def _cleanup_evidence(
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


def test_commercial_transition_records_replacement_and_four_environment_cleanup(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    research_release = _transition_research_release(output_root)
    commercial_release = _commercial_release(output_root)
    cleanup = _cleanup_evidence(
        output_root,
        research_release=research_release,
        commercial_release=commercial_release,
    )

    document, path = write_commercial_transition(
        research_release_id="research-release",
        commercial_release_id="commercial-release",
        transition_run_id="transition-1",
        cleanup_evidence_path=cleanup,
        release_root=output_root / "data/releases",
        output_root=output_root,
    )

    assert document["objectMigrations"] == [
        {
            "researchAssetId": "old-unverified",
            "objectRef": "posts/image/example",
            "action": "replaced",
            "commercialAssetIds": ["new-verified"],
        }
    ]
    assert document["unauthorizedReadbackCount"] == 0
    assert document["poolDigest"] == "sha256:" + "9" * 64
    assert document["researchSourceDigest"] == document["commercialSourceDigest"]
    assert document["cleanupEvidenceDigest"].startswith("sha256:")
    assert document["receiptDigest"].startswith("sha256:")
    assert path.is_file()


def test_commercial_transition_accepts_pool_source_identity_sets(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    research_release = _transition_research_release(output_root)
    commercial_release = _commercial_release(output_root)
    for release in (research_release, commercial_release):
        header_path = release / "payload/release.json"
        header = json.loads(header_path.read_text(encoding="utf-8"))
        header.pop("sourceDigest")
        identity = {
            "executionId": str(header["contents"][0]["executionId"]),
            "sourceDigest": "sha256:" + "a" * 64,
            "entityCatalogDigest": "sha256:" + "6" * 64,
        }
        identity["sourceRevision"] = content_source_revision(
            source_digest=identity["sourceDigest"],
            entity_catalog_digest=identity["entityCatalogDigest"],
        )
        identities, identity_set_digest = source_identity_set([identity])
        header["sourceIdentities"] = identities
        header["sourceIdentitySetDigest"] = identity_set_digest
        _write(header_path, header)
    cleanup = _cleanup_evidence(
        output_root,
        research_release=research_release,
        commercial_release=commercial_release,
    )

    document, _path = write_commercial_transition(
        research_release_id="research-release",
        commercial_release_id="commercial-release",
        transition_run_id="transition-set",
        cleanup_evidence_path=cleanup,
        release_root=output_root / "data/releases",
        output_root=output_root,
    )

    research_header = json.loads(
        (research_release / "payload/release.json").read_text(encoding="utf-8")
    )
    commercial_header = json.loads(
        (commercial_release / "payload/release.json").read_text(encoding="utf-8")
    )
    assert (
        document["researchSourceIdentitySetDigest"]
        == research_header["sourceIdentitySetDigest"]
    )
    assert (
        document["commercialSourceIdentitySetDigest"]
        == commercial_header["sourceIdentitySetDigest"]
    )
    assert "researchSourceDigest" not in document
    assert "commercialSourceDigest" not in document


def test_commercial_transition_rejects_pool_or_authorized_subset_drift(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    research_release = _transition_research_release(output_root)
    commercial_release = _commercial_release(output_root)
    commercial_header_path = commercial_release / "payload/release.json"
    commercial_header = json.loads(
        commercial_header_path.read_text(encoding="utf-8")
    )
    commercial_header["poolDigest"] = "sha256:" + "8" * 64
    _write(commercial_header_path, commercial_header)
    cleanup = _cleanup_evidence(
        output_root,
        research_release=research_release,
        commercial_release=commercial_release,
    )

    with pytest.raises(CommercialTransitionError, match="same frozen poolDigest"):
        write_commercial_transition(
            research_release_id="research-release",
            commercial_release_id="commercial-release",
            transition_run_id="transition-pool-drift",
            cleanup_evidence_path=cleanup,
            release_root=output_root / "data/releases",
            output_root=output_root,
        )

    subset_root = tmp_path / "subset-output"
    research_release = _transition_research_release(subset_root)
    commercial_release = _commercial_release(subset_root)
    commercial_header_path = commercial_release / "payload/release.json"
    commercial_header = json.loads(
        commercial_header_path.read_text(encoding="utf-8")
    )
    commercial_header["contents"][0]["contentId"] = "content-not-in-research"
    _write(commercial_header_path, commercial_header)
    cleanup = _cleanup_evidence(
        subset_root,
        research_release=research_release,
        commercial_release=commercial_release,
    )
    with pytest.raises(CommercialTransitionError, match="authorized object subset"):
        write_commercial_transition(
            research_release_id="research-release",
            commercial_release_id="commercial-release",
            transition_run_id="transition-subset-drift",
            cleanup_evidence_path=cleanup,
            release_root=subset_root / "data/releases",
            output_root=subset_root,
        )


def test_commercial_transition_blocks_nonzero_unauthorized_readback(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    research_release = _transition_research_release(output_root)
    commercial_release = _commercial_release(output_root)
    cleanup = _cleanup_evidence(
        output_root,
        research_release=research_release,
        commercial_release=commercial_release,
    )
    evidence = json.loads(cleanup.read_text(encoding="utf-8"))
    beta = next(
        row for row in evidence["environments"] if row["environment"] == "beta"
    )
    readback = output_root / beta["readbackReceiptRef"]
    tampered = json.loads(readback.read_text(encoding="utf-8"))
    tampered["unauthorizedReadbackCount"] = 1
    tampered["unauthorizedAssetIds"] = ["old-unverified"]
    _write(readback, tampered)

    with pytest.raises(CommercialTransitionError, match="schema violation"):
        write_commercial_transition(
            research_release_id="research-release",
            commercial_release_id="commercial-release",
            transition_run_id="transition-1",
            cleanup_evidence_path=cleanup,
            release_root=output_root / "data/releases",
            output_root=output_root,
        )


def test_commercial_transition_rejects_handwritten_boolean_evidence(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    research_release = _transition_research_release(output_root)
    commercial_release = _commercial_release(output_root)
    path = (
        output_root
        / "data/commercial-transition-evidence/commercial-release/handwritten/evidence.json"
    )
    _write(
        path,
        {
            "researchReleaseId": "research-release",
            "researchManifestDigest": payload_digest(research_release),
            "commercialReleaseId": "commercial-release",
            "commercialManifestDigest": payload_digest(commercial_release),
            "environments": [
                {"environment": environment, "cachePurged": True}
                for environment in ("alpha", "beta", "gamma", "prod")
            ],
        },
    )

    with pytest.raises(CommercialTransitionError, match="schema violation"):
        write_commercial_transition(
            research_release_id="research-release",
            commercial_release_id="commercial-release",
            transition_run_id="transition-1",
            cleanup_evidence_path=path,
            release_root=output_root / "data/releases",
            output_root=output_root,
        )


def test_commercial_transition_cleanup_receipt_is_create_once(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    common = {
        "environment": "alpha",
        "run_id": "cleanup-1",
        "research_release_id": "research-release",
        "research_manifest_digest": "sha256:" + "a" * 64,
        "commercial_release_id": "commercial-release",
        "commercial_manifest_digest": "sha256:" + "c" * 64,
        "cache_purged": True,
        "media_copies_purged": True,
        "signed_urls_revoked": True,
        "output_root": output_root,
    }
    first, _path = write_commercial_transition_cleanup_receipt(**common)
    second, _path = write_commercial_transition_cleanup_receipt(**common)
    assert second == first

    with pytest.raises(
        CommercialTransitionEvidenceError,
        match="create-once.*identity conflict",
    ):
        write_commercial_transition_cleanup_receipt(
            **{**common, "research_manifest_digest": "sha256:" + "b" * 64}
        )
