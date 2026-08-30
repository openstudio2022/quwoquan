"""Verify and snapshot exact source evidence for Post metadata adoption."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.execution.runtime_contract import canonical_sha256, file_sha256
from content.release.canonical.object_transaction_contract import (
    _digest_file,
    _files,
    _read_json,
    _safe_rel,
    _tree_digest,
    _write_json,
)
from content.release.canonical.post_metadata_adoption_contract import (
    PostMetadataAdoptionError,
)


def source_post_root(execution_root: Path, object_ref: str) -> Path:
    root = execution_root / "posts" / _safe_rel(object_ref, label="source.objectRef")
    if root.is_symlink() or not root.is_dir():
        raise PostMetadataAdoptionError(
            "DATA.POOL.METADATA_ADOPTION_SOURCE_OBJECT_MISSING"
        )
    return root


def assert_qualified_and_published(
    execution_root: Path,
    *,
    object_ref: str,
    topic_id: str,
) -> None:
    closure = _read_json(execution_root / "_shared/post_review_closure.json")
    objects = closure.get("objects")
    if (
        closure.get("executionId") != execution_root.name
        or not isinstance(objects, list)
        or sum(
            isinstance(row, Mapping)
            and str(row.get("publishRef") or "").removeprefix("posts/") == object_ref
            and row.get("objectRef") == topic_id
            and row.get("disposition") == "qualified"
            and row.get("issues") == []
            for row in objects
        )
        != 1
    ):
        raise PostMetadataAdoptionError(
            "DATA.POOL.METADATA_ADOPTION_SOURCE_NOT_QUALIFIED"
        )
    published = _read_json(execution_root / "publish_ref.json")
    published_posts = (published.get("publishedRefs") or {}).get("posts")
    discards = published.get("publishDiscards")
    if (
        published.get("executionId") != execution_root.name
        or not isinstance(published_posts, list)
        or object_ref not in published_posts
        or not isinstance(discards, list)
        or any(
            isinstance(row, Mapping) and row.get("objectRef") == object_ref
            for row in discards
        )
    ):
        raise PostMetadataAdoptionError(
            "DATA.POOL.METADATA_ADOPTION_SOURCE_NOT_PUBLISHED"
        )


def assert_retry_delivery_state(execution_root: Path) -> None:
    state = _read_json(execution_root / "_shared/execution_state.json")
    completed = state.get("completed")
    issues = state.get("failedIssueRecords")
    if (
        state.get("executionId") != execution_root.name
        or not isinstance(completed, list)
        or not {"post_author", "post_review"}.issubset(set(completed))
        or not isinstance(issues, list)
        or not any(
            isinstance(row, Mapping)
            and row.get("code") == "DATA.POOL.DELIVERY_UNAVAILABLE"
            and row.get("recovery") == "retry_delivery"
            for row in issues
        )
    ):
        raise PostMetadataAdoptionError(
            "DATA.POOL.METADATA_ADOPTION_RECOVERY_NOT_ALLOWED"
        )


def semantic_attempt(
    semantic_root: Path,
    *,
    run_id: str,
    label: str,
) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for path in _files(semantic_root):
        if path.name.endswith(".json") and "attempts" in path.parts:
            attempt = _read_json(path)
            if attempt.get("runId") == run_id:
                matches.append(attempt)
    if len(matches) != 1:
        raise PostMetadataAdoptionError(
            f"DATA.POOL.METADATA_ADOPTION_{label.upper()}_RUN_INVALID"
        )
    attempt = matches[0]
    if (
        attempt.get("status") != "finished"
        or attempt.get("started") is not True
        or attempt.get("attempt") != 1
    ):
        raise PostMetadataAdoptionError(
            f"DATA.POOL.METADATA_ADOPTION_{label.upper()}_RUN_INVALID"
        )
    return attempt


def restore_snapshot_cas(
    *,
    snapshot: Path,
    source_execution_root: Path,
) -> None:
    package = _read_json(snapshot / "object_transaction_package.json")
    manifest = _read_json(snapshot / "object/manifest.json")
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        raise PostMetadataAdoptionError(
            "DATA.POOL.METADATA_ADOPTION_SOURCE_ASSETS_INVALID"
        )
    for row in (package.get("closure") or {}).get("casRefs") or []:
        if not isinstance(row, Mapping):
            raise PostMetadataAdoptionError(
                "DATA.POOL.METADATA_ADOPTION_SOURCE_CAS_INVALID"
            )
        destination = snapshot / _safe_rel(
            str(row.get("sourceRef") or ""), label="source.casRef"
        )
        expected_digest = str(row.get("sha256") or "")
        expected_bytes = row.get("bytes")
        if destination.is_file():
            if (
                destination.is_symlink()
                or _digest_file(destination) != expected_digest
                or destination.stat().st_size != expected_bytes
            ):
                raise PostMetadataAdoptionError(
                    "DATA.POOL.METADATA_ADOPTION_SOURCE_CAS_DRIFT"
                )
            continue
        candidates: set[Path] = set()
        for raw in assets:
            if not isinstance(raw, Mapping) or raw.get("sha256") != expected_digest:
                continue
            source_ref = str(raw.get("sourceAssetRef") or "").strip()
            if source_ref:
                candidates.add(
                    source_execution_root
                    / _safe_rel(source_ref, label="asset.sourceAssetRef")
                )
        valid = [
            path
            for path in sorted(candidates)
            if path.is_file()
            and not path.is_symlink()
            and _digest_file(path) == expected_digest
            and path.stat().st_size == expected_bytes
        ]
        if len(valid) != 1:
            raise PostMetadataAdoptionError(
                "DATA.POOL.METADATA_ADOPTION_SOURCE_CAS_MISSING"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(valid[0], destination)


def write_semantic_inventory(
    semantic_root: Path,
    *,
    destination: Path,
) -> str:
    if semantic_root.is_symlink() or not semantic_root.is_dir():
        raise PostMetadataAdoptionError(
            "DATA.POOL.METADATA_ADOPTION_SEMANTIC_EVIDENCE_MISSING"
        )
    rows = [
        {
            "path": path.relative_to(semantic_root).as_posix(),
            "sha256": _digest_file(path),
            "bytes": path.stat().st_size,
        }
        for path in _files(semantic_root)
    ]
    if not rows:
        raise PostMetadataAdoptionError(
            "DATA.POOL.METADATA_ADOPTION_SEMANTIC_EVIDENCE_MISSING"
        )
    tree_digest = _tree_digest(semantic_root)
    _write_json(
        destination,
        {
            "schema": "quwoquan_data.post_metadata_adoption_semantic_inventory",
            "files": rows,
            "treeDigest": tree_digest,
        },
    )
    return tree_digest


def source_provenance(
    *,
    source_post: Path,
    source_package_object: Path,
) -> tuple[dict[str, Any], Path]:
    provenance_path = source_post / "5.review/provenance.json"
    if provenance_path.is_symlink() or not provenance_path.is_file():
        raise PostMetadataAdoptionError(
            "DATA.POOL.METADATA_ADOPTION_PROVENANCE_MISSING"
        )
    provenance = _read_json(provenance_path)
    evidence_index_path = source_post / "5.review/evidence_index.json"
    if (
        file_sha256(evidence_index_path)
        != file_sha256(source_package_object / "evidence_index.json")
    ):
        raise PostMetadataAdoptionError(
            "DATA.POOL.METADATA_ADOPTION_EVIDENCE_INDEX_DRIFT"
        )
    index = _read_json(evidence_index_path)
    matches = [
        row
        for row in index.get("evidence") or []
        if isinstance(row, Mapping) and row.get("ref") == "5.review/provenance.json"
    ]
    if len(matches) != 1 or matches[0].get("sha256") != canonical_sha256(provenance):
        raise PostMetadataAdoptionError(
            "DATA.POOL.METADATA_ADOPTION_PROVENANCE_DIGEST_DRIFT"
        )
    return provenance, provenance_path


__all__ = [
    "assert_qualified_and_published",
    "assert_retry_delivery_state",
    "restore_snapshot_cas",
    "semantic_attempt",
    "source_post_root",
    "source_provenance",
    "write_semantic_inventory",
]
