"""Select one aggregate release only from a frozen four-lane campaign.

Callers provide a campaign root and a new release identity.  Execution IDs are
derived from the immutable campaign plan; there is deliberately no public
parameter that can mix lanes by hand.
"""

from __future__ import annotations

import fcntl
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content.execution.campaign.lane import CAMPAIGN_CARRIERS
from content.execution.identity import validate_execution_id
from content.execution.closure.adoption_campaign_contract import (
    CAMPAIGN_ADOPTION_FIELD,
)
from content.release.canonical.aggregate_release import build_aggregate_release
from content.release.canonical.campaign_release_contract import (
    PUBLISH_BINDING_CONTRACT_REQUEST,
    CampaignReleaseError,
    CampaignReleaseRoots,
    selection_attestation_path,
)
from content.release.canonical.campaign_release_contract import (
    canonical_digest as _canonical_digest,
)
from content.release.canonical.campaign_release_contract import (
    output_ref as _output_ref,
)
from content.release.canonical.campaign_release_contract import (
    read_regular as _read_regular,
)
from content.release.canonical.campaign_release_contract import (
    typed_error as _typed,
)
from content.release.canonical.campaign_release_publish import validate_lane_publish
from content.release.canonical.campaign_release_selection import (
    retry_lineage,
    validate_plan,
    validate_runtime,
    validate_submissions,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _safe_id,
)
from content.release.canonical.object_transaction_lock import canonical_publish_lock
from content.release.canonical.release_operation_lock import (
    ReleaseOperationConflict,
    release_operation_guard,
    release_operation_lock_root,
)
from core.io import write_json
from core.release_layout import payload_digest as release_payload_digest
@contextmanager
def _selection_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_attestation(path: Path, stable: Mapping[str, Any]) -> dict[str, Any]:
    if path.is_file():
        existing = _read_regular(path, label="campaign release selection attestation")
        expected_keys = {*stable, "recordedAt", "selectionDigest"}
        if set(existing) != expected_keys or not isinstance(
            existing.get("recordedAt"), str
        ) or not str(existing["recordedAt"]).strip():
            raise _typed(
                "ATTESTATION_CONFLICT",
                "create-once selection shape differs",
                evidence=path,
            )
        digest_input = {
            key: value for key, value in existing.items() if key != "selectionDigest"
        }
        if existing.get("selectionDigest") != _canonical_digest(digest_input):
            raise _typed(
                "ATTESTATION_DIGEST_DRIFT",
                "selection attestation digest drift",
                evidence=path,
            )
        if any(existing.get(key) != value for key, value in stable.items()):
            raise _typed(
                "ATTESTATION_CONFLICT", "create-once selection differs", evidence=path
            )
        return existing
    document = {**dict(stable), "recordedAt": datetime.now(timezone.utc).isoformat()}
    document["selectionDigest"] = _canonical_digest(document)
    write_json(path, document)
    return document


def validate_reviewed_closure_campaign_selection(
    *,
    root_execution_id: str,
    roots: CampaignReleaseRoots | None = None,
) -> dict[str, Any]:
    """Validate fenced adoption selection without creating a release."""

    try:
        root_id = validate_execution_id(root_execution_id)
    except ValueError as exc:
        raise _typed("IDENTITY_INVALID", str(exc)) from exc
    selected_roots = (roots or CampaignReleaseRoots.defaults()).validated()
    plan, _plan_path = validate_plan(root_id, roots=selected_roots)
    if plan.get(CAMPAIGN_ADOPTION_FIELD) is None:
        raise _typed(
            "ADOPTION_BINDING_INVALID",
            "campaign plan is not a reviewed-closure adoption",
        )
    submissions = validate_submissions(root_id, plan, roots=selected_roots)
    snapshot, _checkpoints = validate_runtime(
        root_id,
        plan,
        roots=selected_roots,
    )
    lineage = {
        carrier: retry_lineage(
            carrier,
            str(plan["executionIds"][carrier]),
            submissions[carrier],
            plan,
            roots=selected_roots,
        )
        for carrier in CAMPAIGN_CARRIERS
    }
    lanes = {
        carrier: validate_lane_publish(
            root_id,
            carrier,
            plan,
            submissions[carrier],
            snapshot,
            roots=selected_roots,
        )
        for carrier in CAMPAIGN_CARRIERS
    }
    stable = {
        "schema": "quwoquan_data.reviewed_closure_campaign_selection",
        "rootExecutionId": root_id,
        "planDigest": plan["planDigest"],
        "sourceRevision": plan["sourceRevision"],
        "sourceDigest": plan["sourceDigest"],
        "entityCatalogDigest": plan["entityCatalogDigest"],
        CAMPAIGN_ADOPTION_FIELD: plan[CAMPAIGN_ADOPTION_FIELD],
        "campaignRun": {
            "runId": snapshot["runId"],
            "generation": snapshot["generation"],
            "fencingToken": snapshot["fencingToken"],
        },
        "executionIds": dict(plan["executionIds"]),
        "retryLineage": lineage,
        "lanes": lanes,
        "releaseCreated": False,
    }
    return {**stable, "selectionDigest": _canonical_digest(stable)}


