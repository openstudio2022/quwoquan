# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
"""Resuming a frozen campaign capsule from immutable bytes only.

`REQ-001` freezes one read-only, content-addressed source capsule per campaign
and states that once sealed, live worktree drift must not invalidate that
execution; `campaign-freeze` freezes the single plan, the read-only capsule and
its `planDigest`, and any branch/commit/source/catalog mismatch must fail
closed.  `GWT-001` adds that the capsule is created once and that a stale or
drifted capsule reference is rejected.

These tests exercise the reload guard layer of the resume path, which resolves
the capsule strictly against the content-addressed root and the frozen plan
identity.  They deliberately point `repo_root` at a path that does not exist:
resume must be decided by capsule bytes, never by the current source tree.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from content.execution.campaign.capsule_reload import load_source_capsule
from content.execution.campaign.workspace import CampaignRuntimePaths
from core.io import write_json

CAPSULES_DIR = "content-addressed-capsules"
GIT_BRANCH = "dev1.0"
COMMIT_SHA = "0" * 40
SOURCE_DIGEST = "sha256:" + "a" * 64
SOURCE_REVISION = "sha256:" + "b" * 64
ENTITY_CATALOG_DIGEST = "sha256:" + "c" * 64
EXTERNAL_INPUTS_DIGEST = "sha256:" + "d" * 64
EXECUTION_BUNDLE = {"digest": "sha256:" + "e" * 64}
CAPSULE_DIGEST = "sha256:" + "f" * 64
CARRIERS = ("homepage", "article", "image", "video")


def _runtime(tmp_path: Path) -> CampaignRuntimePaths:
    output_root = tmp_path / "output"
    return CampaignRuntimePaths(
        repo_root=tmp_path / "repo-that-does-not-exist",
        output_root=output_root,
        publish_root=tmp_path / "publish",
        campaigns_root=(
            output_root / "data/local/workspace/content-campaign-submissions"
        ),
        workspaces_root=output_root / "data/local/cache/campaign-workspaces",
    )


def _lane_external_inputs(
    carriers: tuple[str, ...] = CARRIERS,
) -> dict[str, dict[str, Any]]:
    return {
        carrier: {
            "rootRef": f"external-inputs/{carrier}",
            "externalInputRefs": [f"acquisition/{carrier}/unit.json"],
            "externalInputsDigest": "sha256:"
            + hashlib.sha256(carrier.encode("utf-8")).hexdigest(),
        }
        for carrier in carriers
    }


def _frozen_identity() -> dict[str, Any]:
    return {
        "gitBranch": GIT_BRANCH,
        "gitCommitSha": COMMIT_SHA,
        "sourceRevision": SOURCE_REVISION,
        "sourceDigest": SOURCE_DIGEST,
        "executionBundle": dict(EXECUTION_BUNDLE),
        "entityCatalogDigest": ENTITY_CATALOG_DIGEST,
        "externalInputsDigest": EXTERNAL_INPUTS_DIGEST,
    }


def _seal_capsule(
    runtime: CampaignRuntimePaths,
    *,
    lane_external_inputs: dict[str, dict[str, Any]],
    capsule_digest: str = CAPSULE_DIGEST,
    identity_overrides: dict[str, Any] | None = None,
) -> str:
    key = capsule_digest.removeprefix("sha256:")
    capsule_path = runtime.workspaces_root / CAPSULES_DIR / key
    manifest = {
        **_frozen_identity(),
        **(identity_overrides or {}),
        "laneExternalInputs": lane_external_inputs,
        "capsuleDigest": capsule_digest,
        "treeDigest": "sha256:" + "9" * 64,
    }
    write_json(capsule_path / ".qwq_campaign_capsule.json", manifest)
    return capsule_path.resolve().relative_to(
        runtime.output_root.resolve()
    ).as_posix()


def _resume(
    runtime: CampaignRuntimePaths,
    *,
    capsule_ref: str,
    capsule_digest: str = CAPSULE_DIGEST,
    lane_external_inputs: dict[str, dict[str, Any]] | None = None,
    **overrides: Any,
) -> Any:
    identity = {
        "git_branch": GIT_BRANCH,
        "commit_sha": COMMIT_SHA,
        "source_revision": SOURCE_REVISION,
        "source_digest": SOURCE_DIGEST,
        "execution_bundle": dict(EXECUTION_BUNDLE),
        "entity_catalog_digest": ENTITY_CATALOG_DIGEST,
        "external_inputs_digest": EXTERNAL_INPUTS_DIGEST,
    }
    identity.update(overrides)
    return load_source_capsule(
        runtime,
        capsule_ref=capsule_ref,
        capsule_digest=capsule_digest,
        lane_external_inputs=(
            lane_external_inputs
            if lane_external_inputs is not None
            else _lane_external_inputs()
        ),
        **identity,
    )


def test_resume_never_consults_the_live_source_tree(tmp_path: Path) -> None:
    """A sealed capsule must not be invalidated by the current worktree."""

    runtime = _runtime(tmp_path)
    assert not runtime.repo_root.exists()
    capsule_ref = _seal_capsule(
        runtime,
        lane_external_inputs=_lane_external_inputs(),
    )

    with pytest.raises(ValueError, match="plan identity drift"):
        _resume(
            runtime,
            capsule_ref=capsule_ref,
            commit_sha="1" * 40,
        )


@pytest.mark.parametrize(
    "override",
    [
        {"git_branch": "main"},
        {"commit_sha": "1" * 40},
        {"source_revision": "sha256:" + "1" * 64},
        {"source_digest": "sha256:" + "1" * 64},
        {"execution_bundle": {"digest": "sha256:" + "1" * 64}},
        {"entity_catalog_digest": "sha256:" + "1" * 64},
        {"external_inputs_digest": "sha256:" + "1" * 64},
    ],
)
def test_every_frozen_identity_field_is_compared_on_resume(
    tmp_path: Path,
    override: dict[str, Any],
) -> None:
    """Branch/commit/source/catalog mismatch must all fail closed."""

    runtime = _runtime(tmp_path)
    capsule_ref = _seal_capsule(
        runtime,
        lane_external_inputs=_lane_external_inputs(),
    )

    with pytest.raises(ValueError, match="plan identity drift"):
        _resume(runtime, capsule_ref=capsule_ref, **override)


def test_an_absolute_capsule_ref_is_rejected(tmp_path: Path) -> None:
    """The capsule ref is portable and relative to the governed output root."""

    runtime = _runtime(tmp_path)
    _seal_capsule(runtime, lane_external_inputs=_lane_external_inputs())

    with pytest.raises(ValueError, match="capsule ref is unsafe"):
        _resume(runtime, capsule_ref="/tmp/capsule")


def test_a_traversing_capsule_ref_is_rejected(tmp_path: Path) -> None:
    """Path traversal may not reach bytes outside the output root."""

    runtime = _runtime(tmp_path)
    _seal_capsule(runtime, lane_external_inputs=_lane_external_inputs())

    with pytest.raises(ValueError, match="capsule ref is unsafe"):
        _resume(
            runtime,
            capsule_ref=f"data/local/cache/../../{CAPSULES_DIR}/"
            + CAPSULE_DIGEST.removeprefix("sha256:"),
        )


def test_a_capsule_outside_the_content_addressed_root_is_rejected(
    tmp_path: Path,
) -> None:
    """Only the single canonical content-addressed root may host a capsule."""

    runtime = _runtime(tmp_path)
    key = CAPSULE_DIGEST.removeprefix("sha256:")
    stray = runtime.workspaces_root / "hand-made-capsules" / key
    write_json(
        stray / ".qwq_campaign_capsule.json",
        {**_frozen_identity(), "laneExternalInputs": _lane_external_inputs()},
    )
    stray_ref = stray.resolve().relative_to(
        runtime.output_root.resolve()
    ).as_posix()

    with pytest.raises(ValueError, match="outside the canonical root"):
        _resume(runtime, capsule_ref=stray_ref)


def test_a_capsule_directory_name_that_is_not_the_digest_is_rejected(
    tmp_path: Path,
) -> None:
    """Content addressing binds the directory name to the capsule digest."""

    runtime = _runtime(tmp_path)
    misnamed = runtime.workspaces_root / CAPSULES_DIR / ("b" * 64)
    write_json(
        misnamed / ".qwq_campaign_capsule.json",
        {**_frozen_identity(), "laneExternalInputs": _lane_external_inputs()},
    )
    misnamed_ref = misnamed.resolve().relative_to(
        runtime.output_root.resolve()
    ).as_posix()

    with pytest.raises(ValueError, match="ref/digest drift"):
        _resume(runtime, capsule_ref=misnamed_ref)


def test_a_malformed_capsule_digest_is_rejected(tmp_path: Path) -> None:
    """A truncated digest may not resolve to a capsule."""

    runtime = _runtime(tmp_path)
    capsule_ref = _seal_capsule(
        runtime,
        lane_external_inputs=_lane_external_inputs(),
    )

    with pytest.raises(ValueError, match="ref/digest drift"):
        _resume(
            runtime,
            capsule_ref=capsule_ref,
            capsule_digest="sha256:" + "f" * 63,
        )


def test_a_capsule_with_an_unknown_lane_fails_closed(tmp_path: Path) -> None:
    """No hidden lane may appear on resume."""

    lanes = _lane_external_inputs(("homepage", "article"))
    lanes["podcast"] = {
        "rootRef": "external-inputs/podcast",
        "externalInputRefs": ["acquisition/podcast/unit.json"],
        "externalInputsDigest": "sha256:" + "7" * 64,
    }
    runtime = _runtime(tmp_path)
    capsule_ref = _seal_capsule(runtime, lane_external_inputs=lanes)

    with pytest.raises(ValueError, match="active carriers are invalid"):
        _resume(
            runtime,
            capsule_ref=capsule_ref,
            lane_external_inputs=lanes,
        )


def test_lane_external_input_plan_drift_fails_closed(tmp_path: Path) -> None:
    """The frozen per-lane external input plan is part of capsule identity."""

    frozen = _lane_external_inputs()
    runtime = _runtime(tmp_path)
    capsule_ref = _seal_capsule(runtime, lane_external_inputs=frozen)

    drifted = _lane_external_inputs()
    drifted["article"]["externalInputRefs"] = ["acquisition/article/other.json"]

    with pytest.raises(ValueError, match="external input plan drift"):
        _resume(
            runtime,
            capsule_ref=capsule_ref,
            lane_external_inputs=drifted,
        )


def test_a_narrower_active_workload_may_not_reuse_a_wider_capsule(
    tmp_path: Path,
) -> None:
    """Resume must bind the exact active workload frozen in the capsule."""

    runtime = _runtime(tmp_path)
    capsule_ref = _seal_capsule(
        runtime,
        lane_external_inputs=_lane_external_inputs(),
    )

    with pytest.raises(ValueError, match="external input plan drift"):
        _resume(
            runtime,
            capsule_ref=capsule_ref,
            lane_external_inputs=_lane_external_inputs(("article",)),
        )


def test_an_empty_capsule_ref_is_rejected(tmp_path: Path) -> None:
    """An absent capsule ref may not collapse into the output root itself."""

    runtime = _runtime(tmp_path)
    _seal_capsule(runtime, lane_external_inputs=_lane_external_inputs())

    with pytest.raises(ValueError, match="capsule ref"):
        _resume(runtime, capsule_ref="   ")


def test_a_missing_capsule_manifest_fails_closed(tmp_path: Path) -> None:
    """Resume requires the immutable manifest bytes to be present."""

    runtime = _runtime(tmp_path)
    key = CAPSULE_DIGEST.removeprefix("sha256:")
    (runtime.workspaces_root / CAPSULES_DIR / key).mkdir(parents=True)
    capsule_ref = (
        (runtime.workspaces_root / CAPSULES_DIR / key)
        .resolve()
        .relative_to(runtime.output_root.resolve())
        .as_posix()
    )

    with pytest.raises((FileNotFoundError, OSError, TypeError, ValueError)):
        _resume(runtime, capsule_ref=capsule_ref)
