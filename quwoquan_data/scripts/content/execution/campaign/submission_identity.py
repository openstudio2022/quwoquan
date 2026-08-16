"""Repository identity helpers for campaign submissions."""

from __future__ import annotations

import hashlib
import json
import subprocess

from content.execution.campaign.submission import (
    Any,
    Path,
)


def _sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _git_commit(repo_root: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def _git_branch(repo_root: Path) -> str:
    proc = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    branch = proc.stdout.strip()
    if not branch:
        raise ValueError("campaign submission requires a named frozen main branch")
    return branch


def _assert_no_cross_campaign_collision(
    *,
    campaigns_dir: Path,
    root_execution_id: str,
    execution_id: str,
) -> None:
    for candidate in sorted(campaigns_dir.glob(f"*/submissions/{execution_id}.json")):
        owner = candidate.parent.parent.name
        if owner != root_execution_id:
            raise ValueError(
                f"execution {execution_id} already belongs to campaign {owner}"
            )


def _require_stable_source_inputs(
    source_document: dict[str, object],
    *,
    execution_bundle: dict[str, object],
    repo_root: Path,
) -> None:
    """Reject digest drift without requiring a shared worktree to be clean."""
    from content.execution.campaign.submission import (
        current_execution_bundle_identity,
        current_source_definition_snapshot,
    )

    observed = current_source_definition_snapshot(repo_root=repo_root).to_document()
    observed_bundle = current_execution_bundle_identity(
        repo_root=repo_root
    ).to_document()
    if observed != source_document or observed_bundle != execution_bundle:
        raise ValueError(
            "campaign submission source snapshot/execution bundle changed during freeze"
        )
