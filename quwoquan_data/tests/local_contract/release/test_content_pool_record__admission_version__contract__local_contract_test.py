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
    is_pool_record_admitted,
    iter_pool_records,
    latest_pool_record,
    plan_content_pool_identity,
    pool_payload_digest,
    read_pool_record_history,
)
from content.release.canonical.effective_admission import (  # noqa: E402
    resolve_effective_admission,
)
from content.release.canonical.object_source_identity import (  # noqa: E402
    source_identity_digest,
)
from content.release.canonical.object_transaction_contract import (  # noqa: E402
    ObjectTransactionError,
)
from core.source_digest import SourceDefinitionSnapshot, content_source_revision  # noqa: E402


def _content_review(tmp_path: Path) -> Path:
    path = tmp_path / "content_review.json"
    path.write_text('{"decision":"approved"}\n', encoding="utf-8")
    return path


def _commercial_manifest() -> dict[str, object]:
    return {
        "contentId": "travel_panda_base_guide", "version": 2,
        "sourceAttribution": _source_attribution(),
    }


def _commercial_rights() -> list[dict[str, object]]:
    return [
        {
            "rightsAuditStatus": "verified",
            "authorizationProof": "https://example.test/proof",
            "licenseUrl": "https://example.test/terms",
            "author": "Commercial Creator",
            "licenseName": "Commercial License",
        }
    ]


def _reserved_identity(content_id: str, version: int) -> dict[str, object]:
    return {"contentId": content_id, "version": version}


