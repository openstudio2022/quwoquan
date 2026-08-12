"""Validate immutable release attestation evidence."""

from __future__ import annotations

import json
from pathlib import Path

from content.release.canonical.release_attestation import (
    ReleaseAttestation,
    ReleaseAttestationError,
)
from content.release.model import DataSourceOwner
from core.paths import RELEASE_ROOT
from core.release_layout import attestation_root, payload_digest, payload_file
from core.schema import assert_valid
from core.source_digest import (
    FrozenSourceDigest,
    SourceDigest,
    SourceDigestError,
    parse_source_digest_document,
)

RELEASE_ATTESTATION = "release.json"


def read_object(path: Path, *, label: str, issues: list[str]) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(f"{path}: invalid {label}: {exc}")
        return {}
    if not isinstance(payload, dict):
        issues.append(f"{path}: {label} must be an object")
        return {}
    return payload


def validate_document(
    document: dict,
    *,
    path: Path,
    schema_name: str,
    issues: list[str],
) -> bool:
    try:
        assert_valid(
            document,
            "release",
            schema_name,
            label=f"{schema_name}:{path}",
        )
    except (FileNotFoundError, ValueError) as exc:
        issues.append(str(exc))
        return False
    return True


def _source_digests(
    document: dict,
    *,
    path: Path,
    issues: list[str],
) -> tuple[SourceDigest | FrozenSourceDigest, ...] | None:
    raw_value = document.get("sourceDigests")
    if not isinstance(raw_value, list):
        issues.append(f"{path}: sourceDigests must be an array")
        return None
    raw_identities = document.get("sourceIdentities") or []
    if not isinstance(raw_identities, list):
        issues.append(f"{path}: sourceIdentities must be an array")
        return None
    legacy_digests = frozenset(
        str(item.get("sourceDigest") or "")
        for item in raw_identities
        if isinstance(item, dict)
        and item.get("identityKind") == "legacy_canonical_migration"
    )
    try:
        source_digests = tuple(
            parse_source_digest_document(
                item,
                frozen_digest_allowlist=legacy_digests,
            )
            for item in raw_value
        )
    except SourceDigestError as exc:
        issues.append(f"{path}: {exc}")
        return None
    values = tuple(item.digest for item in source_digests)
    if not values or values != tuple(sorted(set(values))):
        issues.append(f"{path}: sourceDigests must be sorted and contain no duplicates")
        return None
    return source_digests


