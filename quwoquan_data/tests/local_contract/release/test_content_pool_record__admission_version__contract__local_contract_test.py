from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

DATA_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(DATA_SCRIPTS))

from content.release.canonical.content_pool_record import (  # noqa: E402
    POOL_RECORD_SCHEMA,
    append_pool_record,
    build_canonical_pool_record,
    build_content_pool_fields,
    latest_pool_record,
    pool_payload_digest,
)
from content.release.canonical.object_source_identity import (  # noqa: E402
    source_identity_digest,
)
from content.release.canonical.object_transaction_contract import (  # noqa: E402
    ObjectTransactionError,
)
from core.source_digest import SourceDigest, content_source_revision  # noqa: E402


def _attestation(tmp_path: Path) -> Path:
    path = tmp_path / "attestation.json"
    path.write_text('{"decision":"approved"}\n', encoding="utf-8")
    return path


def _commercial_manifest() -> dict[str, object]:
    return {
        "contentId": "travel_panda_base_guide",
        "version": 2,
        "variantPurpose": "commercial_variant",
        "admission": {"usageScope": "commercial"},
        "sourceAttribution": {
            "publicationAdmission": "commercial_release",
            "commercialAuthorizationStatus": "verified",
            "authorizationProofUrl": "https://example.test/proof",
            "termsUrl": "https://example.test/terms",
        },
    }


def _commercial_rights() -> list[dict[str, object]]:
    return [
        {
            "rightsAuditStatus": "verified",
            "authorizationProof": "https://example.test/proof",
            "licenseUrl": "https://example.test/terms",
        }
    ]


def _reserved_identity(content_id: str, version: int) -> dict[str, object]:
    return {"contentId": content_id, "version": version}


def _source_attribution() -> dict[str, object]:
    return {
        "isOriginal": False,
        "originalCreatorName": "Research Creator",
        "platform": "Research Media",
        "sourcePostUrl": "https://source.example/post",
        "originalAssetUrl": "https://source.example/asset",
        "attributionText": "Research Creator / Research Media",
        "rightsBasis": "public research reference",
        "commercialAuthorizationStatus": "unverified",
        "publicationAdmission": "research_release",
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-08-11T00:00:00Z",
        "takedownPolicy": "remove on substantiated request",
    }


def _source_identity(execution_id: str) -> tuple[dict[str, str], SourceDigest]:
    source_digest = SourceDigest("sha256:" + "1" * 64)
    entity_catalog_digest = "sha256:" + "2" * 64
    identity = {
        "executionId": execution_id,
        "sourceRevision": content_source_revision(
            source_digest=source_digest.digest,
            entity_catalog_digest=entity_catalog_digest,
        ),
        "sourceDigest": source_digest.digest,
        "entityCatalogDigest": entity_catalog_digest,
    }
    return (
        {**identity, "identityDigest": source_identity_digest(identity)},
        source_digest,
    )


