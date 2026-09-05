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
    iter_pool_records,
    latest_pool_record,
    pool_payload_digest,
    read_pool_record_history,
)
from content.release.canonical.object_source_identity import (  # noqa: E402
    source_identity_digest,
)
from content.release.canonical.object_transaction_contract import (  # noqa: E402
    ObjectTransactionError,
)
from core.source_digest import SourceDefinitionSnapshot, content_source_revision  # noqa: E402


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
            "distributionDecision": "commercial_allowed",
            "rightsAuditStatus": "verified",
            "authorizationProof": "https://example.test/proof",
            "licenseUrl": "https://example.test/terms",
            "author": "Commercial Creator",
            "licenseName": "Commercial License",
        }
    ]


def _reserved_identity(content_id: str, version: int) -> dict[str, object]:
    return {"contentId": content_id, "version": version}


def _rights_authority(*, usage_scope: str = "commercial") -> dict[str, str]:
    return {
        "ref": "posts/article/test/5.review/media_ref_review.json",
        "digest": "sha256:" + "9" * 64,
        "usageScope": usage_scope,
    }


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
        "derivedModifications": [],
    }


def _source_identity(
    execution_id: str,
) -> tuple[dict[str, str], SourceDefinitionSnapshot]:
    source_digest = SourceDefinitionSnapshot("sha256:" + "1" * 64)
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


