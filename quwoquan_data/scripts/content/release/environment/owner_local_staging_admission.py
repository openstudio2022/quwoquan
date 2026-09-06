"""Data-owned admission for four immutable service candidates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content.release.environment.importers import (
    OwnerReleaseEvidence,
    assert_content_release_evidence_unchanged,
    load_owner_release_candidate_receipt,
)

OWNERS = ("tag", "creator", "homepage", "content")


@dataclass(frozen=True)
class OwnerCandidateProof:
    """Schema-checked exact-byte refs accepted by the Data evaluator."""

    evidence: Mapping[str, OwnerReleaseEvidence]

    def result_fields(self) -> dict[str, str]:
        fields: dict[str, str] = {}
        for owner in OWNERS:
            item = self.evidence[owner]
            prefix = f"{owner}Candidate"
            fields[f"{prefix}ReceiptRef"] = item.ref
            fields[f"{prefix}ReceiptDigest"] = item.digest
        return fields


def _count_pair(document: Mapping[str, Any], *, owner: str) -> tuple[int, int]:
    counts = document.get("counts")
    if not isinstance(counts, Mapping):
        raise RuntimeError(f"{owner} candidate receipt counts 缺失")
    if owner == "content":
        pairs = (
            ("postsExpected", "postsProjected"),
            ("outboxExpected", "outboxProjected"),
            ("mediaExpected", "mediaProjected"),
        )
        for expected_name, projected_name in pairs:
            expected, projected = counts.get(expected_name), counts.get(projected_name)
            if type(expected) is not int or type(projected) is not int or expected != projected:
                raise RuntimeError(f"content candidate count mismatch: {expected_name}/{projected_name}")
        return int(counts["postsExpected"]), int(counts["postsProjected"])
    expected, projected = counts.get("expected"), counts.get("projected")
    if type(expected) is not int or type(projected) is not int or expected != projected:
        raise RuntimeError(f"{owner} candidate count mismatch")
    return expected, projected


def require_owner_local_staging_admission(
    *,
    evidence: Mapping[str, OwnerReleaseEvidence],
    output_root: Path,
    environment: str,
    release_id: str,
    manifest_digest: str,
) -> OwnerCandidateProof:
    """Re-read explicit four-owner evidence; import reports are never accepted."""

    if set(evidence) != set(OWNERS):
        missing = sorted(set(OWNERS) - set(evidence))
        extra = sorted(set(evidence) - set(OWNERS))
        raise RuntimeError(f"four-owner candidate proof incomplete: missing={missing} extra={extra}")
    verified: dict[str, OwnerReleaseEvidence] = {}
    for owner in OWNERS:
        asserted = evidence[owner]
        loaded = load_owner_release_candidate_receipt(
            asserted.path,
            owner=owner,
            output_root=output_root,
            environment=environment,
            release_id=release_id,
            manifest_digest=manifest_digest,
            expected_digest=asserted.digest,
        )
        document = loaded.document
        if int(document.get("projectionVersion") or 0) <= 0:
            raise RuntimeError(f"{owner} candidate projectionVersion 非法")
        if not document.get("verifiedAt"):
            raise RuntimeError(f"{owner} candidate verifiedAt 缺失")
        if owner == "content":
            closure = document.get("closureDigests")
            if not isinstance(closure, Mapping) or not closure:
                raise RuntimeError("content candidate closureDigests 缺失")
        elif not document.get("closureDigest"):
            raise RuntimeError(f"{owner} candidate closureDigest 缺失")
        _count_pair(document, owner=owner)
        assert_content_release_evidence_unchanged(loaded)
        verified[owner] = loaded
    return OwnerCandidateProof(verified)


__all__ = ["OWNERS", "OwnerCandidateProof", "require_owner_local_staging_admission"]
