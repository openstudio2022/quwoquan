"""Immutable carrier submissions for one coordinated four-lane execution."""
from __future__ import annotations

import fcntl
import hashlib
import json
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from core import paths
from core.io import read_json, write_json
from core.schema import assert_valid
from core.source_digest import current_source_digest
from content.execution.identity import parse_execution_id, validate_execution_id
from content.execution.request import RuntimeExecutionRequest
from content.execution.workspace import entity_catalog_digest


SUBMISSION_SCHEMA = "quwoquan_data.content_execution_submission"
_OPERATIONS = {
    "homepage": "homepage.generate",
    "article": "article.generate",
    "image": "image.generate",
    "video": "video.generate",
}


def campaigns_root() -> Path:
    return (
        paths.DATA_LOCAL_ROOT
        / "workspace"
        / "content-campaign-submissions"
    )


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
        raise ValueError(
            "campaign submission requires a named frozen main branch"
        )
    return branch


def _require_clean_source_inputs(
    source_document: dict[str, object],
    *,
    repo_root: Path,
) -> None:
    inputs = [str(item) for item in source_document.get("inputs") or []]
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--", *inputs],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    dirty = proc.stdout.strip()
    if dirty:
        raise ValueError(
            "campaign submission requires clean sourceDigest inputs; "
            "freeze the reviewed baseline before submitting"
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
    for candidate in sorted(
        campaigns_dir.glob(f"*/submissions/{execution_id}.json")
    ):
        owner = candidate.parent.parent.name
        if owner != root_execution_id:
            raise ValueError(
                f"execution {execution_id} already belongs to campaign {owner}"
            )


def write_submission(
    *,
    root_execution_id: str,
    execution_id: str,
    request: RuntimeExecutionRequest,
    retry_of: str | None,
    repo_root: Path | None = None,
    root: Path | None = None,
) -> Path:
    source_repo = (repo_root or paths.REPO_ROOT).resolve()
    campaigns_dir = root or campaigns_root()
    root_identity = parse_execution_id(root_execution_id)
    if root_identity.content_type.value != "homepage":
        raise ValueError("campaign root must use the homepage execution identity")
    identity = parse_execution_id(execution_id)
    if identity.vertical != root_identity.vertical:
        raise ValueError("campaign lanes must use the same vertical")
    source = current_source_digest(repo_root=source_repo).to_document()
    _require_clean_source_inputs(source, repo_root=source_repo)
    discovery = (
        source_repo
        / "quwoquan_data"
        / "reference"
        / identity.vertical
        / "entities"
        / request.region_ref
    )
    catalog_digest = entity_catalog_digest(
        discovery.relative_to(source_repo).as_posix()
    )
    stable: dict[str, Any] = {
        "schema": SUBMISSION_SCHEMA,
        "rootExecutionId": root_identity.execution_id,
        "executionId": identity.execution_id,
        "operation": _OPERATIONS[identity.content_type.value],
        "carrier": identity.content_type.value,
        "familyRef": request.family_ref,
        "regionRef": request.region_ref,
        "selector": request.selector.value,
        "quota": request.quota,
        "count": request.count,
        "topic": request.topic,
        "targetNames": list(request.target_names),
        "sourceProviders": list(request.source_providers),
        "retryOf": retry_of,
        "gitBranch": _git_branch(source_repo),
        "gitCommitSha": _git_commit(source_repo),
        "sourceDigest": source,
        "entityCatalogDigest": catalog_digest,
    }
    request_digest = _sha256(stable)
    path = submission_path(
        root_identity.execution_id,
        identity.execution_id,
        root=campaigns_dir,
    )
    with _submission_lock(campaigns_dir):
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
                label=f"campaign submission:{identity.execution_id}",
            )
            if (
                str(existing.get("requestDigest") or "") != request_digest
                or any(existing.get(key) != value for key, value in stable.items())
            ):
                raise ValueError(
                    f"execution {identity.execution_id} already has a different "
                    "campaign submission"
                )
            return path
        payload = {
            **stable,
            "requestDigest": request_digest,
            "submittedAt": _utc_now(),
        }
        assert_valid(
            payload,
            "execution",
            "content_execution_submission",
            label=f"campaign submission:{identity.execution_id}",
        )
        write_json(path, payload)
    return path


def load_submissions(
    root_execution_id: str,
    *,
    root: Path | None = None,
) -> dict[str, dict[str, Any]]:
    normalized_root = validate_execution_id(root_execution_id)
    submissions_dir = campaign_root(normalized_root, root=root) / "submissions"
    submissions: dict[str, dict[str, Any]] = {}
    for path in (
        sorted(submissions_dir.glob("*.json"))
        if submissions_dir.is_dir()
        else ()
    ):
        payload = read_json(path)
        assert_valid(
            payload,
            "execution",
            "content_execution_submission",
            label=f"campaign submission:{path.name}",
        )
        execution_id = validate_execution_id(str(payload.get("executionId") or ""))
        identity = parse_execution_id(execution_id)
        carrier = str(payload.get("carrier") or "")
        if (
            str(payload.get("rootExecutionId") or "") != normalized_root
            or path.stem != execution_id
            or carrier != identity.content_type.value
            or str(payload.get("operation") or "") != _OPERATIONS.get(carrier)
        ):
            raise ValueError(f"campaign submission identity collision: {path}")
        stable = {
            key: value
            for key, value in payload.items()
            if key not in {"requestDigest", "submittedAt"}
        }
        if str(payload.get("requestDigest") or "") != _sha256(stable):
            raise ValueError(f"campaign submission digest drift: {path}")
        if carrier in submissions:
            raise ValueError(f"campaign has duplicate {carrier} submissions")
        submissions[carrier] = payload
    return submissions


__all__ = [
    "campaign_root",
    "campaigns_root",
    "load_submissions",
    "submission_path",
    "write_submission",
]
