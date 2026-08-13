"""travel-to-gathering 迁移契约套件的共享构造 helper。

由 1000 行硬顶拆分自
quwoquan_ops/tests/local_contract/test_travel_to_gathering_migration__local_contract_test.py，
供 stackctl concern 下 mapping / execute / cutover_rollback 三个拆分套件共用；
函数体逐字保留原实现。

spec_ref: specs/feature-tree/travel-journey/spec.md#dom-001
"""

from __future__ import annotations

import json
from pathlib import Path

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
