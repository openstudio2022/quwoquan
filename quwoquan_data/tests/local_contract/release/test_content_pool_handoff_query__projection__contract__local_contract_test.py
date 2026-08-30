# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-021.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-021.t5
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-005
"""ContentPoolHandoffQuery is a pure, fail-closed release-consumer projection."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.canonical.content_pool_handoff import (  # noqa: E402
    project_content_pool_handoff,
)
from content.release.canonical.content_pool_record import (  # noqa: E402
    append_pool_record,
    build_canonical_pool_record,
)
from content.release.canonical.environment_release_candidate import (  # noqa: E402
    _candidate,
)
from content.release.canonical.object_source_identity import (  # noqa: E402
    source_identity_digest,
)
from content.release.canonical.object_transaction_contract import (  # noqa: E402
    ObjectTransactionError,
)
from core.io import write_json  # noqa: E402
from core.schema import assert_valid  # noqa: E402
from core.source_digest import (  # noqa: E402
    SourceDefinitionSnapshot,
    content_source_revision,
)

FORBIDDEN_KEYS = {
    "executionId",
    "sourceExecutionId",
    "sourceIdentity",
    "sourceIdentityDigest",
    "provider",
    "model",
    "campaign",
    "campaignId",
    "runId",
    "fence",
}


def _attribution() -> dict[str, object]:
    return {
        "isOriginal": False,
        "originalCreatorName": "source-author",
        "platform": "source-platform",
        "sourcePostUrl": "https://source.example/post",
        "originalAssetUrl": "https://source.example/asset",
        "attributionText": "source-author / source-platform",
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


def _source(execution_id: str) -> tuple[dict[str, object], SourceDefinitionSnapshot]:
    source_digest = "sha256:" + "1" * 64
    entity_catalog_digest = "sha256:" + "2" * 64
    identity: dict[str, object] = {
        "executionId": execution_id,
        "sourceRevision": content_source_revision(
            source_digest=source_digest,
            entity_catalog_digest=entity_catalog_digest,
        ),
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
    }
    identity["identityDigest"] = source_identity_digest(identity)
    return identity, SourceDefinitionSnapshot(source_digest)


def _post(
    publish_root: Path,
    *,
    status: str = "active",
    include_asset: bool = True,
    execution_id: str = "execution-a",
    generator_model: str = "model-a",
) -> tuple[str, Path]:
    post_ref = "article/guide/work-a/1"
    root = publish_root / "posts" / post_ref
    write_json(
        root / "attestation.json",
        {
            "decision": "approved",
            "deterministicGate": {"status": "passed"},
            "independentReviewer": {"status": "passed"},
            "mediaRefReview": {"status": "passed"},
        },
    )
    evidence_digest = "sha256:" + hashlib.sha256(
        (root / "attestation.json").read_bytes()
    ).hexdigest()
    source_identity, source_digest = _source(execution_id)
    write_json(
        root / "manifest.json",
        {
            "schema": "quwoquan_data.post_object",
            "contentId": "content-a",
            "version": 1,
            "sourceType": "data",
            "executionId": execution_id,
            "sourceDigest": source_digest.to_document(),
            "sourceIdentity": source_identity,
            "contentType": "article",
            "generator": "agent",
            "generatorModel": generator_model,
            "authorId": "author-a",
            "entityRefs": ["/entity/地点/景区/实体甲"],
            "variantPurpose": "original",
            "sourceAttribution": _attribution(),
            "admission": {
                "processResult": "completed",
                "qualityResult": "passed",
                "usageScope": "research",
                "evidenceRef": "attestation.json",
                "evidenceDigest": evidence_digest,
            },
            "status": status,
        },
    )
    write_json(root / "creator.refs.json", {"creatorRefs": ["author-a"]})
    write_json(root / "tag.refs.json", {"tagRefs": []})
    if include_asset:
        digest = "a" * 64
        write_json(
            root / "asset.refs.json",
            {
                "assets": [
                    {
                        "assetId": "asset-a",
                        "objectKey": f"media/objects/sha256/aa/aa/{digest}.jpg",
                        "sha256": f"sha256:{digest}",
                    }
                ]
            },
        )
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        manifest["assetRefsRef"] = "asset.refs.json"
        write_json(root / "manifest.json", manifest)
    append_pool_record(
        object_root=root,
        record=build_canonical_pool_record(
            object_root=root,
            object_type="content",
            object_ref=post_ref,
        ),
    )
    return post_ref, root


def _keys(node: object) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {key for value in node.values() for key in _keys(value)}
    if isinstance(node, list):
        return {key for value in node for key in _keys(value)}
    return set()


def _fingerprint(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_projector_is_pure_and_schema_whitelisted__local_contract(tmp_path: Path) -> None:
    publish_root = tmp_path / "publish"
    post_ref, _root = _post(publish_root)
    before = _fingerprint(publish_root)

    first = project_content_pool_handoff(
        publish_root=publish_root,
        object_type="content",
        object_ref=post_ref,
    )
    second = project_content_pool_handoff(
        publish_root=publish_root,
        object_type="content",
        object_ref=post_ref,
    )

    assert first is not None and second is not None
    document = first.as_document()
    assert document == second.as_document()
    assert_valid(document, "release", "content_pool_handoff_query")
    assert _keys(document).isdisjoint(FORBIDDEN_KEYS)
    assert _fingerprint(publish_root) == before
    assert document["contentLibrary"]["holder"] == "content_library"


def test_retired_and_deleted_objects_are_excluded__local_contract(tmp_path: Path) -> None:
    for status in ("retired", "deleted"):
        publish_root = tmp_path / status / "publish"
        post_ref, _root = _post(publish_root, status=status)
        assert project_content_pool_handoff(
            publish_root=publish_root,
            object_type="content",
            object_ref=post_ref,
        ) is None


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("identity", "DATA.POOL.PAYLOAD_DIGEST_DRIFT"),
        ("digest", "DATA.POOL.CANONICAL_DIGEST_DRIFT"),
        ("admission", "DATA.POOL.ELIGIBILITY_FAILED"),
    ],
)
def test_missing_identity_digest_or_admission_fails_closed__local_contract(
    tmp_path: Path,
    mutation: str,
    code: str,
) -> None:
    publish_root = tmp_path / mutation / "publish"
    post_ref, root = _post(publish_root)
    record_path = root / "_pool/versions/1.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if mutation == "identity":
        manifest["contentId"] = ""
        write_json(manifest_path, manifest)
        record["payloadDigest"] = record["canonicalObjectDigest"] = (
            "sha256:" + "b" * 64
        )
        # Bypass owner validation only to isolate the consumer fail-closed check.
        write_json(record_path, record)
    elif mutation == "digest":
        record["canonicalObjectDigest"] = ""
        write_json(record_path, record)
    else:
        record["eligibilityResult"] = "failed"
        record["usageScope"] = None
        write_json(record_path, record)
    with pytest.raises(ObjectTransactionError, match=code):
        project_content_pool_handoff(
            publish_root=publish_root,
            object_type="content",
            object_ref=post_ref,
        )


def test_producer_only_metadata_does_not_change_selection_identity__local_contract(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first/publish"
    second_root = tmp_path / "second/publish"
    first_ref, _first_object = _post(
        first_root,
        execution_id="execution-a",
        generator_model="model-a",
    )
    second_ref, second_object = _post(
        second_root,
        execution_id="execution-b",
        generator_model="model-b",
    )
    # Re-seal the second owner facts so only producer lineage differs.
    second_record = json.loads(
        (second_object / "_pool/versions/1.json").read_text(encoding="utf-8")
    )
    second_record["canonicalObjectDigest"] = second_record["payloadDigest"]
    write_json(second_object / "_pool/versions/1.json", second_record)

    first = project_content_pool_handoff(
        publish_root=first_root,
        object_type="content",
        object_ref=first_ref,
    )
    second = project_content_pool_handoff(
        publish_root=second_root,
        object_type="content",
        object_ref=second_ref,
    )
    assert first is not None and second is not None
    assert first.selection_identity_digest == second.selection_identity_digest
    first_candidate = _candidate(first_root, first_ref, strict_admission=True)
    second_candidate = _candidate(second_root, second_ref, strict_admission=True)
    assert first_candidate is not None and second_candidate is not None
    assert first_candidate.selection_identity_digest == (
        second_candidate.selection_identity_digest
    )



def test_schema_rejects_producer_identity_fields__local_contract(tmp_path: Path) -> None:
    publish_root = tmp_path / "publish"
    post_ref, _root = _post(publish_root)
    handoff = project_content_pool_handoff(
        publish_root=publish_root,
        object_type="content",
        object_ref=post_ref,
    )
    assert handoff is not None
    document = copy.deepcopy(handoff.as_document())
    document["identity"]["executionId"] = "forbidden"
    with pytest.raises(ValueError, match="executionId"):
        assert_valid(document, "release", "content_pool_handoff_query")
