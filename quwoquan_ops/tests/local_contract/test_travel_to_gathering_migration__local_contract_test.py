"""M6 travel-service -> Gathering target-only 迁移控制面契约。

spec_ref: specs/feature-tree/travel-journey/spec.md#dom-001
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import pytest

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.common import load_json_yaml
from quwoquan_ops.migrations.travel_to_gathering import control_plane

ROOT = Path(__file__).resolve().parents[3]
TIMESTAMP = "2026-08-06T00:00:00Z"
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64


def _target_contract() -> control_plane.TargetContractBinding:
    fields = load_json_yaml(
        ROOT
        / "quwoquan_service/services/circle-service/contracts"
        / "circle_management/gathering/fields.yaml"
    )
    plan_fields = load_json_yaml(
        ROOT
        / "quwoquan_service/services/circle-service/contracts"
        / "circle_management/gathering_plan/fields.yaml"
    )
    assert isinstance(fields, dict) and isinstance(plan_fields, dict)
    return control_plane.TargetContractBinding(
        digest=DIGEST_A,
        graph_digest=DIGEST_B,
        generated_artifact_digest=DIGEST_C,
        sources=(
            {
                "path": "circle/circle_management/gathering/fields.yaml",
                "sha256": "d" * 64,
            },
        ),
        fields_contract=fields,
        plan_fields_contract=plan_fields,
        object_ids=control_plane.CANONICAL_TARGET_OBJECT_IDS,
        operation_ids=control_plane.REQUIRED_TARGET_OPERATION_IDS,
    )


def _empty_objects() -> dict[str, list[dict[str, object]]]:
    return {object_type: [] for object_type in control_plane.SOURCE_OBJECT_TYPES}


def _source_snapshot() -> dict[str, object]:
    objects = _empty_objects()
    objects["TripPlan"] = [
        {
            "_id": "trip-1",
            "version": 3,
            "organizerPersonaId": "persona-host",
            "title": "周末城市漫步",
            "status": "active",
            "startAt": "2026-08-08T01:00:00Z",
            "endAt": "2026-08-08T05:00:00Z",
            "sourceTemplateId": None,
            "sourceTemplateVersion": None,
            "sourceAttributionIds": [],
            "sourceAttributionPersonaIds": [],
            "sourcePostIds": ["post-plan-source"],
            "sourceAttributions": [],
            "currentRevisionId": "revision-1",
            "currentRevisionNumber": 1,
            "currentItemCount": 1,
            "createdAt": TIMESTAMP,
            "updatedAt": TIMESTAMP,
        }
    ]
    objects["TripPlanRevision"] = [
        {
            "_id": "revision-1",
            "tripId": "trip-1",
            "revisionNumber": 1,
            "previousRevisionId": None,
            "changeReason": "首次计划",
            "severity": "major",
            "items": [
                {
                    "itemId": "item-1",
                    "dayIndex": 0,
                    "orderInDay": 0,
                    "kind": "activity",
                    "title": "博物馆",
                    "startAt": "2026-08-08T01:00:00Z",
                    "endAt": "2026-08-08T03:00:00Z",
                    "placeRef": {
                        "objectTypeRef": "entity.Place",
                        "objectId": "place-1",
                    },
                    "note": "入口见面",
                }
            ],
            "changes": [],
            "affectedPersonaIds": ["persona-host"],
            "createdByPersonaId": "persona-host",
            "createdAt": TIMESTAMP,
        }
    ]
    objects["TripMembership"] = [
        {
            "_id": "membership-1",
            "version": 2,
            "tripId": "trip-1",
            "personaId": "persona-host",
            "role": "organizer",
            "state": "active",
            "sourceKind": "circle",
            "sourceObjectRef": {
                "objectTypeRef": "circle.Circle",
                "objectId": "circle-1",
            },
            "sourceVersion": 1,
            "joinedAt": TIMESTAMP,
            "updatedAt": TIMESTAMP,
        }
    ]
    objects["TripMoment"] = [
        {
            "_id": "moment-1",
            "version": 1,
            "tripId": "trip-1",
            "revisionNumber": 1,
            "dayIndex": 0,
            "itemId": "item-1",
            "kind": "photo",
            "contentRef": {
                "objectTypeRef": "content.Post",
                "objectId": "post-moment",
            },
            "inlineText": None,
            "capturedAt": TIMESTAMP,
            "coarsePlaceRef": {
                "objectTypeRef": "entity.Place",
                "objectId": "place-1",
            },
            "visibility": "trip_members",
            "assignmentStatus": "confirmed",
            "attributionPersonaId": "persona-host",
            "sourceVersion": 1,
            "status": "active",
            "createdAt": TIMESTAMP,
            "updatedAt": TIMESTAMP,
        }
    ]
    objects["TripPlanContentLink"] = [
        {
            "_id": "link-1",
            "version": 1,
            "tripId": "trip-1",
            "postId": "post-link",
            "revisionNumber": 1,
            "targetKind": "item",
            "dayIndex": 0,
            "itemId": "item-1",
            "visibility": "trip_members",
            "linkedByPersonaId": "persona-host",
            "sourceVersion": 1,
            "status": "active",
            "createdAt": TIMESTAMP,
            "updatedAt": TIMESTAMP,
        }
    ]
    objects["TripGuideAssignment"] = [
        {
            "_id": "guide-1",
            "version": 1,
            "tripId": "trip-1",
            "taskKey": "guide",
            "assigneePersonaId": "persona-guide",
            "role": "licensed_guide",
            "taskKind": "route_guidance",
            "title": "路线讲解",
            "dueAt": None,
            "sourceRevisionNumber": 1,
            "attributionKind": "professional_commentary",
            "attributionPersonaId": "persona-guide",
            "publicQualificationPersonaId": "persona-guide",
            "status": "accepted",
            "createdByPersonaId": "persona-host",
            "createdAt": TIMESTAMP,
            "updatedAt": TIMESTAMP,
        }
    ]
    objects["TripPlanPlacement"] = [
        {
            "_id": "placement-1",
            "version": 1,
            "tripId": "trip-1",
            "surfaceKind": "conversation",
            "surfaceId": "conversation-1",
            "sourceVersion": 1,
            "status": "active",
            "createdByPersonaId": "persona-host",
            "createdAt": TIMESTAMP,
            "updatedAt": TIMESTAMP,
        }
    ]
    objects["TripMapView"] = [
        {
            "tripId": "trip-1",
            "currentRevisionId": "revision-1",
            "currentRevisionNumber": 1,
            "stops": [],
            "routeSegments": [],
            "momentMarkers": [],
            "sourceMomentIds": ["moment-1"],
            "sourceContentLinkIds": ["link-1"],
            "sourceDigest": DIGEST_A,
            "sourceEventId": "event-map-1",
            "projectedAt": TIMESTAMP,
        }
    ]
    objects["TripTimelineView"] = [
        {
            "tripId": "trip-1",
            "tripVersion": 3,
            "tripStatus": "active",
            "currentRevisionId": "revision-1",
            "currentRevisionNumber": 1,
            "revisionChangeReason": "首次计划",
            "revisionSeverity": "major",
            "tripContentLinks": [],
            "days": [],
            "sourceMomentIds": ["moment-1"],
            "sourceContentLinkIds": ["link-1"],
            "sourceDigest": DIGEST_A,
            "sourceEventId": "event-timeline-1",
            "projectedAt": TIMESTAMP,
        }
    ]
    objects["TripShareSnapshot"] = [
        {
            "_id": "share-1",
            "version": 1,
            "tripId": "trip-1",
            "sourceRevisionId": "revision-1",
            "sourceRevisionNumber": 1,
            "sourceDigest": DIGEST_A,
            "scope": "full",
            "dayIndex": None,
            "itemId": None,
            "momentIds": ["moment-1"],
            "visibility": "trip_members",
            "privacyPolicyDigest": DIGEST_B,
            "items": [],
            "moments": [],
            "contentLinks": [],
            "routeStops": [],
            "createdByPersonaId": "persona-host",
            "status": "active",
            "createdAt": TIMESTAMP,
        }
    ]
    objects["TripPlanTemplate"] = [
        {
            "_id": "template-1",
            "version": 1,
            "ownerPersonaId": "persona-host",
            "title": "公共模板",
            "summary": None,
            "dayCount": 1,
            "templateItemIds": [],
            "items": [],
            "attributionIds": [],
            "attributionPersonaIds": [],
            "attributions": [],
            "status": "active",
            "createdAt": TIMESTAMP,
            "updatedAt": TIMESTAMP,
        }
    ]
    payload: dict[str, object] = {
        "schema": control_plane.SOURCE_SNAPSHOT_SCHEMA,
        "environment": "alpha",
        "capturedAt": TIMESTAMP,
        "source": {
            "service": "travel-service",
            "releaseId": "travel-release-1",
            "serviceImageDigest": DIGEST_B,
            "configDigest": DIGEST_C,
        },
        "targetContractDigest": DIGEST_A,
        "objects": objects,
        "bindings": {
            "tripBindings": {
                "trip-1": {
                    "gatheringId": "gathering-1",
                    "sourceRouteId": "travel.trip.plan.detail",
                    "hostBinding": {
                        "hostSubjectKind": "persona",
                        "hostSubjectId": "persona-host",
                        "authorityEvidenceRef": "authority-host-1",
                        "authorityVersion": 1,
                        "authorityExpiresAt": None,
                    },
                    "purpose": {
                        "summary": "一起步行看展",
                        "coverRef": None,
                        "topicRefs": ["museum"],
                        "requirementRefs": [],
                        "costNotice": "free",
                        "costDescription": None,
                    },
                    "schedule": {
                        "timezone": "Asia/Shanghai",
                        "admissionClosesAt": "2026-08-07T16:00:00Z",
                    },
                    "place": {
                        "mode": "physical",
                        "coarsePlaceRef": {
                            "objectTypeRef": "entity.Place",
                            "objectId": "place-1",
                        },
                        "coarsePlaceLabel": "城市博物馆",
                        "exactMeetingPoint": "东门",
                        "onlineLocationRef": None,
                    },
                    "policySet": {
                        "audiencePolicy": "public",
                        "admissionPolicy": "open",
                        "capacityPolicy": {"maxParticipants": 10},
                        "disclosurePolicy": {
                            "timeDisclosure": "exact",
                            "placeDisclosure": "coarse",
                            "rosterDisclosure": "count_only",
                        },
                        "applicationQuestions": [],
                        "riskControlPolicyRef": "risk-policy-1",
                        "policyDecisionRef": None,
                        "policyDigest": DIGEST_A,
                        "obligationDigest": None,
                    },
                    "admissionControl": {
                        "status": "open",
                        "pausedByPersonaId": None,
                        "reasonRef": None,
                        "pausedAt": None,
                        "version": 1,
                    },
                    "conversationId": "conversation-1",
                    "roomBindingStatus": "ready",
                    "outcome": None,
                    "completedAt": None,
                }
            },
            "membershipBindings": {
                "membership-1": {
                    "admissionSource": "open",
                    "attemptNo": 1,
                    "seatHoldUntil": None,
                    "closedByPersonaId": None,
                    "reasonRef": None,
                    "reviewExpectedBy": None,
                    "applicationAnswers": [],
                    "attendance": {
                        "status": "not_declared",
                        "declaredAt": None,
                        "evidenceRefs": [],
                    },
                    "currentChangeAcknowledgement": {
                        "revisionId": "gathering-revision:revision-1",
                        "revisionNumber": 1,
                        "revisionDigest": None,
                        "status": "not_required",
                        "deadlineAt": None,
                        "acknowledgedAt": None,
                    },
                    "organizerAssignment": {
                        "personaId": "persona-host",
                        "role": "primary_organizer",
                        "authorityEvidenceRef": "authority-host-1",
                        "authorityVersion": 1,
                        "assignedAt": TIMESTAMP,
                        "revokedAt": None,
                        "version": 1,
                    },
                }
            },
            "placementRouteIds": {
                "placement-1": "chat.conversation.detail",
            },
        },
    }
    payload["snapshotDigest"] = control_plane.canonical_digest(payload)
    return payload


def _write_snapshot(path: Path, snapshot: dict[str, object]) -> None:
    path.write_text(
        json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _reseal(snapshot: dict[str, object]) -> None:
    snapshot.pop("snapshotDigest", None)
    snapshot["snapshotDigest"] = control_plane.canonical_digest(snapshot)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _migration_receipts(
    environment: str = "alpha",
) -> tuple[dict[str, object], dict[str, object]]:
    snapshot = _source_snapshot()
    snapshot["environment"] = environment
    _reseal(snapshot)
    mapping = control_plane.build_mapping(snapshot, _target_contract())
    inventory = control_plane.build_receipt(
        environment=environment,
        phase="inventory",
        snapshot=snapshot,
        target_contract=_target_contract(),
        mapping=mapping,
    )
    target_snapshot = {
        "documents": list(mapping.documents),
        "snapshotDigest": control_plane.canonical_digest(mapping.documents),
    }
    parity = control_plane.build_receipt(
        environment=environment,
        phase="parity",
        snapshot=snapshot,
        target_contract=_target_contract(),
        mapping=mapping,
        target_snapshot=target_snapshot,
    )
    assert inventory["status"] == "passed"
    assert parity["status"] == "passed"
    return inventory, parity


def _operational_evidence(
    evidence_type: str,
    *,
    environment: str,
    subject_digests: dict[str, str],
    claims: dict[str, object],
    write_set: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    stable: dict[str, object] = {
        "schema": control_plane.OPERATIONAL_EVIDENCE_SCHEMA,
        "migrationId": control_plane.MIGRATION_ID,
        "environment": environment,
        "evidenceType": evidence_type,
        "status": "passed",
        "issuedAt": TIMESTAMP,
        "subjectDigests": subject_digests,
        "writeSet": write_set or [],
        "claims": claims,
        "signature": {
            "algorithm": "ed25519",
            "keyId": "ops-approval-key-1",
            "signatureDigest": DIGEST_A,
            "verificationReceiptDigest": DIGEST_B,
        },
    }
    return {
        **stable,
        "evidenceDigest": control_plane.canonical_digest(stable),
    }


def _cutover_evidence(
    environment: str = "alpha",
) -> dict[str, object]:
    inventory, parity = _migration_receipts(environment)
    common = {
        "inventoryReceiptDigest": inventory["receiptDigest"],
        "parityReceiptDigest": parity["receiptDigest"],
        "sourceSnapshotDigest": parity["source"]["snapshotDigest"],
        "targetContractDigest": DIGEST_A,
        "crosswalkDigest": parity["crosswalkDigest"],
        "mappingDigest": parity["mapping"]["targetDocumentDigest"],
    }
    backup = _operational_evidence(
        "target_backup",
        environment=environment,
        subject_digests=dict(common),
        claims={"backupScope": "target_only", "restorable": True},
    )
    freeze = _operational_evidence(
        "source_write_freeze",
        environment=environment,
        subject_digests=dict(common),
        claims={
            "sourceWriteState": "frozen_permanently",
            "sourceWriteRecoveryAllowed": False,
            "dualWriteEnabled": False,
        },
    )
    target_command = _operational_evidence(
        "target_command_import",
        environment=environment,
        subject_digests={
            **common,
            "targetBackupEvidenceDigest": backup["evidenceDigest"],
            "sourceFreezeEvidenceDigest": freeze["evidenceDigest"],
            "protectedWriteApprovalDigest": DIGEST_C,
        },
        claims={
            "executionPath": "canonical_commands",
            "directDatabaseWrite": False,
            "derivedProjectionWrite": False,
            "sourceWrite": False,
        },
        write_set=[
            {
                "plane": "target_command",
                "service": "circle-service",
                "operationId": "circle.gathering.CreateGatheringDraft",
                "targetObjectId": "circle.gathering",
                "commandReceiptDigest": DIGEST_A,
            }
        ],
    )
    config_candidate_digest = DIGEST_B
    planned_write_set = [
        {
            "stepId": "cutover.activate-target-only-config",
            "plane": "target_config",
            "service": "circle-service",
            "operation": "activate_target_only_candidate",
            "candidateDigest": config_candidate_digest,
            "executionMode": "external_approval_only",
        }
    ]
    planned_write_set_digest = control_plane.canonical_digest(planned_write_set)
    approval = _operational_evidence(
        "protected_environment_approval",
        environment=environment,
        subject_digests={
            **common,
            "targetCommandEvidenceDigest": target_command["evidenceDigest"],
            "configCandidateDigest": config_candidate_digest,
            "writeSetDigest": planned_write_set_digest,
        },
        claims={
            "decision": "approved",
            "protectedEnvironmentWritesApproved": True,
        },
    )
    activation = _operational_evidence(
        "target_config_activation",
        environment=environment,
        subject_digests={
            **common,
            "configCandidateDigest": config_candidate_digest,
            "plannedWriteSetDigest": planned_write_set_digest,
            "approvalEvidenceDigest": approval["evidenceDigest"],
        },
        claims={
            "targetActivated": True,
            "sourceRuntimeDecommissioned": True,
            "sourceTrafficMode": "disabled",
            "sourceFallbackEnabled": False,
            "sourceWriteRecoveryAllowed": False,
        },
        write_set=[
            {
                "plane": "target_config",
                "service": "circle-service",
                "operationId": "activate_target_only_candidate",
                "targetObjectId": "circle.gathering",
                "commandReceiptDigest": DIGEST_B,
            }
        ],
    )
    return {
        "inventory": inventory,
        "parity": parity,
        "backup": backup,
        "freeze": freeze,
        "targetCommand": target_command,
        "configCandidateDigest": config_candidate_digest,
        "approval": approval,
        "activation": activation,
    }


def _reseal_evidence(evidence: dict[str, object]) -> None:
    evidence.pop("evidenceDigest", None)
    evidence["evidenceDigest"] = control_plane.canonical_digest(evidence)


def _reseal_migration_receipt(
    receipt: dict[str, object],
) -> dict[str, object]:
    stable = {
        key: value
        for key, value in receipt.items()
        if key not in {"receiptId", "receiptDigest"}
    }
    return control_plane._seal_receipt(stable)


def _write_cutover_inputs(
    root: Path,
    evidence: dict[str, object],
    *,
    include_approval: bool = True,
    include_activation: bool = True,
) -> list[str]:
    values = (
        ("inventory", "--inventory-receipt", "inventory.json"),
        ("parity", "--parity-receipt", "parity.json"),
        ("backup", "--target-backup-receipt", "backup.json"),
        ("freeze", "--source-freeze-receipt", "freeze.json"),
        ("targetCommand", "--target-command-receipt", "target-command.json"),
    )
    arguments: list[str] = []
    for key, flag, filename in values:
        path = root / filename
        _write_json(path, evidence[key])
        arguments.extend((flag, str(path)))
    if include_approval:
        path = root / "approval.json"
        _write_json(path, evidence["approval"])
        arguments.extend(("--approval-receipt", str(path)))
    if include_activation:
        path = root / "activation.json"
        _write_json(path, evidence["activation"])
        arguments.extend(("--config-activation-receipt", str(path)))
    arguments.extend(
        (
            "--config-candidate-digest",
            str(evidence["configCandidateDigest"]),
        )
    )
    return arguments


def test_full_crosswalk_maps_or_disposes_every_source_object() -> None:
    result = control_plane.build_mapping(_source_snapshot(), _target_contract())

    assert len(result.records) == len(control_plane.SOURCE_OBJECT_TYPES)
    assert not [
        record for record in result.records if record["disposition"] == "quarantined"
    ]
    assert {record["sourceObjectType"] for record in result.records} == set(
        control_plane.SOURCE_OBJECT_TYPES
    )
    assert {wrapper["kind"] for wrapper in result.documents} == {
        "circle.gathering",
        "circle.gathering_plan",
    }
    assert all(
        ref["objectType"] in control_plane.CANONICAL_TARGET_OBJECT_IDS
        for record in result.records
        for ref in record["targetRefs"]
    )
    policies = {
        record["sourceObjectType"]: (
            record["disposition"],
            record["reason"],
        )
        for record in result.records
        if record["sourceObjectType"]
        in {
            "TripGuideAssignment",
            "TripMapView",
            "TripTimelineView",
            "TripShareSnapshot",
            "TripPlanTemplate",
        }
    }
    assert policies["TripGuideAssignment"] == (
        "not_applicable",
        "canonical_target_guide_assignment_contract_unavailable",
    )
    assert policies["TripMapView"] == (
        "not_applicable",
        "derived_projection_rebuild_only",
    )
    assert policies["TripTimelineView"] == (
        "not_applicable",
        "derived_projection_rebuild_only",
    )
    assert policies["TripShareSnapshot"] == (
        "not_applicable",
        "privacy_trimmed_snapshot_is_parity_input_only",
    )
    assert policies["TripPlanTemplate"] == (
        "not_applicable",
        "canonical_target_plan_template_contract_unavailable",
    )
    assert all(
        record["targetRefs"] == []
        for record in result.records
        if record["disposition"] == "not_applicable"
    )
    assert result.validation["gatheringSchema"]["errorCount"] == 0
    assert result.validation["gatheringPlanSchema"]["errorCount"] == 0


def test_missing_target_field_quarantines_without_fabrication() -> None:
    snapshot = _source_snapshot()
    snapshot["bindings"]["tripBindings"]["trip-1"]["schedule"].pop("timezone")
    _reseal(snapshot)

    result = control_plane.build_mapping(snapshot, _target_contract())

    trip_record = next(
        record for record in result.records if record["sourceObjectType"] == "TripPlan"
    )
    assert trip_record["disposition"] == "quarantined"
    assert trip_record["reason"] == "timezone_missing_or_invalid"
    assert not [
        wrapper
        for wrapper in result.documents
        if wrapper["kind"] == "circle.gathering"
    ]


def test_template_policy_archives_only_already_archived_source_templates() -> None:
    snapshot = _source_snapshot()
    snapshot["objects"]["TripPlanTemplate"][0]["status"] = "archived"
    _reseal(snapshot)

    result = control_plane.build_mapping(snapshot, _target_contract())
    record = next(
        value
        for value in result.records
        if value["sourceObjectType"] == "TripPlanTemplate"
    )

    assert record["disposition"] == "archived"
    assert record["reason"] == "source_template_archived"
    assert record["targetRefs"] == []


def test_receipt_is_idempotent_and_never_emits_raw_pii() -> None:
    snapshot = _source_snapshot()
    snapshot["objects"]["TripMoment"][0]["inlineText"] = (
        "联系 alice@example.com 或 13800138000"
    )
    _reseal(snapshot)
    mapping = control_plane.build_mapping(snapshot, _target_contract())

    first = control_plane.build_receipt(
        environment="alpha",
        phase="dry-run",
        snapshot=snapshot,
        target_contract=_target_contract(),
        mapping=mapping,
    )
    second = control_plane.build_receipt(
        environment="alpha",
        phase="dry-run",
        snapshot=snapshot,
        target_contract=_target_contract(),
        mapping=mapping,
    )
    encoded = json.dumps(first, ensure_ascii=False, sort_keys=True)

    assert first == second
    assert first["receiptId"] == second["receiptId"]
    assert first["writeSet"] == []
    assert first["piiRedaction"]["rawValuesEmitted"] is False
    assert first["piiRedaction"]["detectedValuePatterns"] == {
        "email": 1,
        "phone": 1,
    }
    assert "alice@example.com" not in encoded
    assert "13800138000" not in encoded
    assert "persona-host" not in encoded
    assert "东门" not in encoded


def test_prod_dry_run_is_gate_block_and_writes_output_only(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    source_path = tmp_path / "source.json"
    snapshot = _source_snapshot()
    snapshot["environment"] = "prod"
    _reseal(snapshot)
    _write_snapshot(source_path, snapshot)
    source_before = source_path.read_bytes()
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    args = argparse.Namespace(
        env="prod",
        phase="dry-run",
        source_snapshot=str(source_path),
        target_snapshot="",
        report_dir=str(output / "prod-dry-run"),
    )

    result = control_plane.execute(args)

    assert result["exitCode"] == 2
    report = json.loads(
        (output / "prod-dry-run/report.json").read_text(encoding="utf-8")
    )
    assert report["errorCode"] == "PROD_PHASE_FORBIDDEN"
    assert report["writeSet"] == []
    assert source_path.read_bytes() == source_before
    assert {path.name for path in (output / "prod-dry-run").iterdir()} == {
        "report.json"
    }


def test_alpha_dry_run_validates_in_memory_and_emits_receipt_only(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    source_path = tmp_path / "source.json"
    snapshot = _source_snapshot()
    _write_snapshot(source_path, snapshot)
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setattr(
        control_plane,
        "resolve_target_contract",
        lambda _root: _target_contract(),
    )
    args = argparse.Namespace(
        env="alpha",
        phase="dry-run",
        source_snapshot=str(source_path),
        target_snapshot="",
        report_dir=str(output / "alpha-dry-run"),
    )

    result = control_plane.execute(args)
    receipt = json.loads(
        (output / "alpha-dry-run/receipt.json").read_text(encoding="utf-8")
    )

    assert result["exitCode"] == 0
    assert receipt["status"] == "passed"
    assert receipt["executionMode"] == "zero_write"
    assert receipt["writeSet"] == []
    assert receipt["mapping"]["targetDocumentCount"] > 0
    assert receipt["mapping"]["targetDocumentsEmitted"] is False
    assert {path.name for path in (output / "alpha-dry-run").iterdir()} == {
        "receipt.json",
        "report.json",
    }


def test_receipt_path_outside_qwq_output_is_rejected(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    forbidden = tmp_path / "forbidden"
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    args = argparse.Namespace(
        env="alpha",
        phase="inventory",
        source_snapshot="",
        target_snapshot="",
        report_dir=str(forbidden),
    )

    result = control_plane.execute(args)

    assert result["exitCode"] == 2
    assert result["details"][0].startswith("OUTPUT_PATH_FORBIDDEN:")
    assert not forbidden.exists()


def test_digest_mismatch_fails_before_mapping(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    source_path = tmp_path / "source.json"
    snapshot = _source_snapshot()
    snapshot["targetContractDigest"] = DIGEST_B
    _reseal(snapshot)
    _write_snapshot(source_path, snapshot)
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setattr(
        control_plane,
        "resolve_target_contract",
        lambda _root: _target_contract(),
    )
    args = argparse.Namespace(
        env="alpha",
        phase="inventory",
        source_snapshot=str(source_path),
        target_snapshot="",
        report_dir=str(output / "digest"),
    )

    result = control_plane.execute(args)

    assert result["exitCode"] == 2
    report = json.loads((output / "digest/report.json").read_text(encoding="utf-8"))
    assert report["errorCode"] == "TARGET_CONTRACT_DIGEST_MISMATCH"


def test_missing_canonical_generated_contract_digest_fails_fast(
    tmp_path: Path,
) -> None:
    with pytest.raises(control_plane.MigrationControlError) as raised:
        control_plane.resolve_target_contract(tmp_path)

    assert raised.value.code == "TARGET_CONTRACT_DIGEST_MISSING"


def test_duplicate_conversation_is_a_deterministic_collision() -> None:
    snapshot = _source_snapshot()
    plan = copy.deepcopy(snapshot["objects"]["TripPlan"][0])
    plan.update(
        {
            "_id": "trip-2",
            "organizerPersonaId": "persona-host-2",
            "currentRevisionId": "revision-2",
        }
    )
    revision = copy.deepcopy(snapshot["objects"]["TripPlanRevision"][0])
    revision.update(
        {
            "_id": "revision-2",
            "tripId": "trip-2",
            "createdByPersonaId": "persona-host-2",
        }
    )
    membership = copy.deepcopy(snapshot["objects"]["TripMembership"][0])
    membership.update(
        {
            "_id": "membership-2",
            "tripId": "trip-2",
            "personaId": "persona-host-2",
        }
    )
    trip_binding = copy.deepcopy(snapshot["bindings"]["tripBindings"]["trip-1"])
    trip_binding.update(
        {
            "gatheringId": "gathering-2",
            "conversationId": "conversation-1",
        }
    )
    membership_binding = copy.deepcopy(
        snapshot["bindings"]["membershipBindings"]["membership-1"]
    )
    membership_binding["organizerAssignment"]["personaId"] = "persona-host-2"
    snapshot["objects"]["TripPlan"].append(plan)
    snapshot["objects"]["TripPlanRevision"].append(revision)
    snapshot["objects"]["TripMembership"].append(membership)
    snapshot["bindings"]["tripBindings"]["trip-2"] = trip_binding
    snapshot["bindings"]["membershipBindings"]["membership-2"] = membership_binding
    _reseal(snapshot)

    result = control_plane.build_mapping(snapshot, _target_contract())

    assert result.conflicts["conversationId"]["count"] == 1
    assert any(
        record["sourceObjectType"] == "TripPlan"
        and record["disposition"] == "quarantined"
        and record["reason"] == "duplicate_conversation_id"
        for record in result.records
    )
    receipt = control_plane.build_receipt(
        environment="alpha",
        phase="inventory",
        snapshot=snapshot,
        target_contract=_target_contract(),
        mapping=result,
    )
    assert receipt["status"] == "GATE_BLOCK"
    assert receipt["conflicts"]["totalCount"] > 0


def test_parity_reconciles_all_dimensions_deterministically() -> None:
    mapping = control_plane.build_mapping(
        _source_snapshot(),
        _target_contract(),
    )

    first = control_plane.build_parity(mapping.documents, mapping.documents)
    second = control_plane.build_parity(mapping.documents, mapping.documents)

    assert first == second
    assert first["status"] == "passed"
    assert first["percentage"] == 100
    assert set(first["dimensions"]) == {
        "identity",
        "count",
        "state",
        "host",
        "membership",
        "plan",
        "contentRefs",
        "outcome",
    }


def test_stackctl_parser_exposes_cutover_and_rollback_contract() -> None:
    args = stackctl.build_parser().parse_args(
        [
            "migration",
            "travel-to-gathering",
            "--env",
            "gamma",
            "--phase",
            "rollback",
            "--cutover-receipt",
            "cutover.json",
            "--approval-receipt",
            "approval.json",
            "--target-restore-receipt",
            "restore.json",
            "--post-restore-parity-receipt",
            "parity.json",
            "--rollback-mode",
            "target_snapshot",
            "--rollback-candidate-digest",
            DIGEST_A,
        ]
    )

    assert args.migration_command == "travel-to-gathering"
    assert args.phase == "rollback"
    assert args.rollback_mode == "target_snapshot"
    assert args.cutover_receipt == "cutover.json"
    assert args.target_restore_receipt == "restore.json"


def test_cutover_requires_upstream_receipts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    args = stackctl.build_parser().parse_args(
        [
            "migration",
            "travel-to-gathering",
            "--env",
            "alpha",
            "--phase",
            "cutover",
            "--report-dir",
            str(output / "cutover"),
        ]
    )

    result = control_plane.command(args)

    assert result["exitCode"] == 2
    report = json.loads(
        (output / "cutover/report.json").read_text(encoding="utf-8")
    )
    assert report["errorCode"] == "REQUIRED_RECEIPT_MISSING"
    assert report["writeSet"] == []
    assert not (output / "cutover/receipt.json").exists()


def test_cutover_validates_receipt_chain_and_emits_target_only_write_set(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    evidence = _cutover_evidence()
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setattr(
        control_plane,
        "resolve_target_contract",
        lambda _root: _target_contract(),
    )
    args = stackctl.build_parser().parse_args(
        [
            "migration",
            "travel-to-gathering",
            "--env",
            "alpha",
            "--phase",
            "cutover",
            "--report-dir",
            str(output / "cutover"),
            *_write_cutover_inputs(inputs, evidence),
        ]
    )

    result = control_plane.command(args)
    receipt = json.loads(
        (output / "cutover/receipt.json").read_text(encoding="utf-8")
    )

    assert result["exitCode"] == 0
    assert receipt["status"] == "passed"
    assert receipt["executionMode"] == "external_evidence_only"
    assert receipt["cutover"]["status"] == "externally_executed"
    assert receipt["cutover"]["sourceWriteState"] == "frozen_permanently"
    assert receipt["cutover"]["sourceWriteRecoveryAllowed"] is False
    assert receipt["cutover"]["sourceFallbackAllowed"] is False
    assert receipt["cutover"]["configActivationPlan"] == {
        "candidateDigest": DIGEST_B,
        "writeSetDigest": control_plane.canonical_digest(receipt["writeSet"]),
        "activateTargetReads": True,
        "decommissionSourceRuntime": True,
        "sourceTrafficMode": "disabled",
        "sourceFallbackAllowed": False,
        "sourceWriteRecoveryAllowed": False,
        "executedByControlPlane": False,
    }
    assert receipt["writeSet"] == [
        {
            "stepId": "cutover.activate-target-only-config",
            "plane": "target_config",
            "service": "circle-service",
            "operation": "activate_target_only_candidate",
            "candidateDigest": DIGEST_B,
            "executionMode": "external_approval_only",
        }
    ]
    assert "travel-service" not in json.dumps(receipt["writeSet"])


def test_prod_cutover_without_approval_remains_gate_block(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    evidence = _cutover_evidence("prod")
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setattr(
        control_plane,
        "resolve_target_contract",
        lambda _root: _target_contract(),
    )
    args = stackctl.build_parser().parse_args(
        [
            "migration",
            "travel-to-gathering",
            "--env",
            "prod",
            "--phase",
            "cutover",
            "--report-dir",
            str(output / "prod-cutover"),
            *_write_cutover_inputs(
                inputs,
                evidence,
                include_approval=False,
                include_activation=False,
            ),
        ]
    )

    result = control_plane.command(args)
    receipt = json.loads(
        (output / "prod-cutover/receipt.json").read_text(encoding="utf-8")
    )

    assert result["exitCode"] == 2
    assert receipt["status"] == "GATE_BLOCK"
    assert receipt["executionMode"] == "approval_plan"
    assert receipt["cutover"]["approvalRequirement"]["status"] == "missing"
    assert {
        blocker["code"] for blocker in receipt["blockers"]
    } == {
        "PROTECTED_ENVIRONMENT_APPROVAL_REQUIRED",
        "TARGET_CONFIG_ACTIVATION_EVIDENCE_REQUIRED",
    }
    assert len(receipt["writeSet"]) == 1


def test_cutover_rejects_external_evidence_digest_mismatch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    evidence = _cutover_evidence()
    evidence["backup"]["subjectDigests"]["sourceSnapshotDigest"] = DIGEST_C
    _reseal_evidence(evidence["backup"])
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setattr(
        control_plane,
        "resolve_target_contract",
        lambda _root: _target_contract(),
    )
    args = stackctl.build_parser().parse_args(
        [
            "migration",
            "travel-to-gathering",
            "--env",
            "alpha",
            "--phase",
            "cutover",
            "--report-dir",
            str(output / "digest-mismatch"),
            *_write_cutover_inputs(inputs, evidence),
        ]
    )

    result = control_plane.command(args)
    report = json.loads(
        (output / "digest-mismatch/report.json").read_text(encoding="utf-8")
    )

    assert result["exitCode"] == 2
    assert report["errorCode"] == "EXTERNAL_EVIDENCE_DIGEST_MISMATCH"


@pytest.mark.parametrize(
    ("plane", "service", "operation_id", "expected_code"),
    (
        (
            "source_command",
            "travel-service",
            "travel.TripPlan.Update",
            "SOURCE_WRITE_FORBIDDEN",
        ),
        (
            "target_database",
            "circle-service",
            "direct_database_write",
            "DIRECT_TARGET_WRITE_FORBIDDEN",
        ),
    ),
)
def test_cutover_rejects_source_and_direct_target_database_writes(
    monkeypatch,
    tmp_path: Path,
    plane: str,
    service: str,
    operation_id: str,
    expected_code: str,
) -> None:
    output = tmp_path / ".qwq_output"
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    evidence = _cutover_evidence()
    write = evidence["targetCommand"]["writeSet"][0]
    write.update(
        {
            "plane": plane,
            "service": service,
            "operationId": operation_id,
        }
    )
    _reseal_evidence(evidence["targetCommand"])
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setattr(
        control_plane,
        "resolve_target_contract",
        lambda _root: _target_contract(),
    )
    args = stackctl.build_parser().parse_args(
        [
            "migration",
            "travel-to-gathering",
            "--env",
            "alpha",
            "--phase",
            "cutover",
            "--report-dir",
            str(output / expected_code),
            *_write_cutover_inputs(inputs, evidence),
        ]
    )

    result = control_plane.command(args)
    report = json.loads(
        (output / expected_code / "report.json").read_text(encoding="utf-8")
    )

    assert result["exitCode"] == 2
    assert report["errorCode"] == expected_code


def test_cutover_rejects_quarantined_upstream_receipt(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    evidence = _cutover_evidence()
    evidence["inventory"]["dispositions"]["counts"]["quarantined"] = 1
    evidence["inventory"] = _reseal_migration_receipt(evidence["inventory"])
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setattr(
        control_plane,
        "resolve_target_contract",
        lambda _root: _target_contract(),
    )
    args = stackctl.build_parser().parse_args(
        [
            "migration",
            "travel-to-gathering",
            "--env",
            "alpha",
            "--phase",
            "cutover",
            "--report-dir",
            str(output / "quarantined"),
            *_write_cutover_inputs(inputs, evidence),
        ]
    )

    result = control_plane.command(args)
    report = json.loads(
        (output / "quarantined/report.json").read_text(encoding="utf-8")
    )

    assert result["exitCode"] == 2
    assert report["errorCode"] == "QUARANTINED_SOURCE_OBJECTS"


def test_orphan_is_quarantined_and_blocks_mapping() -> None:
    snapshot = _source_snapshot()
    snapshot["objects"]["TripMoment"][0]["tripId"] = "trip-missing"
    _reseal(snapshot)

    mapping = control_plane.build_mapping(snapshot, _target_contract())

    assert any(
        blocker["code"] == "ORPHAN_SOURCE_REFERENCE"
        for blocker in mapping.blockers
    )
    assert any(
        record["sourceObjectType"] == "TripMoment"
        and record["disposition"] == "quarantined"
        and record["reason"] == "orphan_trip_reference"
        for record in mapping.records
    )


def test_rollback_only_restores_target_snapshot_and_requires_post_parity(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    evidence = _cutover_evidence()
    cutover = control_plane.build_cutover_receipt(
        environment="alpha",
        inventory_receipt=evidence["inventory"],
        parity_receipt=evidence["parity"],
        target_contract=_target_contract(),
        target_backup_evidence=evidence["backup"],
        source_freeze_evidence=evidence["freeze"],
        target_command_evidence=evidence["targetCommand"],
        config_candidate_digest=DIGEST_B,
        approval_evidence=evidence["approval"],
        activation_evidence=evidence["activation"],
    )
    cutover_path = inputs / "cutover.json"
    parity_path = inputs / "post-restore-parity.json"
    _write_json(cutover_path, cutover)
    _write_json(parity_path, evidence["parity"])
    planned_write_set = [
        {
            "stepId": "rollback.target_snapshot",
            "plane": "target_snapshot",
            "service": "circle-service",
            "operation": "restore_target_snapshot",
            "candidateDigest": DIGEST_C,
            "executionMode": "external_approval_only",
        }
    ]
    rollback_subject = {
        "cutoverReceiptDigest": cutover["receiptDigest"],
        "targetContractDigest": DIGEST_A,
        "crosswalkDigest": cutover["crosswalkDigest"],
        "sourceSnapshotDigest": cutover["source"]["snapshotDigest"],
        "rollbackCandidateDigest": DIGEST_C,
        "plannedWriteSetDigest": control_plane.canonical_digest(
            planned_write_set
        ),
    }
    approval = _operational_evidence(
        "protected_environment_approval",
        environment="alpha",
        subject_digests=dict(rollback_subject),
        claims={
            "decision": "approved",
            "protectedEnvironmentWritesApproved": True,
        },
    )
    restore = _operational_evidence(
        "target_restore",
        environment="alpha",
        subject_digests={
            **rollback_subject,
            "approvalEvidenceDigest": approval["evidenceDigest"],
            "restoredTargetSnapshotDigest": evidence["parity"]["target"][
                "snapshotDigest"
            ],
        },
        claims={
            "targetRestored": True,
            "sourceWrite": False,
            "directDatabaseWrite": False,
            "derivedProjectionWrite": False,
        },
        write_set=[
            {
                "plane": "target_snapshot",
                "service": "circle-service",
                "operationId": "restore_target_snapshot",
                "targetObjectId": "circle.gathering",
                "commandReceiptDigest": DIGEST_C,
            }
        ],
    )
    approval_path = inputs / "rollback-approval.json"
    restore_path = inputs / "restore.json"
    _write_json(approval_path, approval)
    _write_json(restore_path, restore)
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setattr(
        control_plane,
        "resolve_target_contract",
        lambda _root: _target_contract(),
    )
    args = stackctl.build_parser().parse_args(
        [
            "migration",
            "travel-to-gathering",
            "--env",
            "alpha",
            "--phase",
            "rollback",
            "--report-dir",
            str(output / "rollback"),
            "--cutover-receipt",
            str(cutover_path),
            "--post-restore-parity-receipt",
            str(parity_path),
            "--approval-receipt",
            str(approval_path),
            "--target-restore-receipt",
            str(restore_path),
            "--rollback-mode",
            "target_snapshot",
            "--rollback-candidate-digest",
            DIGEST_C,
        ]
    )

    result = control_plane.command(args)
    receipt = json.loads(
        (output / "rollback/receipt.json").read_text(encoding="utf-8")
    )

    assert result["exitCode"] == 0
    assert receipt["rollback"]["status"] == (
        "externally_restored_and_parity_passed"
    )
    assert receipt["rollback"]["sourceWriteRecoveryAllowed"] is False
    assert receipt["writeSet"][0]["plane"] == "target_snapshot"
    assert receipt["writeSet"][0]["executionMode"] == "externally_executed"
    assert "travel-service" not in json.dumps(receipt["writeSet"])


def test_rollback_restore_evidence_cannot_recover_travel_source_writes(
    tmp_path: Path,
) -> None:
    evidence = _operational_evidence(
        "target_restore",
        environment="alpha",
        subject_digests={"cutoverReceiptDigest": DIGEST_A},
        claims={
            "targetRestored": True,
            "sourceWrite": False,
            "directDatabaseWrite": False,
            "derivedProjectionWrite": False,
        },
        write_set=[
            {
                "plane": "source_write_recovery",
                "service": "travel-service",
                "operationId": "restore_travel_writes",
                "targetObjectId": "travel.TripPlan",
                "commandReceiptDigest": DIGEST_B,
            }
        ],
    )
    path = tmp_path / "restore.json"
    _write_json(path, evidence)

    with pytest.raises(control_plane.MigrationControlError) as raised:
        control_plane._load_operational_evidence(
            path,
            environment="alpha",
            evidence_type="target_restore",
            expected_digests={"cutoverReceiptDigest": DIGEST_A},
            target_contract=_target_contract(),
        )

    assert raised.value.code == "SOURCE_WRITE_FORBIDDEN"
