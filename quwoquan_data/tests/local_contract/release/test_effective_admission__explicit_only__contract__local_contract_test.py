from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

DATA_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(DATA_SCRIPTS))

from content.release.canonical.content_pool_record import (  # noqa: E402
    is_pool_record_admitted,
    pool_payload_digest,
)
from content.release.canonical.object_source_identity import (  # noqa: E402
    source_identity_digest,
)
from content.release.canonical.effective_admission import (  # noqa: E402
    EffectiveAdmission,
    effective_source_attribution_ready,
    resolve_effective_admission,
)
from content.release.canonical.object_transaction_contract import (  # noqa: E402
    ObjectTransactionError,
)
from core.io import write_json  # noqa: E402


def _attribution() -> dict[str, object]:
    return {
        "isOriginal": False,
        "originalCreatorName": "历史作者",
        "platform": "Wikimedia Commons",
        "sourcePostUrl": "https://commons.wikimedia.org/wiki/File:history.jpg",
        "originalAssetUrl": "https://upload.wikimedia.org/history.jpg",
        "attributionText": "历史作者 / Wikimedia Commons",
        "rightsBasis": "CC BY-SA 4.0",
        "commercialAuthorizationStatus": "verified",
        "publicationAdmission": "commercial_release",
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-08-01T00:00:00Z",
        "takedownPolicy": "remove on substantiated request",
        "authorizationProofUrl": "https://commons.wikimedia.org/wiki/File:history.jpg",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
    }


def _post_manifest() -> dict[str, object]:
    return {
        "contentId": "content-history",
        "version": 1,
        "executionId": "execution-history",
        "contentType": "article",
        "authorId": "author-history",
        "status": "active",
        "reviewDecision": "approved",
        "entityRefs": ["/entity/地点/景区/历史实体"],
    }


def _write_post(
    publish: Path,
    *,
    pool_record_overrides: dict[str, object] | None = None,
    with_sidecar: bool = True,
) -> tuple[Path, dict[str, object]]:
    root = publish / "posts/article/history/1"
    manifest = _post_manifest()
    write_json(root / "manifest.json", manifest)
    attestation = {
        "schema": "quwoquan_data.review_attestation",
        "executionId": "execution-history",
        "decision": "approved",
        "deterministicGate": {"status": "passed", "issues": []},
        "independentReviewer": {"status": "passed"},
        "mediaRefReview": {"status": "passed", "issues": []},
    }
    write_json(root / "attestation.json", attestation)
    if not with_sidecar:
        return root, manifest
    attestation_sha = (
        "sha256:"
        + hashlib.sha256((root / "attestation.json").read_bytes()).hexdigest()
    )
    payload_digest = pool_payload_digest(root)
    identity = {
        "executionId": "execution-history",
        "sourceRevision": "sha256:" + "4" * 64,
        "sourceDigest": "sha256:" + "5" * 64,
        "entityCatalogDigest": "sha256:" + "6" * 64,
    }
    record: dict[str, object] = {
        "schema": "quwoquan_data.pool_object_record",
        "objectType": "content",
        "objectId": "content-history",
        "objectRef": "article/history/1",
        "recordSequence": 1,
        "contentVersion": 1,
        "status": "active",
        "processResult": "completed",
        "qualityResult": "passed",
        "eligibilityResult": "passed",
        "usageScope": "research",
        "evidenceRef": "attestation.json",
        "evidenceDigest": attestation_sha,
        "payloadDigest": payload_digest,
        "canonicalObjectDigest": payload_digest,
        "sourceIdentity": {
            **identity,
            "identityDigest": source_identity_digest(identity),
        },
        "sourceAttribution": _attribution(),
    }
    record.update(pool_record_overrides or {})
    write_json(root / "_pool/versions/1.json", record)
    return root, manifest


def test_pre_sequence_sidecar_shape_fails_closed(tmp_path: Path) -> None:
    """Records without an explicit recordSequence are rejected, never inferred."""

    root, manifest = _write_post(
        tmp_path / "publish",
        pool_record_overrides={"version": 1},
    )
    record_path = root / "_pool/versions/1.json"
    import json as json_module

    document = json_module.loads(record_path.read_text(encoding="utf-8"))
    document.pop("recordSequence")
    document.pop("contentVersion")
    write_json(record_path, document)

    with pytest.raises(ObjectTransactionError, match="RECORD_SEQUENCE_MISSING"):
        resolve_effective_admission(
            root,
            object_type="content",
            document=manifest,
        )


def test_explicit_record_is_the_only_admission_truth(tmp_path: Path) -> None:
    root, manifest = _write_post(tmp_path / "publish")

    effective = resolve_effective_admission(
        root,
        object_type="content",
        document=manifest,
    )

    assert effective.source == "explicit"
    assert effective.record is not None
    assert is_pool_record_admitted(effective.record)
    assert effective.record["usageScope"] == "research"


def test_missing_record_yields_no_inferred_admission(tmp_path: Path) -> None:
    root, manifest = _write_post(
        tmp_path / "publish",
        with_sidecar=False,
    )

    effective = resolve_effective_admission(
        root,
        object_type="content",
        document=manifest,
    )

    assert effective.source == "missing"
    assert effective.record is None


def test_attribution_gate_requires_complete_attribution() -> None:
    complete = EffectiveAdmission(
        record={"usageScope": "research", "sourceAttribution": _attribution()},
        source="explicit",
    )
    incomplete = EffectiveAdmission(
        record={"usageScope": "research", "sourceAttribution": {}},
        source="explicit",
    )

    assert effective_source_attribution_ready(complete)
    assert not effective_source_attribution_ready(incomplete)