def build_campaign_release(
    *,
    root_execution_id: str,
    release_id: str,
    roots: CampaignReleaseRoots | None = None,
    target_environment: str | None = None,
) -> dict[str, Any]:
    """Build a release from the exact current four-lane campaign selection."""

    try:
        root_id = validate_execution_id(root_execution_id)
        release_id = _safe_id(release_id, label="releaseId")
    except (ObjectTransactionError, ValueError) as exc:
        raise _typed("IDENTITY_INVALID", str(exc)) from exc
    selected_roots = (roots or CampaignReleaseRoots.defaults()).validated()
    selection_path = selection_attestation_path(
        root_id, release_id, roots=selected_roots
    )
    lock_path = selection_path.parent / f".{release_id}.lock"
    with _selection_lock(lock_path):
        release_path = selected_roots.release_root / release_id
        selection_exists = selection_path.exists() or selection_path.is_symlink()
        if selection_exists and not release_path.is_dir():
            raise _typed(
                "ATTESTATION_CONFLICT",
                "selection attestation cannot exist before its immutable release",
                evidence=selection_path,
            )
        plan, _plan_path = validate_plan(root_id, roots=selected_roots)
        adoption_document = plan.get(CAMPAIGN_ADOPTION_FIELD)
        if (
            adoption_document is not None
            and (adoption_document.get("sourceReleaseIdentity") or {}).get("releaseId")
            == release_id
        ):
            raise _typed(
                "IDENTITY_REUSE_FORBIDDEN",
                "a collided source releaseId cannot be reused for the new release",
                evidence=_plan_path,
            )
        submissions = validate_submissions(root_id, plan, roots=selected_roots)
        snapshot, _checkpoints = validate_runtime(root_id, plan, roots=selected_roots)
        lineage = {
            carrier: retry_lineage(
                carrier,
                str(plan["executionIds"][carrier]),
                submissions[carrier],
                plan,
                roots=selected_roots,
            )
            for carrier in CAMPAIGN_CARRIERS
        }
        try:
            guarded_release_ids = (release_id,)
            if adoption_document is not None:
                source_release_id = str(
                    (adoption_document.get("sourceReleaseIdentity") or {}).get(
                        "releaseId"
                    )
                    or ""
                )
                guarded_release_ids = (source_release_id, release_id)
            publish_guard = (
                nullcontext()
                if adoption_document is not None
                else canonical_publish_lock(selected_roots.publish_root)
            )
            with (
                release_operation_guard(
                    lock_root=release_operation_lock_root(selected_roots.release_root),
                    release_ids=guarded_release_ids,
                    exclusive_releases=True,
                ),
                publish_guard,
            ):
                lanes = {
                    carrier: validate_lane_publish(
                        root_id,
                        carrier,
                        plan,
                        submissions[carrier],
                        snapshot,
                        roots=selected_roots,
                    )
                    for carrier in CAMPAIGN_CARRIERS
                }
                execution_ids = {
                    carrier: str(plan["executionIds"][carrier])
                    for carrier in CAMPAIGN_CARRIERS
                }
                aggregate = build_aggregate_release(
                    publish_root=selected_roots.publish_root,
                    release_root=selected_roots.release_root,
                    release_id=release_id,
                    execution_ids=list(execution_ids.values()),
                    source_revision=str(plan["sourceRevision"]),
                    entity_catalog_digest=str(plan["entityCatalogDigest"]),
                    reviewed_closure_adoption=adoption_document,
                    adoption_output_root=selected_roots.output_root,
                    target_environment=target_environment,
                )
                manifest_digest = release_payload_digest(release_path)
                stable = {
                    "schema": "quwoquan_data.campaign_release_selection_attestation",
                    "rootExecutionId": root_id,
                    "releaseId": release_id,
                    "planDigest": plan["planDigest"],
                    "sourceRevision": plan["sourceRevision"],
                    "sourceDigest": plan["sourceDigest"],
                    "entityCatalogDigest": plan["entityCatalogDigest"],
                    "externalInputsDigest": plan["externalInputsDigest"],
                    "campaignRun": {
                        "runId": snapshot["runId"],
                        "generation": snapshot["generation"],
                        "fencingToken": snapshot["fencingToken"],
                    },
                    "executionIds": execution_ids,
                    "retryLineage": lineage,
                    "lanes": lanes,
                    "releaseRootRef": _output_ref(
                        release_path / "payload/release.json",
                        roots=selected_roots,
                        label="aggregate release header",
                    ),
                    "manifestDigest": manifest_digest,
                    "canonicalMerkle": aggregate["canonicalMerkle"],
                }
                if adoption_document is not None:
                    stable[CAMPAIGN_ADOPTION_FIELD] = adoption_document
                if target_environment is not None:
                    stable["targetEnvironment"] = target_environment
                attestation = _write_attestation(selection_path, stable)
        except CampaignReleaseError:
            raise
        except (
            FileNotFoundError,
            OSError,
            ObjectTransactionError,
            ReleaseOperationConflict,
            TypeError,
            ValueError,
        ) as exc:
            raise _typed("AGGREGATE_BLOCKED", str(exc)) from exc
    return {
        **aggregate,
        "rootExecutionId": root_id,
        "manifestDigest": manifest_digest,
        "campaignSelectionAttestation": str(selection_path),
        "campaignSelectionDigest": attestation["selectionDigest"],
    }


__all__ = [
    "PUBLISH_BINDING_CONTRACT_REQUEST",
    "CampaignReleaseError",
    "CampaignReleaseRoots",
    "build_campaign_release",
    "selection_attestation_path",
    "validate_reviewed_closure_campaign_selection",
]
