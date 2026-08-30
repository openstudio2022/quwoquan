# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-003
"""Content operation views are deterministic queries over explicit owner facts."""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
from pathlib import Path

import pytest

from content.execution.operation_views import (
    ProjectionContractError,
    project_content_item_version_view,
    project_content_production_task_view,
)
from content.execution.planning.work_request_dependencies import canonical_digest
from content.release.canonical.object_source_identity import source_identity_digest
from core.schema import load_schema, validate_strict

EXECUTION_ID = "20260829--family-article-projection--region--pilot-001"


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _binding(ref: str, fact: dict[str, object]) -> dict[str, object]:
    return {"ref": ref, "digest": _digest(fact), "fact": fact}


def _work_request() -> dict[str, object]:
    dependencies = {"source": {"ref": "source.json", "digest": _digest("source")}}
    stable: dict[str, object] = {
        "schema": "quwoquan_data.work_request",
        "requestDigest": _digest("request"),
        "status": "compiled",
        "intent": {
            "vertical": "family",
            "regionRef": "Region/test",
            "scopeType": "region",
            "primaryTopicRef": None,
            "relatedTopicRefs": [],
        },
        "lifecycle": "research",
        "executionMode": "fresh",
        "scale": "M1",
        "workloadMode": "explicit",
        "activeCarriers": ["article"],
        "workloads": {"article": 1},
        "carrierPolicyRef": "policy/carrier.json",
        "carrierPolicyDigest": _digest("policy"),
        "rootExecutionId": EXECUTION_ID,
        "sourceRevision": _digest("revision"),
        "sourceDigest": _digest("source-def"),
        "entityCatalogDigest": _digest("entity-catalog"),
        "sourcePool": {
            "poolId": "pool-projection",
            "targetScale": "WORKLOAD",
            "planRef": "source-pool-plan.json",
            "planDigest": _digest("source-pool-plan"),
            "evidenceRootRef": "evidence/source-pool",
        },
        "dependencies": dependencies,
        "dependencySetDigest": canonical_digest(dependencies),
        "carrierEnvelopes": [
            {
                "carrier": "article",
                "executionId": EXECUTION_ID,
                "envelopeRef": "execution-envelope.json",
                "requestDigest": _digest("request"),
            }
        ],
        "retention": {
            "archiveAfterDays": 30,
            "deleteAfterDays": 90,
            "tombstoneRequired": True,
        },
    }
    work_request_digest = canonical_digest(stable)
    return {
        **stable,
        "workRequestId": f"wr-{work_request_digest[7:31]}",
        "workRequestDigest": work_request_digest,
        "compiledAt": "2026-08-29T00:00:00Z",
    }


def _execution_state(status: str = "succeeded") -> dict[str, object]:
    return {
        "schema": "quwoquan.content.execution_state",
        "executionId": EXECUTION_ID,
        "completed": [],
        "status": status,
        "updatedAt": "2026-08-29T00:00:00Z",
    }


def _receipts(*, through: str = "ship") -> list[dict[str, object]]:
    stages = [
        "0.plan",
        "sources",
        "1.download",
        "2.quality",
        "3.compose",
        "4.draft",
        "5.review",
        "publish",
        "release",
        "ship",
    ]
    end = stages.index(through) + 1
    rows: list[dict[str, object]] = []
    for index, stage in enumerate(stages[:end]):
        next_stage = "END" if stage == "ship" else stages[index + 1]
        rows.append(
            {
                "schema": "quwoquan_data.stage_receipt",
                "executionId": EXECUTION_ID,
                "stage": stage,
                "sequence": index + 1,
                "verdict": "pass",
                "actor": {
                    "host": "cursor",
                    "modelFamily": "gpt",
                    "sessionId": "session-projection",
                },
                "artifacts": [f"{stage}/result.json"],
                "openItems": [],
                "next": next_stage,
                "evidence": {
                    "commands": [{"command": "verify projection", "exitCode": 0}],
                    "issueCount": 0,
                    "repairRounds": 0,
                },
                "recordedAt": f"2026-08-29T00:{index:02d}:00Z",
            }
        )
    return rows


def _task_owner_refs(*, shipped: str = "passed") -> dict[str, object]:
    facts = {
        "productionReady": {
            "schema": "quwoquan_data.production_ready_fact",
            "executionId": EXECUTION_ID,
            "verdict": "passed",
        },
        "published": {
            "schema": "quwoquan_data.content_publish_fact",
            "executionId": EXECUTION_ID,
            "verdict": "passed",
        },
        "released": {
            "schema": "quwoquan_data.content_release_fact",
            "executionId": EXECUTION_ID,
            "verdict": "passed",
        },
        "shipped": {
            "schema": "quwoquan_data.content_ship_fact",
            "executionId": EXECUTION_ID,
            "verdict": shipped,
        },
    }
    return {name: _binding(f"facts/{name}.json", fact) for name, fact in facts.items()}