def _pool_evidence(root: Path) -> tuple[str, str]:
    path = root / "attestation.json"
    path.write_text('{"decision":"approved"}\n', encoding="utf-8")
    return (
        "attestation.json",
        "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def _legacy_record(root: Path, *, migration_identity: bool) -> None:
    evidence_ref, evidence_digest = _pool_evidence(root)
    record: dict[str, object] = {
        "schema": POOL_RECORD_SCHEMA,
        "objectType": "content",
        "objectId": "legacy-content",
        "objectRef": "article/legacy/1",
        "status": "active",
        "processResult": "completed",
        "qualityResult": "passed",
        "eligibilityResult": "passed",
        "usageScope": "research",
        "evidenceRef": evidence_ref,
        "evidenceDigest": evidence_digest,
        "payloadDigest": pool_payload_digest(root),
    }
    if migration_identity:
        stable_identity = {
            "identityKind": "legacy_canonical_migration",
            "executionId": "legacy-execution",
            "sourceDigest": "sha256:" + "1" * 64,
            "canonicalObjectDigest": record["payloadDigest"],
            "migrationEvidenceDigest": "sha256:" + "2" * 64,
        }
        record.update(
            recordSequence=1,
            contentVersion=1,
            canonicalObjectDigest=record["payloadDigest"],
            sourceIdentity={
                **stable_identity,
                "identityDigest": source_identity_digest(stable_identity),
            },
            sourceAttribution=_source_attribution(),
        )
    else:
        record["version"] = 1
    versions = root / "_pool/versions"
    versions.mkdir(parents=True)
    (versions / "1.json").write_text(
        json.dumps(record, ensure_ascii=False), encoding="utf-8"
    )


def test_unknown_usage_defaults_to_research(tmp_path: Path) -> None:
    source_manifest = {"contentId": "content-a", "version": 1}
    fields = build_content_pool_fields(
        source_manifest=source_manifest,
        canonical_ref="article/guide/a/1",
        source_task_id="task-1",
        attestation_path=_attestation(tmp_path),
        publish_root=tmp_path / "publish",
        rights_rows=[],
        reserved_identity=_reserved_identity("content-a", 1),
    )
    assert fields["version"] == 1
    assert fields["admission"]["usageScope"] == "research"
    assert fields["variantPurpose"] == "original"


def test_commercial_variant_requires_publication_proof(tmp_path: Path) -> None:
    manifest = _commercial_manifest()
    manifest["sourceAttribution"] = {}
    with pytest.raises(ObjectTransactionError, match="COMMERCIAL_PROOF_INCOMPLETE"):
        build_content_pool_fields(
            source_manifest=manifest,
            canonical_ref="article/guide/a-commercial/1",
            source_task_id="task-2",
            attestation_path=_attestation(tmp_path),
            publish_root=tmp_path / "publish",
            rights_rows=_commercial_rights(),
            reserved_identity=_reserved_identity(
                "travel_panda_base_guide", 2
            ),
        )


def test_existing_version_requires_exact_next_append(tmp_path: Path) -> None:
    manifest_path = tmp_path / "publish/posts/article/a/manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps({"contentId": "travel_panda_base_guide", "version": 1}),
        encoding="utf-8",
    )
    fields = build_content_pool_fields(
        source_manifest=_commercial_manifest(),
        canonical_ref="article/guide/a-commercial/1",
        source_task_id="task-2",
        attestation_path=_attestation(tmp_path),
        publish_root=tmp_path / "publish",
        rights_rows=_commercial_rights(),
        reserved_identity=_reserved_identity("travel_panda_base_guide", 2),
    )
    assert fields["version"] == 2
    assert fields["admission"]["usageScope"] == "commercial"


@pytest.mark.parametrize("migration_identity", [False, True])
def test_legacy_record_without_manifest_identity_is_excluded_from_known_versions(
    tmp_path: Path,
    migration_identity: bool,
) -> None:
    legacy = tmp_path / "publish/posts/article/legacy/1"
    legacy.mkdir(parents=True)
    (legacy / "manifest.json").write_text(
        json.dumps({"contentType": "article"}), encoding="utf-8"
    )
    _legacy_record(legacy, migration_identity=migration_identity)

    fields = build_content_pool_fields(
        source_manifest={"contentId": "modern-content", "version": 1},
        canonical_ref="article/modern/1",
        source_task_id="modern-task",
        attestation_path=_attestation(tmp_path),
        publish_root=tmp_path / "publish",
        rights_rows=[],
        reserved_identity=_reserved_identity("modern-content", 1),
    )

    assert fields["contentId"] == "modern-content"
    assert fields["version"] == 1


