from __future__ import annotations

from pathlib import Path

import pytest
from content.release.canonical import assemble
from content.release.canonical.aggregate_release import build_aggregate_release
from content.release.canonical.baseline_release import build_empty_baseline_release
from content.release.canonical.release_identity_incident import (
    ReleaseIdentityIncidentOpenError,
    canonical_release_identity_guard,
    record_release_identity_incident,
)
from core.io import write_json

RELEASE_ID = "collided-release"


def _record_incident(output_root: Path) -> None:
    sources: list[Path] = []
    for index, digest_char in enumerate(("a", "b"), start=1):
        path = output_root / f"source-attestation-{index}.json"
        write_json(
            path,
            {
                "releaseId": RELEASE_ID,
                "payloadSha256": "sha256:" + digest_char * 64,
                "canonicalMerkle": "sha256:" + str(index) * 64,
                "executionIds": [f"execution-{index}"],
            },
        )
        sources.append(path)
    record_release_identity_incident(
        release_id=RELEASE_ID,
        incident_id="collision-1",
        original_attestations=sources,
        recovery_provenances=[],
        output_root=output_root,
    )


def test_release_identity_incident__blocks_every_ordinary_canonical_creator__local_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "output"
    releases = output_root / "data/releases"
    _record_incident(output_root)

    with pytest.raises(
        ReleaseIdentityIncidentOpenError,
        match="DATA.RELEASE.IDENTITY_INCIDENT_OPEN",
    ):
        build_aggregate_release(
            publish_root=output_root / "data/publish",
            release_root=releases,
            release_id=RELEASE_ID,
            execution_ids=["missing-execution"],
            release_class="research",
            source_revision="sha256:" + "c" * 64,
            entity_catalog_digest="sha256:" + "d" * 64,
        )
    with pytest.raises(
        ReleaseIdentityIncidentOpenError,
        match="DATA.RELEASE.IDENTITY_INCIDENT_OPEN",
    ):
        build_empty_baseline_release(
            publish_root=output_root / "data/publish",
            release_root=releases,
            release_id=RELEASE_ID,
            release_class="research",
        )
    monkeypatch.setattr(
        assemble,
        "release_root",
        lambda release_id: releases / release_id,
    )
    with pytest.raises(
        ReleaseIdentityIncidentOpenError,
        match="DATA.RELEASE.IDENTITY_INCIDENT_OPEN",
    ):
        assemble.assemble_release("missing-execution", RELEASE_ID)


def test_release_identity_incident__does_not_name_deny_unrelated_release__local_contract(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    _record_incident(output_root)

    with canonical_release_identity_guard(
        output_root=output_root,
        release_id="fresh-release",
    ):
        pass