def _rights_authority(
    *,
    canonical_ref: str = "article/test",
) -> dict[str, str]:
    return {
        "ref": f"posts/{canonical_ref}/content_review.json",
        "digest": "sha256:" + "9" * 64,
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
    path = root / "content_review.json"
    path.write_text('{"decision":"approved"}\n', encoding="utf-8")
    return (
        "content_review.json",
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
        "rightsAuthorityRef": "posts/article/test/content_review.json",
        "rightsAuthorityDigest": "sha256:" + "9" * 64,
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
    versions = root / "records"
    versions.mkdir(parents=True)
    (versions / "1.json").write_text(
        json.dumps(record, ensure_ascii=False), encoding="utf-8"
    )


def _pre_rights_canonical_record(
    root: Path,
    *,
    record_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps({"contentId": "historical-content", "version": 1, "objectRef": "article/historical/1"}),
        encoding="utf-8",
    )
    evidence_ref, evidence_digest = _pool_evidence(root)
    source_identity, _ = _source_identity("historical-execution")
    payload_digest = pool_payload_digest(root)
    record: dict[str, object] = {
        "schema": POOL_RECORD_SCHEMA,
        "objectType": "content",
        "objectId": "historical-content",
        "objectRef": "article/historical/1",
        "recordSequence": 1,
        "contentVersion": 1,
        "status": "active",
        "processResult": "completed",
        "qualityResult": "passed",
        "eligibilityResult": "passed",
        "evidenceRef": evidence_ref,
        "evidenceDigest": evidence_digest,
        "payloadDigest": payload_digest,
        "canonicalObjectDigest": payload_digest,
        "sourceIdentity": source_identity,
        "sourceAttribution": _source_attribution(),
    }
    record.update(record_overrides or {})
    versions = root / "records"
    versions.mkdir(parents=True)
    (versions / "1.json").write_text(
        json.dumps(record, ensure_ascii=False), encoding="utf-8"
    )
    return record


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
    versions = root / "records"
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


@pytest.mark.parametrize("patch", [
    {"variantPurpose": "commercial_variant"},
    {"admission": {"usageScope": "research"}},
    {"sourceAttribution": {**_source_attribution(), "publicationAdmission": "research_release"}},
])
def test_pool_writer_rejects_retired_classification(tmp_path: Path, patch: dict[str, object]) -> None:
    manifest = {**_commercial_manifest(), **patch}
    with pytest.raises(ObjectTransactionError, match="RETIRED_CLASSIFICATION_FIELD"):
        build_content_pool_fields(
            source_manifest=manifest, canonical_ref="article/guide/a/1", source_task_id="task-1",
            content_review_path=_content_review(tmp_path),
            rights_authority=_rights_authority(canonical_ref="article/guide/a/1"),
            publish_root=tmp_path / "publish", rights_rows=_commercial_rights(),
            reserved_identity=_reserved_identity("travel_panda_base_guide", 2),
        )


def test_valid_source_omits_object_classification(tmp_path: Path) -> None:
    fields = build_content_pool_fields(
        source_manifest=_commercial_manifest(), canonical_ref="article/guide/a/1", source_task_id="task-1",
        content_review_path=_content_review(tmp_path),
        rights_authority=_rights_authority(canonical_ref="article/guide/a/1"),
        publish_root=tmp_path / "publish", rights_rows=_commercial_rights(),
        reserved_identity=_reserved_identity("travel_panda_base_guide", 2),
    )
    assert "variantPurpose" not in fields
    assert "usageScope" not in fields["admission"]
    assert fields["admission"]["rightsResult"] == "passed"


def test_existing_version_requires_exact_next_append(tmp_path: Path) -> None:
    manifest_path = tmp_path / "publish/posts/article/a/manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps({"contentId": "travel_panda_base_guide", "version": 1, "objectRef": "article/a"}),
        encoding="utf-8",
    )
    fields = build_content_pool_fields(
        source_manifest=_commercial_manifest(),
        canonical_ref="article/guide/a-commercial/1",
        source_task_id="task-2",
        content_review_path=_content_review(tmp_path),
        rights_authority=_rights_authority(canonical_ref="article/guide/a-commercial/1"),
        publish_root=tmp_path / "publish",
        rights_rows=_commercial_rights(),
        reserved_identity=_reserved_identity("travel_panda_base_guide", 2),
    )
    assert fields["version"] == 2
    assert "usageScope" not in fields["admission"]


def test_pre_sequence_record_blocks_identity_scan(tmp_path: Path) -> None:
    stale = tmp_path / "publish/posts/article/pre-contract/1"
    stale.mkdir(parents=True)
    (stale / "manifest.json").write_text(json.dumps({"contentType": "article", "objectRef": "article/pre-contract/1"}), encoding="utf-8")
    _pre_contract_record(stale, migration_identity=False)
    with pytest.raises(ObjectTransactionError, match="RECORD_SEQUENCE_MISSING"):
        plan_content_pool_identity(
            source_manifest={"contentId": "modern-content", "version": 1},
            canonical_ref="article/modern/1", publish_root=tmp_path / "publish",
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
    assert exclusion.record_ref == "records/1.json"
    assert exclusion.record_sequence == 1
    assert exclusion.reason == "DATA.POOL.RECORD_SEQUENCE_MISSING"
    assert exclusion.superseded_by is None
    with pytest.raises(ObjectTransactionError, match="RECORD_SEQUENCE_MISSING"):
        iter_pool_records(root, object_type="author")
    with pytest.raises(ObjectTransactionError, match="RECORD_SEQUENCE_MISSING"):
        latest_pool_record(root, "author")


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

    history = read_pool_record_history(root, object_type="author")
    assert history.exclusions[0].superseded_by is None
    with pytest.raises(ObjectTransactionError, match="RECORD_SEQUENCE_MISSING"):
        iter_pool_records(root, object_type="author")


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


def test_retired_migration_identity_blocks_every_reader(tmp_path: Path) -> None:
    stale = tmp_path / "publish/posts/article/pre-contract/1"
    stale.mkdir(parents=True)
    (stale / "manifest.json").write_text(json.dumps({"contentType": "article", "objectRef": "article/pre-contract/1"}), encoding="utf-8")
    _pre_contract_record(stale, migration_identity=True)
    with pytest.raises(ObjectTransactionError, match="SOURCE_IDENTITY_INVALID"):
        latest_pool_record(stale, "content")
    with pytest.raises(ObjectTransactionError, match="SOURCE_IDENTITY_INVALID"):
        plan_content_pool_identity(
            source_manifest={"contentId": "modern-content", "version": 1},
            canonical_ref="article/modern/1", publish_root=tmp_path / "publish",
        )


def test_pre_rights_record_blocks_identity_scan_without_mutation(tmp_path: Path) -> None:
    historical = tmp_path / "publish/posts/article/historical/1"
    _pre_rights_canonical_record(historical)
    record_path = historical / "records/1.json"
    original_bytes = record_path.read_bytes()
    with pytest.raises(ObjectTransactionError, match="RECORD_RIGHTS_INVALID"):
        plan_content_pool_identity(
            source_manifest={"contentId": "unrelated-content", "version": 1},
            canonical_ref="article/unrelated/1", publish_root=tmp_path / "publish",
        )
    assert record_path.read_bytes() == original_bytes


def test_pre_rights_record_stays_excluded_from_direct_admission(
    tmp_path: Path,
) -> None:
    historical = tmp_path / "publish/posts/article/historical/1"
    raw = _pre_rights_canonical_record(historical)
    record_path = historical / "records/1.json"
    original_bytes = record_path.read_bytes()

    history = read_pool_record_history(historical, object_type="content")

    assert history.records == ()
    assert len(history.exclusions) == 1
    assert history.exclusions[0].reason == "DATA.POOL.RECORD_RIGHTS_INVALID"
    assert history.exclusions[0].superseded_by is None
    assert not is_pool_record_admitted(raw)
    with pytest.raises(
        ObjectTransactionError, match=r"^DATA\.POOL\.RECORD_RIGHTS_INVALID"
    ):
        latest_pool_record(historical, "content")
    with pytest.raises(
        ObjectTransactionError, match=r"^DATA\.POOL\.RECORD_RIGHTS_INVALID"
    ):
        resolve_effective_admission(historical, object_type="content")
    assert record_path.read_bytes() == original_bytes


@pytest.mark.parametrize(
    ("record_overrides", "error"),
    [
        ({"rightsResult": "passed"}, "RECORD_RIGHTS_AUTHORITY_MISSING"),
        (
            {
                "rightsResult": "failed",
                "rightsAuthorityRef": "5.review/media_ref_review.json",
                "rightsAuthorityDigest": "sha256:" + "9" * 64,
            },
            "RECORD_RIGHTS_INVALID",
        ),
        (
            {
                "rightsResult": "passed",
                "rightsAuthorityRef": "5.review/media_ref_review.json",
                "rightsAuthorityDigest": "sha256" + ":invalid",
            },
            "RECORD_RIGHTS_AUTHORITY_DIGEST_INVALID",
        ),
        ({"processResult": "pending"}, "RECORD_PROCESS_INVALID"),
    ],
)
def test_non_legacy_malformed_records_still_block_collision_scan(
    tmp_path: Path,
    record_overrides: dict[str, object],
    error: str,
) -> None:
    historical = tmp_path / "publish/posts/article/historical/1"
    _pre_rights_canonical_record(
        historical, record_overrides=record_overrides
    )

    with pytest.raises(ObjectTransactionError, match=error):
        build_content_pool_fields(
            source_manifest={
                "contentId": "unrelated-content",
                "version": 1,
            },
            canonical_ref="article/unrelated/1",
            source_task_id="unrelated-task",
            content_review_path=_content_review(tmp_path),
            rights_authority=_rights_authority(canonical_ref="article/unrelated/1"),
            publish_root=tmp_path / "publish",
            rights_rows=[],
            reserved_identity=_reserved_identity("unrelated-content", 1),
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
            "rightsAuthorityRef": "posts/article/test/content_review.json",
            "rightsAuthorityDigest": "sha256:" + "9" * 64,
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
            source_manifest={"contentId": "modern-content", "version": 1, "sourceAttribution": _source_attribution()},
            canonical_ref="article/modern/1",
            source_task_id="modern-task",
            content_review_path=_content_review(tmp_path),
            rights_authority=_rights_authority(canonical_ref="article/modern/1"),
            publish_root=tmp_path / "publish",
            rights_rows=[],
            reserved_identity=_reserved_identity("modern-content", 1),
        )


def test_complete_manifest_identity_must_match_pool_record(tmp_path: Path) -> None:
    historical = tmp_path / "publish/posts/article/historical/1"
    historical.mkdir(parents=True)
    (historical / "manifest.json").write_text(
        json.dumps({"contentId": "content-a", "version": 1, "objectRef": "article/historical/1"}),
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
            "rightsAuthorityRef": "posts/article/test/content_review.json",
            "rightsAuthorityDigest": "sha256:" + "9" * 64,
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
            source_manifest={"contentId": "modern-content", "version": 1, "sourceAttribution": _source_attribution()},
            canonical_ref="article/modern/1",
            source_task_id="modern-task",
            content_review_path=_content_review(tmp_path),
            rights_authority=_rights_authority(canonical_ref="article/modern/1"),
            publish_root=tmp_path / "publish",
            rights_rows=[],
            reserved_identity=_reserved_identity("modern-content", 1),
        )


def test_same_content_version_conflicts(tmp_path: Path) -> None:
    manifest_path = tmp_path / "publish/posts/article/a/manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps({"contentId": "travel_panda_base_guide", "version": 2, "objectRef": "article/a"}),
        encoding="utf-8",
    )
    with pytest.raises(ObjectTransactionError, match="VERSION_CONFLICT"):
        build_content_pool_fields(
            source_manifest=_commercial_manifest(),
            canonical_ref="article/guide/a-commercial/1",
            source_task_id="task-2",
            content_review_path=_content_review(tmp_path),
            rights_authority=_rights_authority(canonical_ref="article/guide/a-commercial/1"),
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
    review = root / "content_review.json"
    review.write_text('{"decision":"approved"}\n', encoding="utf-8")
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
                                "rightsResult": "passed",
                    "rightsAuthorityRef": "posts/article/work/1/content_review.json",
                    "rightsAuthorityDigest": review_digest,
                    "evidenceRef": "content_review.json",
                    "evidenceDigest": review_digest,
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


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md#gwt-002
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md#req-001

def _versioned_history(root: Path, versions: tuple[int, ...] = (1, 2)) -> None:
    """通过现役 builder/append 构造新契约历史，不刷新已追加的记录。"""
    root.mkdir(parents=True)
    evidence_ref, evidence_digest = _pool_evidence(root)
    identity, _ = _source_identity("version-history-execution")
    attribution = _source_attribution()
    for version in versions:
        manifest = {
            "contentId": "history-content", "version": version,
            "objectRef": "article/history/1", "sourceIdentity": identity,
            "executionId": identity["executionId"],
            "sourceAttribution": attribution,
            "admission": {
                "processResult": "completed", "qualityResult": "passed",
                "rightsResult": "passed",
                "rightsAuthorityRef": "posts/article/history/1/content_review.json",
                "rightsAuthorityDigest": evidence_digest,
                "evidenceRef": evidence_ref, "evidenceDigest": evidence_digest,
            },
        }
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        append_pool_record(object_root=root, record=build_canonical_pool_record(
            object_root=root, object_type="content", object_ref="article/history/1",
        ))


def _allocate_after_history(tmp_path: Path, content_id: str, version: int) -> dict:
    return build_content_pool_fields(
        source_manifest={"contentId": content_id, "version": version, "sourceAttribution": _source_attribution()},
        canonical_ref="article/new/1", source_task_id="new-execution",
        content_review_path=_content_review(tmp_path),
        rights_authority=_rights_authority(canonical_ref="article/new/1"),
        publish_root=tmp_path / "publish", rights_rows=[],
        reserved_identity=_reserved_identity(content_id, version),
    )


@pytest.mark.parametrize("versions", [(1, 2), (1, 1, 2)])
def test_validated_version_history_allows_unrelated_post_without_rewriting_history(
    tmp_path: Path, versions: tuple[int, ...],
) -> None:
    root = tmp_path / "publish/posts/article/history/1"
    _versioned_history(root, versions)
    before = {p.name: p.read_bytes() for p in (root / "records").glob("*.json")}
    assert not read_pool_record_history(root, object_type="content").exclusions
    assert latest_pool_record(root, "content")["contentVersion"] == 2
    assert _allocate_after_history(tmp_path, "unrelated-content", 1)["version"] == 1
    assert _allocate_after_history(tmp_path, "history-content", 3)["version"] == 3
    assert before == {p.name: p.read_bytes() for p in (root / "records").glob("*.json")}


@pytest.mark.parametrize("drift", ["manifest_id", "manifest_version", "historical_id", "historical_ref", "version_rollback"])
def test_version_history_rejects_identity_drift_and_rollback(tmp_path: Path, drift: str) -> None:
    root = tmp_path / "publish/posts/article/history/1"
    _versioned_history(root)
    path = root / ("manifest.json" if drift.startswith("manifest") else "records/1.json")
    row = json.loads(path.read_bytes())
    key, value = {
        "manifest_id": ("contentId", "different-content"),
        "manifest_version": ("version", 3),
        "historical_id": ("objectId", "different-content"),
        "historical_ref": ("objectRef", "article/different/1"),
        "version_rollback": ("contentVersion", 3),
    }[drift]
    row[key] = value
    path.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(ObjectTransactionError, match="DATA.POOL.IDENTITY_INVALID"):
        _allocate_after_history(tmp_path, "unrelated-content", 1)


@pytest.mark.parametrize(("version", "error"), [(1, "VERSION_CONFLICT"), (2, "VERSION_CONFLICT"), (4, "VERSION_GAP")])
def test_version_history_keeps_used_versions_reserved(tmp_path: Path, version: int, error: str) -> None:
    _versioned_history(tmp_path / "publish/posts/article/history/1")
    with pytest.raises(ObjectTransactionError, match=error):
        _allocate_after_history(tmp_path, "history-content", version)


def test_version_history_rejects_duplicate_version_in_another_object(tmp_path: Path) -> None:
    _versioned_history(tmp_path / "publish/posts/article/history/1")
    _versioned_history(tmp_path / "publish/posts/article/duplicate/1", (1,))
    with pytest.raises(ObjectTransactionError, match="content pool contains duplicate versions"):
        _allocate_after_history(tmp_path, "history-content", 3)


def test_version_history_invalid_old_record_cannot_be_hidden_by_current(tmp_path: Path) -> None:
    root = tmp_path / "publish/posts/article/history/1"
    _versioned_history(root)
    path = root / "records/1.json"
    row = json.loads(path.read_bytes())
    row.pop("rightsResult")
    path.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(ObjectTransactionError, match="RECORD_RIGHTS_INVALID"):
        _allocate_after_history(tmp_path, "unrelated-content", 1)


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md#gwt-002
def test_build_scans_version_history_once_but_public_plan_reads_fresh(tmp_path, monkeypatch):
    from collections import Counter
    from content.release.canonical import content_pool_record as pool

    root = tmp_path / "publish/posts/article/history/1"
    _versioned_history(root, (1, 1, 2))
    reads = Counter()
    original = pool._read_json

    def counted(path):
        reads[path] += 1
        return original(path)

    monkeypatch.setattr(pool, "_read_json", counted)
    assert _allocate_after_history(tmp_path, "history-content", 3)["version"] == 3
    assert reads[root / "manifest.json"] == 1
    assert _allocate_after_history(tmp_path, "unrelated-content", 1)["version"] == 1
    assert reads[root / "manifest.json"] == 2
    # 独立 plan 仍严格扫描所有历史，不能沿用上次 build 的身份占用。
    path = root / "records/1.json"
    row = json.loads(path.read_bytes())
    row.pop("rightsResult")
    path.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(ObjectTransactionError, match="RECORD_RIGHTS_INVALID"):
        plan_content_pool_identity(source_manifest={"contentId": "new-content", "version": 1},
            canonical_ref="article/new/1", publish_root=tmp_path / "publish")
