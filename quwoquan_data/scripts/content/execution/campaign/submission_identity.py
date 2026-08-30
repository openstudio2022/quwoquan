"""Campaign submission paths, immutable identity, and serialization lock."""

from __future__ import annotations

import fcntl
import hashlib
import json
import subprocess
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

from core import paths
from core.io import read_json, write_json
from core.schema import assert_valid
from core.source_digest import (
    current_execution_bundle_identity,
    current_source_definition_snapshot,
)

from content.execution.campaign.external_inputs import (
    content_source_revision,
    external_inputs_digest,
    verify_external_input_refs,
)
from content.execution.campaign.carrier_execution_policy import carrier_operation
from content.execution.campaign.lane import (
    CAMPAIGN_CARRIERS,
    normalize_active_carriers,
    normalize_workloads,
)
from content.execution.campaign.scale import execution_campaign_scale
from content.execution.closure.adoption_campaign_contract import (
    ADOPTION_OPERATIONS,
    CAMPAIGN_ADOPTION_FIELD,
)
from content.execution.identity import parse_execution_id, validate_execution_id
from content.execution.model_contract import (
    CURSOR_AUTO_SEMANTIC_SELECTION_ID,
    DEFAULT_SEMANTIC_SELECTION_ID,
    normalize_semantic_selection_id,
)
from content.execution.planning.semantic_preflight_admission import (
    bind_semantic_preflight_receipt,
    validate_semantic_preflight_binding_at,
)
from content.execution.planning.semantic_failover_admission import (
    require_cursor_auto_retry_admission,
)
from content.execution.request import RuntimeExecutionRequest
from content.execution.workspace import entity_catalog_digest

SUBMISSION_SCHEMA = "quwoquan_data.content_execution_submission"


def campaigns_root() -> Path:
    return paths.DATA_LOCAL_ROOT / "workspace" / "content-campaign-submissions"


def campaign_root(
    root_execution_id: str,
    *,
    root: Path | None = None,
) -> Path:
    root_id = validate_execution_id(root_execution_id)
    return (root or campaigns_root()) / root_id


def submission_path(
    root_execution_id: str,
    execution_id: str,
    *,
    root: Path | None = None,
) -> Path:
    return (
        campaign_root(root_execution_id, root=root)
        / "submissions"
        / f"{validate_execution_id(execution_id)}.json"
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _require_stable_source_inputs(
    source_document: dict[str, object],
    *,
    execution_bundle: dict[str, object],
    repo_root: Path,
) -> None:
    """Reject digest drift without requiring a shared worktree to be clean."""
    observed = current_source_definition_snapshot(repo_root=repo_root).to_document()
    observed_bundle = current_execution_bundle_identity(
        repo_root=repo_root
    ).to_document()
    if observed != source_document or observed_bundle != execution_bundle:
        raise ValueError(
            "campaign submission source snapshot/execution bundle changed during freeze"
        )


@contextmanager
def _submission_lock(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".submission.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


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