def release_lifecycle_issues(
    release_id: str,
    *,
    release_root: Path | None = None,
) -> list[str]:
    root = (release_root or RELEASE_ROOT) / release_id
    required = (
        payload_file(root, "release.json"),
        payload_file(root, "desired_state.json"),
        attestation_root(root) / RELEASE_ATTESTATION,
    )
    issues = [
        f"{path}: missing immutable release evidence"
        for path in required
        if not path.is_file()
    ]
    release_file = payload_file(root, "release.json")
    desired_file = payload_file(root, "desired_state.json")
    aggregate_file = attestation_root(root) / RELEASE_ATTESTATION
    if (
        not release_file.is_file()
        or not desired_file.is_file()
        or not aggregate_file.is_file()
    ):
        return issues

    header = read_object(release_file, label="release header", issues=issues)
    desired = read_object(desired_file, label="desired state", issues=issues)
    aggregate = read_object(
        aggregate_file,
        label="aggregate attestation",
        issues=issues,
    )
    if not header or not desired or not aggregate:
        return issues
    if not validate_document(
        header,
        path=release_file,
        schema_name="release_header",
        issues=issues,
    ):
        return issues
    if not validate_document(
        desired,
        path=desired_file,
        schema_name="release_desired_state",
        issues=issues,
    ):
        return issues
    try:
        assert_valid(
            aggregate,
            "release",
            "release_attestation",
            label=f"release_attestation:{release_id}",
        )
    except (FileNotFoundError, ValueError) as exc:
        issues.append(str(exc))
        return issues
    try:
        typed_attestation = ReleaseAttestation.from_document(aggregate)
    except ReleaseAttestationError as exc:
        issues.append(f"{aggregate_file}: {exc}")
        return issues

    if header.get("releaseId") != release_id:
        issues.append(f"{release_file}: releaseId does not match directory")
    if header.get("sourceOwner") != DataSourceOwner.QWQ_DATA:
        issues.append(f"{release_file}: sourceOwner must be qwq_data")
    release_kind = header.get("releaseKind")
    if release_kind not in {"content", "empty_baseline"}:
        issues.append(f"{release_file}: releaseKind is invalid")
    header_execution_ids = header.get("executionIds")
    if not isinstance(header_execution_ids, list):
        issues.append(f"{release_file}: executionIds must be an array")
        header_execution_ids = []
    desired_refs = desired.get("desiredRefs")
    if not isinstance(desired_refs, dict):
        issues.append(f"{desired_file}: desiredRefs must be an object")
        desired_refs = {}
    entity_refs = desired_refs.get("entities")
    post_refs = desired_refs.get("posts")
    creator_refs = desired_refs.get("creators")
    tag_refs = desired_refs.get("tags")
    if not all(
        isinstance(refs, list)
        for refs in (entity_refs, post_refs, creator_refs, tag_refs)
    ):
        issues.append(f"{desired_file}: all desiredRefs kinds must be arrays")
        return issues
    if typed_attestation.release_id != release_id:
        issues.append(f"{aggregate_file}: releaseId does not match directory")
    if typed_attestation.source_owner is not DataSourceOwner.QWQ_DATA:
        issues.append(f"{aggregate_file}: sourceOwner must be qwq_data")
    if typed_attestation.source_owner.value != header.get("sourceOwner"):
        issues.append(f"{aggregate_file}: sourceOwner drift from release header")
    if typed_attestation.release_kind.value != release_kind:
        issues.append(f"{aggregate_file}: releaseKind drift from release header")
    if sorted(typed_attestation.execution_ids) != sorted(header_execution_ids):
        issues.append(f"{aggregate_file}: executionIds drift from release header")
    if typed_attestation.canonical_merkle != header.get("canonicalMerkle"):
        issues.append(f"{aggregate_file}: canonicalMerkle drift from release header")
    header_source_digests = _source_digests(
        header,
        path=release_file,
        issues=issues,
    )
    aggregate_source_digests = _source_digests(
        aggregate,
        path=aggregate_file,
        issues=issues,
    )
    if (
        header_source_digests is not None
        and aggregate_source_digests is not None
        and header_source_digests != aggregate_source_digests
    ):
        issues.append(f"{aggregate_file}: sourceDigests drift from release header")
    if typed_attestation.entity_count != len(entity_refs):
        issues.append(f"{aggregate_file}: entityCount drift from desired state")
    if typed_attestation.post_count != len(post_refs):
        issues.append(f"{aggregate_file}: postCount drift from desired state")
    if typed_attestation.creator_count != len(creator_refs):
        issues.append(f"{aggregate_file}: creatorCount drift from desired state")
    if typed_attestation.tag_count != len(tag_refs):
        issues.append(f"{aggregate_file}: tagCount drift from desired state")
    if release_kind == "content" and (
        not header_execution_ids or not (entity_refs or post_refs)
    ):
        issues.append(
            f"{release_file}: content release requires executionIds and "
            "canonical entity or post refs"
        )
    if release_kind == "empty_baseline" and (
        header_execution_ids or entity_refs or post_refs or creator_refs or tag_refs
    ):
        issues.append(
            f"{release_file}: empty baseline must have no executions or desired refs"
        )
    try:
        actual_payload_digest = payload_digest(root)
    except (FileNotFoundError, OSError, ValueError) as exc:
        issues.append(f"{root}: cannot compute payload digest: {exc}")
    else:
        if aggregate.get("payloadSha256") != actual_payload_digest:
            issues.append(
                f"{aggregate_file}: payloadSha256 drift from immutable payload"
            )
    return issues