def _source_identity() -> dict[str, str]:
    identity = {
        "executionId": EXECUTION_ID,
        "sourceRevision": _digest("revision"),
        "sourceDigest": _digest("source"),
        "entityCatalogDigest": _digest("entity-catalog"),
    }
    return {**identity, "identityDigest": source_identity_digest(identity)}


def _source_attribution() -> dict[str, object]:
    return {
        "isOriginal": True,
        "originalCreatorName": "Projection Author",
        "platform": "quwoquan",
        "sourcePostUrl": "https://example.test/post",
        "originalAssetUrl": "https://example.test/asset",
        "attributionText": "Projection Author / quwoquan",
        "rightsBasis": "original",
        "commercialAuthorizationStatus": "verified",
        "publicationAdmission": "research_release",
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-08-29T00:00:00Z",
        "takedownPolicy": "remove on substantiated request",
        "derivedModifications": [],
    }


def _pool_record() -> dict[str, object]:
    payload_digest = _digest("payload")
    return {
        "schema": "quwoquan_data.pool_object_record",
        "objectType": "content",
        "objectId": "content-projection-001",
        "objectRef": "article/projection/content-projection-001/1",
        "recordSequence": 3,
        "contentVersion": 1,
        "status": "active",
        "processResult": "completed",
        "qualityResult": "passed",
        "eligibilityResult": "passed",
        "usageScope": "research",
        "evidenceRef": "evidence/review.json",
        "evidenceDigest": _digest("review"),
        "payloadDigest": payload_digest,
        "canonicalObjectDigest": payload_digest,
        "sourceIdentity": _source_identity(),
        "sourceAttribution": _source_attribution(),
    }


def _item_inputs() -> dict[str, object]:
    record = _pool_record()
    identity = {
        "objectId": record["objectId"],
        "contentVersion": record["contentVersion"],
        "payloadDigest": record["payloadDigest"],
    }
    library_fact = {
        "schema": "quwoquan_data.content_library_version_fact",
        **identity,
        "holder": "content_library",
        "mediaRefs": [
            {
                "assetId": "asset-b",
                "ref": "content-library/media/b",
                "digest": _digest("media-b"),
            },
            {
                "assetId": "asset-a",
                "ref": "content-library/media/a",
                "digest": _digest("media-a"),
            },
        ],
    }
    source_fact = {
        "schema": "quwoquan_data.content_source_fact",
        "executionId": EXECUTION_ID,
        "identityDigest": record["sourceIdentity"]["identityDigest"],
    }
    publish_fact = {
        "schema": "quwoquan_data.content_publish_fact",
        **identity,
        "verdict": "passed",
    }
    release_fact = {
        "schema": "quwoquan_data.release_content_fact",
        "releaseId": "release-projection-001",
        **identity,
        "verdict": "included",
    }
    return {
        "pool_record": record,
        "content_library_ref": _binding("library/content-projection-001.json", library_fact),
        "source_ref": _binding("sources/content-projection-001.json", source_fact),
        "publish_ref": _binding("publish/content-projection-001.json", publish_fact),
        "release_refs": [_binding("releases/release-projection-001.json", release_fact)],
    }


