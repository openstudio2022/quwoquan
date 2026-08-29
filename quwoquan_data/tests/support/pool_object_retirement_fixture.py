"""One canonical pool carrying a pre-receipt historical object next to an admissible one.

退役路径的两级证据（local_contract 直调、api_integration 走真实命令面）必须站在同一
个池形态上，否则两级的「计数不变」说的不是同一件事。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from content.release.canonical.content_pool_record import (  # noqa: E402
    append_pool_record,
    build_canonical_pool_record,
)
from content.release.canonical.object_source_identity import (  # noqa: E402
    source_identity_digest,
)
from core.io import write_json  # noqa: E402
from core.source_digest import (  # noqa: E402
    SourceDefinitionSnapshot,
    content_source_revision,
)

HISTORICAL_GENERATOR = "image_evidence_pack"
HISTORICAL_OBJECT_REF = "image/historical/1"
ADMISSIBLE_OBJECT_REF = "image/ready/1"


def source_attribution() -> dict[str, object]:
    return {
        "isOriginal": False,
        "originalCreatorName": "来源作者",
        "platform": "source-platform",
        "sourcePostUrl": "https://source.example/post",
        "originalAssetUrl": "https://source.example/asset.jpg",
        "attributionText": "来源作者 / source-platform",
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
        "derivedModifications": [],
    }


def _source_identity(
    execution_id: str,
) -> tuple[dict[str, object], SourceDefinitionSnapshot]:
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


def _rebind_evidence_digest(root: Path) -> None:
    """Bind ``admission.evidenceDigest`` to the attestation bytes actually written."""

    write_json(
        root / "attestation.json",
        {
            "schema": "quwoquan_data.review_attestation",
            "decision": "approved",
            "deterministicGate": {"status": "passed", "issues": []},
            "independentReviewer": {"status": "passed"},
            "mediaRefReview": {"status": "passed", "issues": []},
        },
    )
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["admission"]["evidenceDigest"] = (
        "sha256:" + hashlib.sha256((root / "attestation.json").read_bytes()).hexdigest()
    )
    write_json(manifest_path, manifest)


def author(publish: Path) -> None:
    write_json(
        publish / "creators/author-a/profile.json",
        {
            "authorId": "author-a",
            "version": 1,
            "status": "active",
            "admission": {
                "processResult": "completed",
                "qualityResult": "passed",
                "evidenceRef": "evidence.json",
                "evidenceDigest": "sha256:" + "a" * 64,
            },
        },
    )


def homepage(publish: Path, name: str = "实体甲") -> Path:
    root = publish / f"entities/地点/景区/{name}"
    identity, source_digest = _source_identity("execution-a")
    write_json(
        root / "manifest.json",
        {
            "schema": "quwoquan_data.entity_manifest",
            "entityId": f"entity-{name}",
            "entityRef": f"/entity/地点/景区/{name}",
            "executionId": "execution-a",
            "sourceDigest": source_digest.to_document(),
            "sourceIdentity": identity,
            "sourceAttribution": source_attribution(),
            "version": 1,
            "status": "active",
            "admission": {
                "processResult": "completed",
                "qualityResult": "passed",
                "usageScope": "research",
                "evidenceRef": "attestation.json",
                "evidenceDigest": "sha256:" + "b" * 64,
            },
        },
    )
    write_json(root / "creator.refs.json", {"creatorRefs": ["author-a"]})
    _rebind_evidence_digest(root)
    append_pool_record(
        object_root=root,
        record=build_canonical_pool_record(
            object_root=root,
            object_type="homepage",
            object_ref=root.relative_to(publish / "entities").as_posix(),
        ),
    )
    return root


def post(
    publish: Path,
    *,
    carrier: str,
    work: str,
    generator: str = "agent",
) -> Path:
    root = publish / "posts" / carrier / work / "1"
    identity, source_digest = _source_identity("execution-a")
    write_json(
        root / "manifest.json",
        {
            "contentId": f"content-{work}",
            "version": 1,
            "executionId": "execution-a",
            "sourceTaskId": "execution-a",
            "sourceDigest": source_digest.to_document(),
            "sourceIdentity": identity,
            "contentType": carrier,
            "generator": generator,
            "authorId": "author-a",
            "status": "active",
            "entityRefs": ["/entity/地点/景区/实体甲"],
            "sourceAttribution": source_attribution(),
            "admission": {
                "processResult": "completed",
                "qualityResult": "passed",
                "usageScope": "research",
                "evidenceRef": "attestation.json",
                "evidenceDigest": "sha256:" + "c" * 64,
            },
        },
    )
    write_json(root / "creator.refs.json", {"creatorRefs": ["author-a"]})
    _rebind_evidence_digest(root)
    append_pool_record(
        object_root=root,
        record=build_canonical_pool_record(
            object_root=root,
            object_type="content",
            object_ref=root.relative_to(publish / "posts").as_posix(),
        ),
    )
    return root


def pool_with_one_historical_object(publish: Path) -> Path:
    """One admissible object plus one pre-receipt object with a historical generator."""

    author(publish)
    homepage(publish)
    post(publish, carrier="image", work="ready")
    return post(
        publish,
        carrier="image",
        work="historical",
        generator=HISTORICAL_GENERATOR,
    )


__all__ = [
    "ADMISSIBLE_OBJECT_REF",
    "HISTORICAL_GENERATOR",
    "HISTORICAL_OBJECT_REF",
    "author",
    "homepage",
    "pool_with_one_historical_object",
    "post",
    "source_attribution",
]
