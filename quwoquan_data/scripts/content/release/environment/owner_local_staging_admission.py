"""Data-owned admission for four immutable service candidates."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content.release.environment.importers import (
    OwnerReleaseEvidence,
    assert_content_release_evidence_unchanged,
    load_owner_release_candidate_receipt,
)
from content.release.environment.public_api_client import PublicApiClient
from core.io import read_json
from core.release_layout import payload_digest, payload_file
from core.schema import assert_valid

OWNERS = ("tag", "creator", "homepage", "content")
_MEDIA_READ_CHUNK_BYTES = 1024 * 1024


class CandidateMediaClosureError(RuntimeError):
    """完整媒体公开读闭包未成立；调用方必须在 CAS 前停止。"""


def require_candidate_media_readable(
    *,
    release: Path,
    release_id: str,
    manifest_digest: str,
    media_base_url: str,
    ssl_cafile: str = "",
) -> None:
    """逐个完整读取 sealed manifest 的全部公开媒体，不以抽样/同步计数作证明。"""

    try:
        if payload_digest(release) != manifest_digest:
            raise ValueError("candidate payload digest drift")
        manifest = read_json(payload_file(release, "media_manifest.json"))
        assert_valid(manifest, "release", "media_manifest")
        assets = manifest["assets"]
        if (
            manifest["releaseId"] != release_id
            or manifest["sourceOwner"] != "qwq_data"
            or manifest["issues"]
            or manifest["counts"] != {"assets": len(assets), "issues": 0}
            or len({row["assetId"] for row in assets}) != len(assets)
            or len({row["publicSliceKey"] for row in assets}) != len(assets)
        ):
            raise ValueError("candidate media manifest identity/closure differs")
        if assets:
            client = PublicApiClient(base_url=media_base_url, ssl_cafile=ssl_cafile)
            for asset in assets:
                _require_complete_public_asset(client, media_base_url, asset)
        # 读取期间 producer 身份不得变化；不回写 manifest 或 handoff。
        if payload_digest(release) != manifest_digest:
            raise ValueError("candidate payload digest drift during media readback")
    except (Exception, SystemExit) as error:
        raise CandidateMediaClosureError(
            "GATE_BLOCK: candidate media closure is not completely readable "
            f"({type(error).__name__})"
        ) from error


def _require_complete_public_asset(
    client: PublicApiClient, media_base_url: str, asset: Mapping[str, Any]
) -> None:
    size = asset["bytes"]
    digest = hashlib.sha256()
    url = f"{media_base_url.rstrip('/')}/{asset['publicSliceKey']}"
    for start in range(0, size, _MEDIA_READ_CHUNK_BYTES):
        end = min(start + _MEDIA_READ_CHUNK_BYTES, size) - 1
        response = client.get_bytes(
            url, byte_range=f"bytes={start}-{end}", max_bytes=end - start + 1
        )
        whole = start == 0 and end == size - 1
        if (
            (response.status != 206 and not (whole and response.status == 200))
            or (response.status == 206 and response.content_range != f"bytes {start}-{end}/{size}")
            or len(response.body) != end - start + 1
            or response.content_length not in (0, len(response.body))
            or response.content_type.split(";", 1)[0].strip() != asset["contentType"]
        ):
            raise ValueError("candidate public media range/length/type differs")
        digest.update(response.body)
    if f"sha256:{digest.hexdigest()}" != asset["sha256"]:
        raise ValueError("candidate public media digest differs")


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


__all__ = [
    "OWNERS", "OwnerCandidateProof", "CandidateMediaClosureError",
    "require_candidate_media_readable", "require_owner_local_staging_admission",
]