def _tree_snapshot(root: Path) -> tuple[str, ...]:
    return tuple(
        f"{path.relative_to(root).as_posix()}:{hashlib.sha256(path.read_bytes()).hexdigest()}"
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def test_task_projection_is_deterministic_and_does_not_write_disk(tmp_path: Path) -> None:
    marker = tmp_path / "owner-facts.json"
    marker.write_text('{"immutable":true}\n', encoding="utf-8")
    before = _tree_snapshot(tmp_path)
    inputs = {
        "work_request": _work_request(),
        "execution_state": _execution_state(),
        "stage_receipts": _receipts(),
        "owner_evidence_refs": _task_owner_refs(),
    }
    frozen = copy.deepcopy(inputs)

    first = project_content_production_task_view(**inputs)
    second = project_content_production_task_view(**copy.deepcopy(inputs))

    assert first == second
    assert inputs == frozen
    assert _tree_snapshot(tmp_path) == before
    assert first["terminal"] == "succeeded"
    assert first["currentStage"] == "END"
    assert first["shipped"] is True


def test_non_ship_stage_cannot_project_succeeded() -> None:
    refs = _task_owner_refs(shipped="not_observed")
    with pytest.raises(ProjectionContractError, match="ship pass END"):
        project_content_production_task_view(
            work_request=_work_request(),
            execution_state=_execution_state("succeeded"),
            stage_receipts=_receipts(through="release"),
            owner_evidence_refs=refs,
        )


def test_task_projection_fails_closed_for_missing_owner_fact_and_digest_drift() -> None:
    refs = _task_owner_refs()
    refs.pop("released")
    with pytest.raises(ProjectionContractError, match=r"missing=\['released'\]"):
        project_content_production_task_view(
            work_request=_work_request(),
            execution_state=_execution_state(),
            stage_receipts=_receipts(),
            owner_evidence_refs=refs,
        )

    drifted = _task_owner_refs()
    drifted["shipped"]["fact"]["verdict"] = "failed"
    with pytest.raises(ProjectionContractError, match="digest mismatch"):
        project_content_production_task_view(
            work_request=_work_request(),
            execution_state=_execution_state(),
            stage_receipts=_receipts(),
            owner_evidence_refs=drifted,
        )


def test_item_projection_is_deterministic_ref_only_and_content_library_held(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "library-index.json"
    marker.write_text('{"holder":"content_library"}\n', encoding="utf-8")
    before = _tree_snapshot(tmp_path)
    inputs = _item_inputs()
    frozen = copy.deepcopy(inputs)

    first = project_content_item_version_view(**inputs)
    second = project_content_item_version_view(**copy.deepcopy(inputs))

    assert first == second
    assert inputs == frozen
    assert _tree_snapshot(tmp_path) == before
    assert first["holder"] == "content_library"
    assert first["usageScope"] == "research"
    assert first["delivery"]["media"] == sorted(
        first["delivery"]["media"], key=lambda row: row["assetId"]
    )
    encoded = json.dumps(first, sort_keys=True).lower()
    assert "bytes" not in encoded
    assert "body" not in encoded
    assert set(first["delivery"]["media"][0]) == {"assetId", "ref", "digest"}


def test_item_projection_fails_closed_for_unknown_key_identity_and_holder_drift() -> None:
    unknown = _item_inputs()
    unknown["pool_record"]["unknown"] = True
    with pytest.raises(ProjectionContractError, match="未知字段 'unknown'"):
        project_content_item_version_view(**unknown)

    identity = _item_inputs()
    identity["publish_ref"]["fact"]["objectId"] = "different-content"
    identity["publish_ref"]["digest"] = _digest(identity["publish_ref"]["fact"])
    with pytest.raises(ProjectionContractError, match="identity or digest mismatch"):
        project_content_item_version_view(**identity)

    holder = _item_inputs()
    holder["content_library_ref"]["fact"]["holder"] = "release"
    holder["content_library_ref"]["digest"] = _digest(
        holder["content_library_ref"]["fact"]
    )
    with pytest.raises(ProjectionContractError, match="holder mismatch"):
        project_content_item_version_view(**holder)

    unknown_schema = _item_inputs()
    unknown_schema["source_ref"]["fact"]["schema"] = "unknown.source.fact"
    unknown_schema["source_ref"]["digest"] = _digest(
        unknown_schema["source_ref"]["fact"]
    )
    with pytest.raises(ProjectionContractError, match="schema mismatch"):
        project_content_item_version_view(**unknown_schema)


def test_projection_api_and_schemas_expose_queries_only() -> None:
    import content.execution.operation_views as module

    public = {
        name
        for name, value in inspect.getmembers(module)
        if not name.startswith("_") and inspect.isfunction(value)
    }
    assert public == {
        "project_content_item_version_view",
        "project_content_production_task_view",
    }
    forbidden = ("save", "command", "repository", "checkpoint")
    assert not any(token in name.lower() for token in forbidden for name in public)
    source = inspect.getsource(module).lower()
    assert "path(" not in source
    assert ".open(" not in source
    assert "write_text(" not in source
    assert "write_bytes(" not in source

    for command, name in (
        ("execution", "content_production_task_view"),
        ("release", "content_item_version_view"),
    ):
        schema = load_schema(command, name)
        assert schema["additionalProperties"] is False
        assert schema["x-spec-ref"].endswith("#sit-003")
        unknown = {field: None for field in schema["required"]}
        unknown["unknown"] = True
        assert any("未知字段 'unknown'" in issue for issue in validate_strict(unknown, schema))
