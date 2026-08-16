"""Digest helpers for immutable campaign workspaces."""

from __future__ import annotations

import hashlib
import json

from content.execution.campaign.workspace import (
    Any,
    Path,
    os,
)


def _canonical_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _capsule_tree_digest(root: Path) -> str:
    """Verify every exported executor byte, not only sourceDigest inputs."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if relative == ".qwq_campaign_capsule.json":
            continue
        if path.is_symlink():
            row = f"L\0{relative}\0{os.readlink(path)}\n"
        elif path.is_file():
            executable = path.stat().st_mode & 0o111
            row = f"F\0{relative}\0{executable:o}\0{_file_digest(path)}\n"
        else:
            continue
        digest.update(row.encode("utf-8"))
    return "sha256:" + digest.hexdigest()


def _capsule_identity(
    *,
    git_branch: str,
    commit_sha: str,
    source_revision: str,
    source_digest: str,
    execution_bundle: dict[str, Any],
    entity_catalog_digest: str,
    lane_external_inputs: dict[str, dict[str, Any]],
    external_inputs_digest: str,
    source_pool_fields: dict[str, Any],
    roots: tuple[str, ...],
) -> tuple[dict[str, Any], str]:
    from content.execution.campaign.workspace import (
        CAPSULE_FORMAT,
        CAPSULE_SCHEMA,
        _canonical_digest,
    )

    stable = {
        "schema": CAPSULE_SCHEMA,
        "format": CAPSULE_FORMAT,
        "gitBranch": git_branch,
        "gitCommitSha": commit_sha,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "executionBundle": execution_bundle,
        "entityCatalogDigest": entity_catalog_digest,
        "roots": list(roots),
        "laneExternalInputs": lane_external_inputs,
        "externalInputsDigest": external_inputs_digest,
    }
    stable.update(source_pool_fields)
    return stable, _canonical_digest(stable)
