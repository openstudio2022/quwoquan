# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-005.t4
"""The raw append path refuses objects a compiled WorkRequest already owns."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

DATA_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(DATA_SCRIPTS))

from content.release.canonical.object_source_identity import (  # noqa: E402
    source_identity_digest,
)
from content.release.canonical.object_transaction_contract import (  # noqa: E402
    ObjectTransactionError,
)
from content.release.canonical.pool_append import (  # noqa: E402
    BATCH_SCHEMA,
    append_pool_batch,
)
from content.release.canonical.pool_append_admission import (  # noqa: E402
    work_request_driven_execution_ids,
)
from core.io import write_json  # noqa: E402
from core.source_digest import content_source_revision  # noqa: E402

_DRIVEN_EXECUTION_ID = "20260827--travel-homepage-coverage--sichuan--pilot-001"
_HISTORIC_EXECUTION_ID = "travel-workload-homepage--scale-003"


def _source_identity(execution_id: str) -> dict[str, str]:
    source_digest = "sha256:" + "2" * 64
    entity_catalog_digest = "sha256:" + "3" * 64
    identity = {
        "executionId": execution_id,
        "sourceRevision": content_source_revision(
            source_digest=source_digest,
            entity_catalog_digest=entity_catalog_digest,
        ),
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
    }
    return {**identity, "identityDigest": source_identity_digest(identity)}


def _source_attribution() -> dict[str, object]:
    return {
        "isOriginal": False,
        "originalCreatorName": "Source Author",
        "platform": "source-platform",
        "sourcePostUrl": "https://source.example/post",
        "originalAssetUrl": "https://source.example/asset",
        "attributionText": "Source Author / source-platform",
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


def _batch_file(tmp_path: Path, *, execution_id: str) -> Path:
    digest = "sha256:" + hashlib.sha256(execution_id.encode("utf-8")).hexdigest()
    path = tmp_path / "batch.json"
    write_json(
        path,
        {
            "schema": BATCH_SCHEMA,
            "appendSetId": "canonical-evidence-backfill",
            "items": [
                {
                    "itemId": "content-1",
                    "sourceRef": "posts/article/work-1/1",
                    "record": {
                        "schema": "quwoquan_data.pool_object_record",
                        "objectType": "content",
                        "objectId": "content-1",
                        "objectRef": "article/work-1/1",
                        "recordSequence": 1,
                        "contentVersion": 1,
                        "status": "active",
                        "processResult": "completed",
                        "qualityResult": "passed",
                        "eligibilityResult": "passed",
                        "usageScope": "research",
                        "evidenceRef": "attestation.json",
                        "evidenceDigest": digest,
                        "payloadDigest": digest,
                        "canonicalObjectDigest": digest,
                        "sourceIdentity": _source_identity(execution_id),
                        "sourceAttribution": _source_attribution(),
                    },
                }
            ],
        },
    )
    return path


def _compile_package(root: Path, *, execution_id: str) -> None:
    write_json(
        root / "workspace/content-campaign-envelopes/travel/M1/sichuan/sequence-001"
        / "work-request.json",
        {
            "workRequestId": "wr-000000000000000000000001",
            "carrierEnvelopes": [
                {
                    "carrier": "homepage",
                    "executionId": execution_id,
                    "envelopeRef": "homepage.json",
                    "requestDigest": "sha256:" + "4" * 64,
                }
            ],
        },
    )


def test_object_of_a_compiled_work_request_is_refused_by_the_raw_append_path(
    tmp_path: Path,
) -> None:
    envelope_root = tmp_path / "local"
    _compile_package(envelope_root, execution_id=_DRIVEN_EXECUTION_ID)
    batch = _batch_file(tmp_path, execution_id=_DRIVEN_EXECUTION_ID)

    with pytest.raises(ObjectTransactionError) as excinfo:
        append_pool_batch(
            input_path=batch,
            publish_root=tmp_path / "publish",
            apply=False,
            envelope_output_root=envelope_root,
        )

    message = str(excinfo.value)
    assert "DATA.POOL.DELIVERY_INTENT_REQUIRED" in message
    # 判否要点名是哪个 execution 与哪份 WorkRequest，否则运营者读到终态仍不知道
    # 该去哪条链路重入。
    assert _DRIVEN_EXECUTION_ID in message
    assert "wr-000000000000000000000001" in message
    assert not (tmp_path / "publish").exists()


def test_preflight_refuses_before_apply_rather_than_only_at_write_time(
    tmp_path: Path,
) -> None:
    envelope_root = tmp_path / "local"
    _compile_package(envelope_root, execution_id=_DRIVEN_EXECUTION_ID)
    batch = _batch_file(tmp_path, execution_id=_DRIVEN_EXECUTION_ID)

    for apply in (False, True):
        with pytest.raises(ObjectTransactionError, match="DELIVERY_INTENT_REQUIRED"):
            append_pool_batch(
                input_path=batch,
                publish_root=tmp_path / "publish",
                apply=apply,
                envelope_output_root=envelope_root,
            )


def test_pre_receipt_protocol_object_still_reaches_the_backfill_path(
    tmp_path: Path,
) -> None:
    # 历史对象没有任何 WorkRequest 声明它，本判据必须放行它继续走既有身份判据，
    # 否则 receipt 协议之前入池的对象连诊断都做不了。
    envelope_root = tmp_path / "local"
    _compile_package(envelope_root, execution_id=_DRIVEN_EXECUTION_ID)
    batch = _batch_file(tmp_path, execution_id=_HISTORIC_EXECUTION_ID)

    report = append_pool_batch(
        input_path=batch,
        publish_root=tmp_path / "publish",
        apply=False,
        envelope_output_root=envelope_root,
    )

    codes = {str(row["code"]) for row in report["reasons"]}
    # 该对象被交回既有对象证据判据（此处 fixture 未落 manifest），
    # 而不是被入池路径判据挡在门外。
    assert "DATA.POOL.DELIVERY_INTENT_REQUIRED" not in codes
    assert codes and all("manifest.json" in code for code in codes)


def test_absent_envelope_root_is_absence_not_a_blanket_refusal(
    tmp_path: Path,
) -> None:
    assert work_request_driven_execution_ids(output_root=tmp_path / "missing") == {}


def test_incomplete_compile_package_is_typed_rather_than_silently_skipped(
    tmp_path: Path,
) -> None:
    envelope_root = tmp_path / "local"
    write_json(
        envelope_root
        / "workspace/content-campaign-envelopes/travel/M1/sichuan/sequence-001"
        / "work-request.json",
        {"workRequestId": "wr-000000000000000000000001"},
    )

    with pytest.raises(ObjectTransactionError, match="WORK_REQUEST_PACKAGE_INVALID"):
        work_request_driven_execution_ids(output_root=envelope_root)
