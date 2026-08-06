"""Reviewed-closure adoption submission implementation behind the campaign facade."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core import paths
from core.io import read_json, write_json
from core.schema import assert_valid
from core.source_digest import current_source_digest

from content.execution.campaign_external_inputs import (
    content_source_revision,
    external_inputs_digest,
)
from content.execution.identity import parse_execution_id
from content.execution.reviewed_closure_adoption_campaign_contract import (
    ADOPTION_OPERATIONS,
    CAMPAIGN_ADOPTION_FIELD,
    adopted_object_refs,
    validate_adoption_target_identity,
    validate_campaign_adoption_binding,
)
from content.execution.workspace import entity_catalog_digest


def write_adoption_submission(
    *,
    root_execution_id: str,
    execution_id: str,
    region_ref: str,
    reviewed_closure_adoption: Mapping[str, Any],
    repo_root: Path | None = None,
    output_root: Path | None = None,
    root: Path | None = None,
    frozen_source_identity: Mapping[str, Any] | None = None,
    git_branch: str | None = None,
    git_commit_sha: str | None = None,
) -> Path:
    from content.execution.campaign_submission import (
        SUBMISSION_SCHEMA,
        _assert_no_cross_campaign_collision,
        _git_branch,
        _git_commit,
        _require_stable_source_inputs,
        _sha256,
        _submission_lock,
        _utc_now,
        campaigns_root,
        submission_path,
    )

    source_repo = (repo_root or paths.REPO_ROOT).resolve()
    selected_output = (output_root or paths.OUTPUT_ROOT).resolve()
    campaigns_dir = root or campaigns_root()
    root_identity = parse_execution_id(root_execution_id)
    identity = parse_execution_id(execution_id)
    carrier = identity.content_type.value
    if (
        root_identity.content_type.value != "homepage"
        or identity.vertical != root_identity.vertical
        or carrier not in ADOPTION_OPERATIONS
    ):
        raise ValueError("reviewed closure campaign lane identity is invalid")
    binding = validate_campaign_adoption_binding(
        reviewed_closure_adoption,
        output_root=selected_output,
    )
    receipt_document = read_json(binding.receipt_path)
    lane_refs = adopted_object_refs(receipt_document)
    expected_execution_ids = {
        str(row["carrier"]): str(row["executionId"])
        for row in receipt_document["laneExecutions"]
    }
    if (
        expected_execution_ids.get("homepage") != root_identity.execution_id
        or expected_execution_ids.get(carrier) != identity.execution_id
    ):
        raise ValueError("reviewed closure receipt lane identity drift")
    source = (
        dict(frozen_source_identity)
        if frozen_source_identity is not None
        else current_source_digest(repo_root=source_repo).to_document()
    )
    if frozen_source_identity is None:
        _require_stable_source_inputs(source, repo_root=source_repo)
    discovery = (
        source_repo
        / "quwoquan_data/reference"
        / identity.vertical
        / "entities"
        / str(region_ref).strip().strip("/")
    )
    catalog_digest = entity_catalog_digest(
        discovery.relative_to(source_repo).as_posix()
    )
    source_revision = content_source_revision(
        source_digest=str(source["digest"]),
        entity_catalog_digest=catalog_digest,
    )
    validate_adoption_target_identity(
        {
            "sourceRevision": source_revision,
            "sourceDigest": source,
            "entityCatalogDigest": catalog_digest,
        },
        binding=binding,
    )
    refs = lane_refs[carrier]
    stable: dict[str, Any] = {
        "schema": SUBMISSION_SCHEMA,
        "rootExecutionId": root_identity.execution_id,
        "executionId": identity.execution_id,
        "operation": ADOPTION_OPERATIONS[carrier],
        "carrier": carrier,
        "familyRef": f"content/{identity.vertical}/{carrier}/{carrier}",
        "regionRef": str(region_ref).strip().strip("/"),
        "selector": "reviewed-closure",
        "quota": len(refs),
        "count": len(refs),
        "topic": None,
        "targetNames": list(refs),
        "sourceProviders": [],
        "semanticSelectionId": "not_applicable",
        "retryOf": None,
        "gitBranch": git_branch or _git_branch(source_repo),
        "gitCommitSha": git_commit_sha or _git_commit(source_repo),
        "sourceRevision": source_revision,
        "sourceDigest": source,
        "entityCatalogDigest": catalog_digest,
        "externalInputRefs": [],
        "externalInputsDigest": external_inputs_digest([]),
        CAMPAIGN_ADOPTION_FIELD: dict(reviewed_closure_adoption),
    }
    request_digest = _sha256(stable)
    path = submission_path(
        root_identity.execution_id,
        identity.execution_id,
        root=campaigns_dir,
    )
    with _submission_lock(campaigns_dir):
        if frozen_source_identity is None:
            _require_stable_source_inputs(source, repo_root=source_repo)
        _assert_no_cross_campaign_collision(
            campaigns_dir=campaigns_dir,
            root_execution_id=root_identity.execution_id,
            execution_id=identity.execution_id,
        )
        if path.is_file():
            existing = read_json(path)
            assert_valid(
                existing,
                "execution",
                "content_execution_submission",
                label=f"campaign adoption submission:{identity.execution_id}",
            )
            if existing.get("requestDigest") != request_digest or any(
                existing.get(key) != value for key, value in stable.items()
            ):
                raise ValueError("reviewed closure submission create-once conflict")
            return path
        payload = {**stable, "requestDigest": request_digest, "submittedAt": _utc_now()}
        assert_valid(
            payload,
            "execution",
            "content_execution_submission",
            label=f"campaign adoption submission:{identity.execution_id}",
        )
        write_json(path, payload)
    return path


__all__ = ["write_adoption_submission"]
