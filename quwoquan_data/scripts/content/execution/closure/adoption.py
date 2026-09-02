"""Canonical task/campaign adoption of one immutable reviewed release closure.

This operation creates only task and campaign evidence.  It never creates a
release, mutates canonical publish state, ships data, or activates an
environment.  The release selector consumes the resulting fenced evidence in a
later phase.
"""

from __future__ import annotations

import argparse
import fcntl
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.io import read_json, write_json
from core.release_layout import objects_merkle
from core.source_digest import (
    content_source_revision,
    current_source_definition_snapshot,
)

from content.execution.campaign.plan import freeze_plan
from content.execution.campaign.receipt import write_adoption_publish_receipt
from content.execution.campaign.runtime import campaign_run_session
from content.execution.campaign.submission import (
    campaign_root,
    load_submissions,
    write_adoption_submission,
)
from content.execution.planning.carrier_demand import normalize_active_carriers
from content.execution.campaign.workspace import (
    CampaignRuntimePaths,
    current_branch,
    current_commit,
)
from content.execution.identity import parse_execution_id
from content.execution.closure.adoption_campaign_contract import (
    ADOPTION_OPERATIONS,
    CAMPAIGN_ADOPTION_FIELD,
    adopted_object_refs,
    validate_adoption_task_binding,
    validate_campaign_adoption_binding,
)
from content.execution.closure.adoption_contract import (
    _desired_refs,
    _expected_evidence,
    _media_assets,
    canonical_digest,
    file_digest,
    validate_release_identity_incident,
    validate_reviewed_closure_adoption_receipt,
    validate_reviewed_closure_adoption_ref,
)
from content.execution.closure.adoption_identity import (
    ReleaseIdentityTuple,
)
from content.execution.workspace import entity_catalog_digest
from content.release.canonical.release_identity_incident import (
    release_identity_protection_lock,
)
from content.release.canonical.release_operation_lock import (
    release_operation_guard,
    release_operation_lock_root,
)

