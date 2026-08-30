"""Campaign stage boundaries record revision drift instead of blocking (DEC-030).

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/design.md#dec-030
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import content.execution.campaign.workspace as workspace
from content.execution.campaign.plan import write_report
from content.execution.campaign.workspace import (
    CampaignRuntimePaths,
    audit_frozen_revision,
)
from core.io import read_json

_FROZEN_COMMIT = "a" * 40
_FROZEN_SOURCE = "sha256:" + "b" * 64
_FROZEN_BUNDLE = "sha256:" + "c" * 64


def _patch_observed(
    monkeypatch: pytest.MonkeyPatch,
    *,
    branch: str,
    commit: str,
    source: str,
    bundle: str,
) -> None:
    monkeypatch.setattr(workspace, "current_branch", lambda _repo: branch)
    monkeypatch.setattr(workspace, "current_commit", lambda _repo: commit)
    monkeypatch.setattr(
        workspace,
        "current_source_definition_snapshot",
        lambda **_kwargs: SimpleNamespace(digest=source),
    )
    import core.source_digest as source_digest

    monkeypatch.setattr(
        source_digest,
        "current_execution_bundle_identity",
        lambda **_kwargs: SimpleNamespace(digest=bundle),
    )


def test_commit_and_digest_drift_is_recorded_not_blocking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    drifted_commit = "d" * 40
    drifted_source = "sha256:" + "e" * 64
    drifted_bundle = "sha256:" + "f" * 64
    _patch_observed(
        monkeypatch,
        branch="dev1.0",
        commit=drifted_commit,
        source=drifted_source,
        bundle=drifted_bundle,
    )
    audit = audit_frozen_revision(
        tmp_path,
        phase="publish",
        git_branch="dev1.0",
        commit_sha=_FROZEN_COMMIT,
        source_digest=_FROZEN_SOURCE,
        execution_bundle_digest=_FROZEN_BUNDLE,
    )
    assert audit["drifted"] is True
    assert audit["phase"] == "publish"
    assert audit["frozenCommitSha"] == _FROZEN_COMMIT
    assert audit["observedCommitSha"] == drifted_commit
    assert audit["frozenSourceDigest"] == _FROZEN_SOURCE
    assert audit["observedSourceDigest"] == drifted_source
    assert audit["frozenExecutionBundleDigest"] == _FROZEN_BUNDLE
    assert audit["observedExecutionBundleDigest"] == drifted_bundle


def test_matching_revision_yields_undrifted_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_observed(
        monkeypatch,
        branch="dev1.0",
        commit=_FROZEN_COMMIT,
        source=_FROZEN_SOURCE,
        bundle=_FROZEN_BUNDLE,
    )
    audit = audit_frozen_revision(
        tmp_path,
        phase="review",
        git_branch="dev1.0",
        commit_sha=_FROZEN_COMMIT,
        source_digest=_FROZEN_SOURCE,
        execution_bundle_digest=_FROZEN_BUNDLE,
    )
    assert audit["drifted"] is False
    assert audit["phase"] == "review"


def test_branch_drift_remains_a_hard_precondition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_observed(
        monkeypatch,
        branch="main",
        commit=_FROZEN_COMMIT,
        source=_FROZEN_SOURCE,
        bundle=_FROZEN_BUNDLE,
    )
    with pytest.raises(ValueError, match="campaign branch drift"):
        audit_frozen_revision(
            tmp_path,
            phase="review",
            git_branch="dev1.0",
            commit_sha=_FROZEN_COMMIT,
            source_digest=_FROZEN_SOURCE,
            execution_bundle_digest=_FROZEN_BUNDLE,
        )


def _runtime(tmp_path: Path) -> CampaignRuntimePaths:
    runtime = CampaignRuntimePaths(
        repo_root=tmp_path / "repo",
        output_root=tmp_path / "out",
        publish_root=tmp_path / "publish",
        campaigns_root=tmp_path / "campaigns",
        workspaces_root=tmp_path / "workspaces",
    )
    runtime.campaigns_root.mkdir(parents=True, exist_ok=True)
    return runtime


def _lane(execution_id: str) -> dict[str, object]:
    return {
        "executionId": execution_id,
        "status": "pending",
        "phase": "submission",
        "reviewReturnCode": None,
        "publishReturnCode": None,
        "sourceCapsuleRef": None,
        "sourceCapsuleDigest": None,
        "sourceCapsuleCommitSha": None,
        "sourceCapsuleSourceDigest": None,
        "sourceCapsuleReadOnly": None,
        "executionRootRef": None,
        "cleanupStatus": "not_created",
        "approvedQuota": None,
        "qualifiedCount": None,
        "finalizedCount": None,
        "selectedCount": None,
        "discardedCount": None,
        "shortfallCount": None,
        "deliveryPendingCount": 0,
        "deliveryIntentRefs": [],
        "error": None,
    }


def test_report_schema_carries_revision_audits(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    root_id = "20260825--travel-homepage-m1-first--sichuan--pilot-901"
    audit = {
        "phase": "publish",
        "observedAt": "2026-08-25T12:00:00Z",
        "gitBranch": "dev1.0",
        "frozenCommitSha": _FROZEN_COMMIT,
        "observedCommitSha": "d" * 40,
        "frozenSourceDigest": _FROZEN_SOURCE,
        "observedSourceDigest": "sha256:" + "e" * 64,
        "frozenExecutionBundleDigest": _FROZEN_BUNDLE,
        "observedExecutionBundleDigest": "sha256:" + "f" * 64,
        "drifted": True,
    }
    path = write_report(
        runtime,
        root_id,
        status="running",
        phase="publish",
        plan_digest="sha256:" + "1" * 64,
        git_branch="dev1.0",
        git_commit_sha=_FROZEN_COMMIT,
        source_digest=_FROZEN_SOURCE,
        entity_catalog_digest="sha256:" + "2" * 64,
        lanes={"homepage": _lane(root_id)},
        started_at="2026-08-25T11:00:00Z",
        failure=None,
        active_carriers=("homepage",),
        workloads={"homepage": 1},
        revision_audits=[audit],
    )
    payload = read_json(path)
    assert payload["revisionAudits"] == [audit]


def test_report_defaults_to_empty_revision_audits(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    root_id = "20260825--travel-homepage-m1-first--sichuan--pilot-902"
    path = write_report(
        runtime,
        root_id,
        status="running",
        phase="capsule",
        plan_digest=None,
        git_branch=None,
        git_commit_sha=None,
        source_digest=None,
        entity_catalog_digest=None,
        lanes={"homepage": _lane(root_id)},
        started_at="2026-08-25T11:00:00Z",
        failure=None,
        active_carriers=("homepage",),
        workloads={"homepage": 1},
    )
    payload = read_json(path)
    assert payload["revisionAudits"] == []