@pytest.mark.parametrize(
    "manifest",
    [
        {"contentType": "article"},
        {"contentId": "legacy-content"},
        {"version": 1},
    ],
)
def test_modern_record_requires_complete_matching_manifest_identity(
    tmp_path: Path,
    manifest: dict[str, object],
) -> None:
    historical = tmp_path / "publish/posts/article/historical/1"
    historical.mkdir(parents=True)
    (historical / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    source_identity, _ = _source_identity("modern-execution")
    evidence_ref, evidence_digest = _pool_evidence(historical)
    payload_digest = pool_payload_digest(historical)
    append_pool_record(
        object_root=historical,
        record={
            "schema": POOL_RECORD_SCHEMA,
            "objectType": "content",
            "objectId": "legacy-content",
            "objectRef": "article/historical/1",
            "recordSequence": 1,
            "contentVersion": 1,
            "status": "active",
            "processResult": "completed",
            "qualityResult": "passed",
            "eligibilityResult": "passed",
            "usageScope": "research",
            "evidenceRef": evidence_ref,
            "evidenceDigest": evidence_digest,
            "payloadDigest": payload_digest,
            "canonicalObjectDigest": payload_digest,
            "sourceIdentity": source_identity,
            "sourceAttribution": _source_attribution(),
        },
    )

    with pytest.raises(ObjectTransactionError, match="IDENTITY_INVALID"):
        build_content_pool_fields(
            source_manifest={"contentId": "modern-content", "version": 1},
            canonical_ref="article/modern/1",
            source_task_id="modern-task",
            attestation_path=_attestation(tmp_path),
            publish_root=tmp_path / "publish",
            rights_rows=[],
            reserved_identity=_reserved_identity("modern-content", 1),
        )


def test_complete_manifest_identity_must_match_pool_record(tmp_path: Path) -> None:
    historical = tmp_path / "publish/posts/article/historical/1"
    historical.mkdir(parents=True)
    (historical / "manifest.json").write_text(
        json.dumps({"contentId": "content-a", "version": 1}),
        encoding="utf-8",
    )
    source_identity, _ = _source_identity("modern-execution")
    evidence_ref, evidence_digest = _pool_evidence(historical)
    payload_digest = pool_payload_digest(historical)
    append_pool_record(
        object_root=historical,
        record={
            "schema": POOL_RECORD_SCHEMA,
            "objectType": "content",
            "objectId": "content-b",
            "objectRef": "article/historical/1",
            "recordSequence": 1,
            "contentVersion": 1,
            "status": "active",
            "processResult": "completed",
            "qualityResult": "passed",
            "eligibilityResult": "passed",
            "usageScope": "research",
            "evidenceRef": evidence_ref,
            "evidenceDigest": evidence_digest,
            "payloadDigest": payload_digest,
            "canonicalObjectDigest": payload_digest,
            "sourceIdentity": source_identity,
            "sourceAttribution": _source_attribution(),
        },
    )

    with pytest.raises(ObjectTransactionError, match="manifest/pool record identity drift"):
        build_content_pool_fields(
            source_manifest={"contentId": "modern-content", "version": 1},
            canonical_ref="article/modern/1",
            source_task_id="modern-task",
            attestation_path=_attestation(tmp_path),
            publish_root=tmp_path / "publish",
            rights_rows=[],
            reserved_identity=_reserved_identity("modern-content", 1),
        )


def test_same_content_version_conflicts(tmp_path: Path) -> None:
    manifest_path = tmp_path / "publish/posts/article/a/manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps({"contentId": "travel_panda_base_guide", "version": 2}),
        encoding="utf-8",
    )
    with pytest.raises(ObjectTransactionError, match="VERSION_CONFLICT"):
        build_content_pool_fields(
            source_manifest=_commercial_manifest(),
            canonical_ref="article/guide/a-commercial/1",
            source_task_id="task-2",
            attestation_path=_attestation(tmp_path),
            publish_root=tmp_path / "publish",
            rights_rows=_commercial_rights(),
            reserved_identity=_reserved_identity(
                "travel_panda_base_guide", 2
            ),
        )


def test_explicit_content_record_uses_content_identity_not_author_identity(
    tmp_path: Path,
) -> None:
    root = tmp_path / "publish/posts/article/work/1"
    root.mkdir(parents=True)
    execution_id = "execution-a"
    source_identity, source_digest = _source_identity(execution_id)
    attestation = root / "attestation.json"
    attestation.write_text('{"decision":"approved"}\n', encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "contentId": "content-a",
                "authorId": "author-a",
                "version": 1,
                "executionId": execution_id,
                "sourceDigest": source_digest.to_document(),
                "sourceIdentity": source_identity,
                "sourceAttribution": _source_attribution(),
                "status": "active",
                "admission": {
                    "processResult": "completed",
                    "qualityResult": "passed",
                    "usageScope": "research",
                    "evidenceRef": "attestation.json",
                    "evidenceDigest": (
                        "sha256:"
                        + hashlib.sha256(attestation.read_bytes()).hexdigest()
                    ),
                },
            }
        ),
        encoding="utf-8",
    )
    append_pool_record(
        object_root=root,
        record=build_canonical_pool_record(
            object_root=root,
            object_type="content",
            object_ref="article/work/1",
        ),
    )

    assert latest_pool_record(root, "content")["objectId"] == "content-a"