_SOURCE_EVIDENCE = {
    "releaseAttestation": "attestations/release.json",
    "releaseHeader": "payload/release.json",
    "desiredState": "payload/desired_state.json",
    "objectIndex": "payload/index/objects.json",
    "mediaManifest": "payload/media_manifest.json",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _portable(path: Path, *, output_root: Path) -> str:
    resolved = path.resolve(strict=True)
    try:
        return resolved.relative_to(output_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"adoption evidence is outside output root: {path}") from exc


def _file_binding(path: Path, *, output_root: Path) -> dict[str, str]:
    return {
        "ref": _portable(path, output_root=output_root),
        "sha256": file_digest(path),
    }


@contextmanager
def _adoption_lock(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".adoption.lock").open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def adoption_root(output_root: Path, adoption_id: str) -> Path:
    normalized = str(adoption_id or "").strip()
    if not normalized or "/" in normalized or normalized in {".", ".."}:
        raise ValueError("adoptionId is not a safe identifier")
    return output_root / "data/local/reviewed-closure-adoptions" / normalized


def _source_release_identity(release_root: Path) -> ReleaseIdentityTuple:
    attestation_path = release_root / "attestations/release.json"
    attestation = read_json(attestation_path)
    if not isinstance(attestation, dict):
        raise TypeError("source release attestation must be an object")
    return ReleaseIdentityTuple.from_document(
        {
            "releaseId": attestation.get("releaseId"),
            "payloadSha256": attestation.get("payloadSha256"),
            "canonicalMerkle": attestation.get("canonicalMerkle"),
            "attestationFileSha256": file_digest(attestation_path),
        },
        label="source release identity",
    )


def _write_adoption_ref(
    *,
    adoption_id: str,
    source_release_id: str,
    identity_incident_path: Path,
    output_root: Path,
) -> tuple[dict[str, Any], Path]:
    root = adoption_root(output_root, adoption_id)
    path = root / "adoption_ref.json"
    if path.is_file():
        existing = read_json(path)
        validated = validate_reviewed_closure_adoption_ref(
            existing,
            output_root=output_root,
        )
        if (
            validated.adoption_id != adoption_id
            or validated.source_release_identity.release_id != source_release_id
            or (existing.get("identityIncident") or {}).get("ref")
            != _portable(identity_incident_path, output_root=output_root)
        ):
            raise ValueError("reviewed closure adoption ref create-once conflict")
        return dict(existing), path

    release_root = output_root / "data/releases" / source_release_id
    if release_root.is_symlink() or not release_root.is_dir():
        raise ValueError("source release root is missing or is a symlink")
    identity = _source_release_identity(release_root)
    if identity.release_id != source_release_id:
        raise ValueError("source release identity differs from requested releaseId")
    incident = read_json(identity_incident_path)
    validated_incident = validate_release_identity_incident(
        incident,
        output_root=output_root,
    )
    if (
        validated_incident.release_id != source_release_id
        or identity not in validated_incident.observed_identities
    ):
        raise ValueError("identity incident does not contain the source release tuple")

    evidence_paths = {
        field: release_root / suffix for field, suffix in _SOURCE_EVIDENCE.items()
    }
    evidence_documents = {
        field: read_json(evidence_path)
        for field, evidence_path in evidence_paths.items()
    }
    desired = _desired_refs(
        evidence_documents["desiredState"].get("desiredRefs"),
        label="desiredState.desiredRefs",
    )
    desired_document = {key: list(value) for key, value in desired.items()}
    reviews, rights = _expected_evidence(
        release_root=release_root,
        output_root=output_root,
        desired_refs=desired,
    )
    media_assets = _media_assets(
        evidence_documents["mediaManifest"].get("assets"),
        release_root=release_root,
        desired_refs=desired,
        rights_rows=rights,
    )
    header = evidence_documents["releaseHeader"]
    upstream = {
        "executionIds": list(header.get("executionIds") or []),
        "sourceDigests": list(header.get("sourceDigests") or []),
    }
    closure_digests = {
        "objects": objects_merkle(release_root),
        "media": canonical_digest(media_assets),
        "review": canonical_digest(reviews),
        "rights": canonical_digest(rights),
        "upstream": canonical_digest(upstream),
    }
    stable: dict[str, Any] = {
        "schema": "quwoquan_data.reviewed_closure_adoption_ref",
        "adoptionId": adoption_id,
        "sourceReleaseRootRef": _portable(release_root, output_root=output_root),
        "sourceReleaseIdentity": identity.to_document(),
        "identityIncident": {
            "ref": _portable(identity_incident_path, output_root=output_root),
            "fileSha256": file_digest(identity_incident_path),
            "receiptDigest": validated_incident.receipt_digest,
        },
        "sourceEvidence": {
            field: _file_binding(evidence_path, output_root=output_root)
            for field, evidence_path in evidence_paths.items()
        },
        "desiredRefs": desired_document,
        "mediaAssets": media_assets,
        "reviewEvidence": reviews,
        "rightsEvidence": rights,
        "upstreamProvenance": upstream,
        "closureDigests": closure_digests,
        "recordedAt": _utc_now(),
    }
    document = {**stable, "adoptionRefDigest": canonical_digest(stable)}
    validate_reviewed_closure_adoption_ref(document, output_root=output_root)
    write_json(path, document)
    return document, path


def _write_adoption_receipt(
    *,
    adoption_ref: Mapping[str, Any],
    adoption_ref_path: Path,
    execution_ids: Mapping[str, str],
    target_source: Mapping[str, Any],
    output_root: Path,
) -> tuple[dict[str, Any], Path]:
    root = adoption_ref_path.parent
    path = root / "adoption_receipt.json"
    desired = adoption_ref["desiredRefs"]
    lane_refs = {
        "homepage": [f"entities/{ref}" for ref in desired["entities"]],
        **{
            carrier: [
                f"posts/{ref}"
                for ref in desired["posts"]
                if ref.startswith(f"{carrier}/")
            ]
            for carrier in ("article", "image", "video")
        },
    }
    if path.is_file():
        existing = read_json(path)
        validated = validate_reviewed_closure_adoption_receipt(
            existing,
            output_root=output_root,
        )
        if (
            validated.adoption_id != adoption_ref["adoptionId"]
            or validated.lane_execution_ids
            != tuple(execution_ids[carrier] for carrier in execution_ids)
            or existing.get("targetSourceIdentity") != dict(target_source)
        ):
            raise ValueError("reviewed closure adoption receipt create-once conflict")
        return dict(existing), path
    stable: dict[str, Any] = {
        "schema": "quwoquan_data.reviewed_closure_adoption_receipt",
        "adoptionId": adoption_ref["adoptionId"],
        "adoptionRef": {
            "ref": _portable(adoption_ref_path, output_root=output_root),
            "fileSha256": file_digest(adoption_ref_path),
            "adoptionRefDigest": adoption_ref["adoptionRefDigest"],
        },
        "sourceReleaseIdentity": adoption_ref["sourceReleaseIdentity"],
        "targetSourceIdentity": dict(target_source),
        "laneExecutions": [
            {
                "carrier": carrier,
                "executionId": execution_ids[carrier],
                "adoptedObjectRefs": lane_refs[carrier],
            }
            for carrier in execution_ids
        ],
        "sharedObjectRefs": [
            *[f"creators/{ref}" for ref in desired["creators"]],
            *[f"tags/{ref}" for ref in desired["tags"]],
        ],
        "closureDigests": adoption_ref["closureDigests"],
        "upstreamProvenance": adoption_ref["upstreamProvenance"],
        "status": "passed",
        "recordedAt": _utc_now(),
    }
    document = {**stable, "receiptDigest": canonical_digest(stable)}
    validate_reviewed_closure_adoption_receipt(document, output_root=output_root)
    write_json(path, document)
    return document, path


def _campaign_binding(
    adoption_ref: Mapping[str, Any],
    adoption_ref_path: Path,
    receipt: Mapping[str, Any],
    receipt_path: Path,
    *,
    output_root: Path,
) -> dict[str, Any]:
    return {
        "adoptionId": adoption_ref["adoptionId"],
        "sourceReleaseIdentity": adoption_ref["sourceReleaseIdentity"],
        "adoptionRef": {
            "ref": _portable(adoption_ref_path, output_root=output_root),
            "fileSha256": file_digest(adoption_ref_path),
            "adoptionRefDigest": adoption_ref["adoptionRefDigest"],
        },
        "adoptionReceipt": {
            "ref": _portable(receipt_path, output_root=output_root),
            "fileSha256": file_digest(receipt_path),
            "receiptDigest": receipt["receiptDigest"],
        },
    }


def _write_task_binding(
    *,
    runtime: CampaignRuntimePaths,
    plan: Mapping[str, Any],
    carrier: str,
    execution_id: str,
    campaign_binding: Mapping[str, Any],
    adopted_refs: list[str],
    target_source: Mapping[str, Any],
) -> Path:
    path = (
        runtime.output_root
        / "data/tasks"
        / execution_id
        / "0.plan/reviewed_closure_adoption.json"
    )
    if path.is_file():
        existing = read_json(path)
        validate_adoption_task_binding(existing, output_root=runtime.output_root)
        if existing.get("planDigest") != plan["planDigest"] or existing.get(
            CAMPAIGN_ADOPTION_FIELD
        ) != dict(campaign_binding):
            raise ValueError("reviewed closure task binding create-once conflict")
        return path
    stable: dict[str, Any] = {
        "schema": "quwoquan_data.reviewed_closure_adoption_task_binding",
        "rootExecutionId": plan["rootExecutionId"],
        "executionId": execution_id,
        "carrier": carrier,
        "operation": ADOPTION_OPERATIONS[carrier],
        "planDigest": plan["planDigest"],
        CAMPAIGN_ADOPTION_FIELD: dict(campaign_binding),
        "adoptedObjectRefs": list(adopted_refs),
        "targetSourceIdentity": dict(target_source),
        "status": "adopted_reviewed_closure",
        "recordedAt": _utc_now(),
    }
    document = {**stable, "bindingDigest": canonical_digest(stable)}
    validate_adoption_task_binding(document, output_root=runtime.output_root)
    write_json(path, document)
    return path


def _completed_adoption(
    *,
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    plan_digest: str,
) -> bool:
    path = (
        campaign_root(root_execution_id, root=runtime.campaigns_root)
        / "runtime/snapshot.json"
    )
    if not path.is_file():
        return False
    snapshot = read_json(path)
    return (
        snapshot.get("status") == "succeeded"
        and snapshot.get("phase") == "completed"
        and snapshot.get("planDigest") == plan_digest
        and snapshot.get("failure") in {None, ""}
    )


def adopt_reviewed_closure(
    *,
    adoption_id: str,
    source_release_id: str,
    identity_incident_path: Path,
    execution_ids: Mapping[str, str],
    region_ref: str,
    runtime: CampaignRuntimePaths | None = None,
    lease_seconds: int = 30,
) -> dict[str, Any]:
    selected = runtime or CampaignRuntimePaths.defaults()
    active_carriers = normalize_active_carriers(execution_ids)
    if tuple(execution_ids) != active_carriers:
        raise ValueError("reviewed closure adoption lane IDs must use canonical order")
    identities = {
        carrier: parse_execution_id(execution_ids[carrier]) for carrier in active_carriers
    }
    verticals = {identity.vertical for identity in identities.values()}
    if len(verticals) != 1 or any(
        identities[carrier].content_type.value != carrier for carrier in active_carriers
    ):
        raise ValueError("reviewed closure lane carrier/vertical identity drift")
    root_carrier = active_carriers[0]
    root_execution_id = execution_ids[root_carrier]
    discovery = (
        selected.repo_root
        / "quwoquan_data/reference"
        / identities[root_carrier].vertical
        / "entities"
        / str(region_ref).strip().strip("/")
    )
    catalog_digest = entity_catalog_digest(
        discovery.relative_to(selected.repo_root).as_posix()
    )
    source = current_source_definition_snapshot(
        repo_root=selected.repo_root
    ).to_document()
    frozen_branch = current_branch(selected.repo_root)
    frozen_commit = current_commit(selected.repo_root)
    target_source = {
        "sourceRevision": content_source_revision(
            source_digest=str(source["digest"]),
            entity_catalog_digest=catalog_digest,
        ),
        "sourceDigest": source,
        "entityCatalogDigest": catalog_digest,
    }
    root = adoption_root(selected.output_root, adoption_id)
    if identity_incident_path.is_symlink():
        raise ValueError("identity incident cannot be a symlink")
    incident_path = identity_incident_path.resolve(strict=True)
    source_release_root = selected.output_root / "data/releases"
    with (
        release_identity_protection_lock(
            output_root=selected.output_root,
            exclusive=True,
        ),
        release_operation_guard(
            lock_root=release_operation_lock_root(source_release_root),
            release_ids=(source_release_id,),
            exclusive_releases=True,
        ),
        _adoption_lock(root),
    ):
        adoption_ref, adoption_ref_path = _write_adoption_ref(
            adoption_id=adoption_id,
            source_release_id=source_release_id,
            identity_incident_path=incident_path,
            output_root=selected.output_root,
        )
        receipt, receipt_path = _write_adoption_receipt(
            adoption_ref=adoption_ref,
            adoption_ref_path=adoption_ref_path,
            execution_ids=execution_ids,
            target_source=target_source,
            output_root=selected.output_root,
        )
        binding = _campaign_binding(
            adoption_ref,
            adoption_ref_path,
            receipt,
            receipt_path,
            output_root=selected.output_root,
        )
        validate_campaign_adoption_binding(binding, output_root=selected.output_root)
        for carrier in active_carriers:
            write_adoption_submission(
                root_execution_id=root_execution_id,
                execution_id=execution_ids[carrier],
                region_ref=region_ref,
                reviewed_closure_adoption=binding,
                repo_root=selected.repo_root,
                output_root=selected.output_root,
                root=selected.campaigns_root,
                frozen_source_identity=source,
                git_branch=frozen_branch,
                git_commit_sha=frozen_commit,
            )
        submissions = load_submissions(
            root_execution_id,
            root=selected.campaigns_root,
        )
        plan, _plan_digest = freeze_plan(selected, root_execution_id, submissions)
        lane_refs = adopted_object_refs(receipt)
        for carrier in active_carriers:
            _write_task_binding(
                runtime=selected,
                plan=plan,
                carrier=carrier,
                execution_id=execution_ids[carrier],
                campaign_binding=binding,
                adopted_refs=lane_refs[carrier],
                target_source=target_source,
            )
        if not _completed_adoption(
            runtime=selected,
            root_execution_id=root_execution_id,
            plan_digest=str(plan["planDigest"]),
        ):
            with campaign_run_session(
                selected,
                root_execution_id,
                lease_seconds=lease_seconds,
            ) as session:
                session.campaign_checkpoint(
                    phase="publish",
                    plan_digest=str(plan["planDigest"]),
                )
                for carrier in active_carriers:
                    lane_execution_root = (
                        selected.output_root / "data/tasks" / execution_ids[carrier]
                    )
                    session.lane_checkpoint(
                        carrier=carrier,
                        execution_id=execution_ids[carrier],
                        phase="run",
                        status="succeeded",
                        capsule_ref=binding["adoptionRef"]["ref"],
                        execution_root=lane_execution_root,
                        return_code=0,
                    )
                    write_adoption_publish_receipt(
                        root_execution_id=root_execution_id,
                        execution_id=execution_ids[carrier],
                        reviewed_closure_adoption=binding,
                        adopted_object_refs=lane_refs[carrier],
                        run_session=session,
                    )
                session.finish(status="succeeded", phase="completed", failure=None)
        from content.release.canonical.campaign_release import (
            validate_reviewed_closure_campaign_selection,
        )
        from content.release.canonical.campaign_release_contract import (
            CampaignReleaseRoots,
        )

        selection = validate_reviewed_closure_campaign_selection(
            root_execution_id=root_execution_id,
            roots=CampaignReleaseRoots(
                output_root=selected.output_root,
                campaigns_root=selected.campaigns_root,
                tasks_root=selected.output_root / "data/tasks",
                publish_root=selected.publish_root,
                release_root=selected.output_root / "data/releases",
            ),
        )
        return {
            "schema": "quwoquan_data.reviewed_closure_adoption_campaign_result",
            "adoptionId": adoption_id,
            "rootExecutionId": root_execution_id,
            "planDigest": plan["planDigest"],
            "adoptionRef": binding["adoptionRef"],
            "adoptionReceipt": binding["adoptionReceipt"],
            "status": "campaign_evidence_ready",
            "selectionDigest": selection["selectionDigest"],
            "releaseCreated": False,
        }


def handle_adopt_reviewed_closure(args: argparse.Namespace) -> None:
    try:
        result = adopt_reviewed_closure(
            adoption_id=str(args.adoption_id),
            source_release_id=str(args.source_release_id),
            identity_incident_path=Path(args.identity_incident).expanduser(),
            execution_ids={
                "homepage": str(args.execution_id),
                "article": str(args.article_execution_id),
                "image": str(args.image_execution_id),
                "video": str(args.video_execution_id),
            },
            region_ref=str(args.region_ref),
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(
            f"[task execute] GATE_BLOCK reviewed closure adoption: {exc}"
        ) from exc
    import json

    print(json.dumps(result, ensure_ascii=False, indent=2))


__all__ = [
    "adopt_reviewed_closure",
    "adoption_root",
    "handle_adopt_reviewed_closure",
]