def _pre_contract_record(root: Path, *, migration_identity: bool) -> None:
    evidence_ref, evidence_digest = _pool_evidence(root)
    record: dict[str, object] = {
        "schema": POOL_RECORD_SCHEMA,
        "objectType": "content",
        "objectId": "pre-contract-content",
        "objectRef": "article/pre-contract/1",
        "status": "active",
        "processResult": "completed",
        "qualityResult": "passed",
        "eligibilityResult": "passed",
        "rightsResult": "passed",
        "rightsAuthorityRef": "posts/article/test/5.review/media_ref_review.json",
        "rightsAuthorityDigest": "sha256:" + "9" * 64,
        "usageScope": "research",
        "evidenceRef": evidence_ref,
        "evidenceDigest": evidence_digest,
        "payloadDigest": pool_payload_digest(root),
    }
    if migration_identity:
        record.update(
            recordSequence=1,
            contentVersion=1,
            canonicalObjectDigest=record["payloadDigest"],
            sourceIdentity={
                "identityKind": "retired_migration_kind",
                "executionId": "pre-contract-execution",
                "sourceDigest": "sha256:" + "1" * 64,
                "canonicalObjectDigest": record["payloadDigest"],
                "migrationEvidenceDigest": "sha256:" + "2" * 64,
                "identityDigest": "sha256:" + "3" * 64,
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


def _legacy_author_record(*, payload_digest: str) -> dict[str, object]:
    return {
        "schema": POOL_RECORD_SCHEMA,
        "objectType": "author",
        "objectId": "builtin_travel_geo_editor",
        "objectRef": "qwq_creator_geo_editor_001",
        "status": "active",
        "processResult": "completed",
        "qualityResult": "passed",
        "eligibilityResult": "passed",
        "usageScope": None,
        "evidenceRef": "evidence/system_builtin_author_admission.json",
        "evidenceDigest": "sha256:" + "e" * 64,
        "payloadDigest": payload_digest,
        "version": 1,
    }


def _canonical_author_record(
    *,
    payload_digest: str,
    record_sequence: int = 2,
) -> dict[str, object]:
    legacy = _legacy_author_record(payload_digest=payload_digest)
    legacy.pop("version")
    return {
        **legacy,
        "recordSequence": record_sequence,
        "contentVersion": 1,
    }


def _write_author_history(
    root: Path,
    *,
    legacy_payload_digest: str,
    canonical_payload_digest: str | None = None,
    canonical_record_sequence: int = 2,
) -> None:
    versions = root / "_pool/versions"
    versions.mkdir(parents=True)
    (versions / "1.json").write_text(
        json.dumps(
            _legacy_author_record(payload_digest=legacy_payload_digest),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    if canonical_payload_digest is not None:
        (versions / "2.json").write_text(
            json.dumps(
                _canonical_author_record(
                    payload_digest=canonical_payload_digest,
                    record_sequence=canonical_record_sequence,
                ),
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


def test_unknown_usage_defaults_to_research(tmp_path: Path) -> None:
    source_manifest = {"contentId": "content-a", "version": 1, "variantPurpose": "original"}
    fields = build_content_pool_fields(
        source_manifest=source_manifest,
        canonical_ref="article/guide/a/1",
        source_task_id="task-1",
        attestation_path=_attestation(tmp_path),
        rights_authority=_rights_authority(),
        publish_root=tmp_path / "publish",
        rights_rows=[],
        reserved_identity=_reserved_identity("content-a", 1),
    )
    assert fields["version"] == 1
    assert fields["admission"]["usageScope"] == "research"
    assert fields["variantPurpose"] == "original"


def test_content_pool_fields_require_explicit_variant_purpose(tmp_path: Path) -> None:
    with pytest.raises(ObjectTransactionError, match="variantPurpose"):
        build_content_pool_fields(
            source_manifest={"contentId": "content-a", "version": 1},
            canonical_ref="article/guide/a/1",
            source_task_id="task-1",
            attestation_path=_attestation(tmp_path),
            rights_authority=_rights_authority(),
            publish_root=tmp_path / "publish",
            rights_rows=[],
            reserved_identity=_reserved_identity("content-a", 1),
        )


def test_ai_research_scope_caps_commercial_hard_facts(tmp_path: Path) -> None:
    manifest = _commercial_manifest()
    manifest["variantPurpose"] = "original"
    fields = build_content_pool_fields(
        source_manifest=manifest,
        canonical_ref="article/guide/ai-research/1",
        source_task_id="task-ai-research",
        attestation_path=_attestation(tmp_path),
        rights_authority=_rights_authority(usage_scope="research"),
        publish_root=tmp_path / "publish",
        rights_rows=_commercial_rights(),
        reserved_identity=_reserved_identity("travel_panda_base_guide", 2),
    )
    assert fields["admission"]["usageScope"] == "research"


def test_ai_research_scope_rejects_commercial_variant(tmp_path: Path) -> None:
    with pytest.raises(ObjectTransactionError, match="COMMERCIAL_VARIANT_NOT_ADMITTED"):
        build_content_pool_fields(
            source_manifest=_commercial_manifest(),
            canonical_ref="article/guide/ai-research-commercial/1",
            source_task_id="task-ai-research-commercial",
            attestation_path=_attestation(tmp_path),
            rights_authority=_rights_authority(usage_scope="research"),
            publish_root=tmp_path / "publish",
            rights_rows=_commercial_rights(),
            reserved_identity=_reserved_identity("travel_panda_base_guide", 2),
        )


def test_commercial_variant_requires_publication_proof(tmp_path: Path) -> None:
    manifest = _commercial_manifest()
    manifest["sourceAttribution"] = {}
    with pytest.raises(ObjectTransactionError, match="COMMERCIAL_VARIANT_NOT_ADMITTED"):
        build_content_pool_fields(
            source_manifest=manifest,
            canonical_ref="article/guide/a-commercial/1",
            source_task_id="task-2",
            attestation_path=_attestation(tmp_path),
            rights_authority=_rights_authority(),
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
        rights_authority=_rights_authority(),
        publish_root=tmp_path / "publish",
        rights_rows=_commercial_rights(),
        reserved_identity=_reserved_identity("travel_panda_base_guide", 2),
    )
    assert fields["version"] == 2
    assert fields["admission"]["usageScope"] == "commercial"


def test_pre_sequence_record_is_excluded_but_does_not_block_new_identity(
    tmp_path: Path,
) -> None:
    """Retired sidecars reserve identity without becoming pool admission."""

    stale = tmp_path / "publish/posts/article/pre-contract/1"
    stale.mkdir(parents=True)
    (stale / "manifest.json").write_text(
        json.dumps({"contentType": "article"}), encoding="utf-8"
    )
    _pre_contract_record(stale, migration_identity=False)

    fields = build_content_pool_fields(
        source_manifest={"contentId": "modern-content", "version": 1, "variantPurpose": "original"},
        canonical_ref="article/modern/1",
        source_task_id="modern-task",
        attestation_path=_attestation(tmp_path),
        rights_authority=_rights_authority(),
        publish_root=tmp_path / "publish",
        rights_rows=[],
        reserved_identity=_reserved_identity("modern-content", 1),
    )

    assert fields["contentId"] == "modern-content"
    assert fields["version"] == 1
    with pytest.raises(ObjectTransactionError, match="VERSION_CONFLICT"):
        build_content_pool_fields(
            source_manifest={"contentId": "pre-contract-content", "version": 1, "variantPurpose": "original"},
            canonical_ref="article/modern/1",
            source_task_id="modern-task",
            attestation_path=_attestation(tmp_path),
            rights_authority=_rights_authority(),
            publish_root=tmp_path / "publish",
            rights_rows=[],
            reserved_identity=_reserved_identity("pre-contract-content", 1),
        )


def test_exact_legacy_author_record_isolated_by_canonical_successor(
    tmp_path: Path,
) -> None:
    """A proven v2 repair admits the author without rewriting invalid v1."""

    root = tmp_path / "publish/creators/qwq_creator_geo_editor_001"
    payload_digest = "sha256:" + "a" * 64
    _write_author_history(
        root,
        legacy_payload_digest=payload_digest,
        canonical_payload_digest=payload_digest,
    )

    history = read_pool_record_history(root, object_type="author")

    assert [row["recordSequence"] for row in history.records] == [2]
    assert len(history.exclusions) == 1
    exclusion = history.exclusions[0]
    assert exclusion.record_ref == "_pool/versions/1.json"
    assert exclusion.record_sequence == 1
    assert exclusion.reason == "DATA.POOL.RECORD_SEQUENCE_MISSING"
    assert exclusion.superseded_by == 2
    assert [row["recordSequence"] for row in iter_pool_records(
        root, object_type="author"
    )] == [2]
    assert latest_pool_record(root, "author")["recordSequence"] == 2


def test_all_invalid_author_history_remains_excluded(tmp_path: Path) -> None:
    root = tmp_path / "publish/creators/qwq_creator_geo_editor_001"
    _write_author_history(
        root,
        legacy_payload_digest="sha256:" + "a" * 64,
    )

    history = read_pool_record_history(root, object_type="author")

    assert history.records == ()
    assert history.exclusions[0].superseded_by is None
    with pytest.raises(ObjectTransactionError, match="RECORD_SEQUENCE_MISSING"):
        latest_pool_record(root, "author")


def test_legacy_author_digest_conflict_remains_blocking(tmp_path: Path) -> None:
    root = tmp_path / "publish/creators/qwq_creator_geo_editor_001"
    _write_author_history(
        root,
        legacy_payload_digest="sha256:" + "a" * 64,
        canonical_payload_digest="sha256:" + "b" * 64,
    )

    with pytest.raises(ObjectTransactionError, match="RECORD_DIGEST_CONFLICT"):
        read_pool_record_history(root, object_type="author")


def test_record_path_and_embedded_sequence_conflict_remains_blocking(
    tmp_path: Path,
) -> None:
    root = tmp_path / "publish/creators/qwq_creator_geo_editor_001"
    payload_digest = "sha256:" + "a" * 64
    _write_author_history(
        root,
        legacy_payload_digest=payload_digest,
        canonical_payload_digest=payload_digest,
        canonical_record_sequence=3,
    )

    with pytest.raises(ObjectTransactionError, match="RECORD_SEQUENCE_CONFLICT"):
        read_pool_record_history(root, object_type="author")


def test_retired_migration_identity_is_collision_only(tmp_path: Path) -> None:
    """Retired identity stays non-admitted but cannot block unrelated content."""

    stale = tmp_path / "publish/posts/article/pre-contract/1"
    stale.mkdir(parents=True)
    (stale / "manifest.json").write_text(
        json.dumps({"contentType": "article"}), encoding="utf-8"
    )
    _pre_contract_record(stale, migration_identity=True)

    fields = build_content_pool_fields(
        source_manifest={"contentId": "modern-content", "version": 1, "variantPurpose": "original"},
        canonical_ref="article/modern/1",
        source_task_id="modern-task",
        attestation_path=_attestation(tmp_path),
        rights_authority=_rights_authority(),
        publish_root=tmp_path / "publish",
        rights_rows=[],
        reserved_identity=_reserved_identity("modern-content", 1),
    )

    assert fields["contentId"] == "modern-content"
    with pytest.raises(ObjectTransactionError, match="SOURCE_IDENTITY_INVALID"):
        latest_pool_record(stale, "content")
    with pytest.raises(ObjectTransactionError, match="VERSION_CONFLICT"):
        build_content_pool_fields(
            source_manifest={"contentId": "pre-contract-content", "version": 1, "variantPurpose": "original"},
            canonical_ref="article/modern/1",
            source_task_id="modern-task",
            attestation_path=_attestation(tmp_path),
            rights_authority=_rights_authority(),
            publish_root=tmp_path / "publish",
            rights_rows=[],
            reserved_identity=_reserved_identity("pre-contract-content", 1),
        )


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
            "rightsResult": "passed",
            "rightsAuthorityRef": "posts/article/test/5.review/media_ref_review.json",
            "rightsAuthorityDigest": "sha256:" + "9" * 64,
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
            source_manifest={"contentId": "modern-content", "version": 1, "variantPurpose": "original"},
            canonical_ref="article/modern/1",
            source_task_id="modern-task",
            attestation_path=_attestation(tmp_path),
            rights_authority=_rights_authority(),
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
            "rightsResult": "passed",
            "rightsAuthorityRef": "posts/article/test/5.review/media_ref_review.json",
            "rightsAuthorityDigest": "sha256:" + "9" * 64,
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
            source_manifest={"contentId": "modern-content", "version": 1, "variantPurpose": "original"},
            canonical_ref="article/modern/1",
            source_task_id="modern-task",
            attestation_path=_attestation(tmp_path),
            rights_authority=_rights_authority(),
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
            rights_authority=_rights_authority(),
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
    review = root / "5.review/media_ref_review.json"
    review.parent.mkdir(parents=True, exist_ok=True)
    review.write_text('{"passed":true}\n', encoding="utf-8")
    review_digest = "sha256:" + hashlib.sha256(review.read_bytes()).hexdigest()
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
                    "rightsResult": "passed",
                    "rightsAuthorityRef": "posts/article/work/1/5.review/media_ref_review.json",
                    "rightsAuthorityDigest": review_digest,
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
