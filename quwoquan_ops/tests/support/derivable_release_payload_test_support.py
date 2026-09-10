"""Minimal immutable release payload that the downstream sample plan can derive from.

ReleaseUatSamplePlan 由消费侧从 ``payload/release.json``、``payload/desired_state.json``
与 ``payload/objects/**`` 派生（`release_uat_sample_plan_derivation`）。测试 fixture
不再手写 sample plan 字节，而是写出最小可派生 payload，再调用生产派生逻辑取回
exact plan/ref/digest，保证 fixture 与真实 release 同形。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.release_uat_sample_plan_derivation import (
    load_or_derive_release_uat_sample_plan,
)


def release_header_fixture(
    *, release_id: str,
    contents: Sequence[Mapping[str, Any]] | None = None,
    source_identities: Sequence[Mapping[str, Any]] | None = None,
    source_identity_set_digest: str = "",
) -> dict[str, Any]:
    """显式构造现役闭集 header，不对传入文档删除旧类别或放宽 schema。"""
    from quwoquan_ops.cli.commands.app_preflight_readiness import _validate_data_schema
    from quwoquan_ops.cli.lib.release_uat_sample_plan_derivation import canonical_digest

    digest = "sha256:" + "6" * 64
    sources = list(source_identities or [{
        "sourceRevision": "sha256:" + "a" * 64,
        "sourceDigest": "sha256:" + "b" * 64,
        "entityCatalogDigest": "sha256:" + "c" * 64,
        "executionIds": ["execution-1"],
    }])
    rows = [
        {"version": 1, "selectionIdentityDigest": digest,
         "canonicalObjectDigest": digest, "contentLibraryBindingDigest": digest, **row}
        for row in (contents if contents is not None else [
            {"contentId": f"{carrier}-a", "postRef": f"{carrier}/a/1"}
            for carrier in ("article", "image", "video")
        ])
    ]
    counts = {carrier: sum(str(row["postRef"]).startswith(carrier + "/") for row in rows)
              for carrier in ("article", "image", "video")}
    header = {
        "schema": "quwoquan_data.release", "releaseId": release_id,
        "sourceOwner": "qwq_data", "releaseKind": "content",
        "containsUnverifiedAssets": True,
        "rightsStatusCounts": {"verified": 0, "unverified": 1, "restricted": 0, "unknown": 0},
        "authorizationRequiredAssetIds": ["asset-1"],
        "researchAcceptedCount": 1, "commercialAcceptedCount": 0,
        "sourceIdentities": sources,
        "sourceIdentitySetDigest": source_identity_set_digest or canonical_digest({
            "schema": "quwoquan_data.source_identity_set", "sourceIdentities": sources,
        }),
        "executionIds": sorted({item for source in sources for item in source["executionIds"]}),
        "sourceDigests": [{"algorithm": "sha256", "digest": digest, "inputs": ["quwoquan_data"]}],
        "canonicalMerkle": digest, "poolDigest": digest,
        "counts": {"homepage": 1, **counts, "total": len(rows) + 1},
        "contents": rows,
    }
    _validate_data_schema(header, "release_header")
    return header


def release_attestation_fixture(
    header: Mapping[str, Any], *, payload_digest: str,
) -> dict[str, Any]:
    """从完整 header 明确投影 attestation 身份与权利事实。"""
    from quwoquan_ops.cli.commands.app_preflight_readiness import _validate_data_schema

    fields = (
        "releaseId", "sourceOwner", "releaseKind", "containsUnverifiedAssets",
        "rightsStatusCounts", "authorizationRequiredAssetIds", "researchAcceptedCount",
        "commercialAcceptedCount", "executionIds", "sourceIdentities",
        "sourceIdentitySetDigest", "canonicalMerkle", "sourceDigests",
    )
    attestation = {
        "schema": "quwoquan_data.release_attestation",
        **{field: header[field] for field in fields},
        "carrierCounts": dict(header["counts"]),
        "entityCount": header["counts"]["homepage"],
        "postCount": len(header["contents"]), "creatorCount": 1, "tagCount": 1,
        "payloadSha256": payload_digest, "recordedAt": "2026-09-09T00:00:00Z",
    }
    _validate_data_schema(attestation, "release_attestation")
    return attestation


def release_payload_root(output_root: Path, release_id: str) -> Path:
    """The only payload location the derivation accepts."""
    return output_root / "data" / "releases" / release_id / "payload"


def write_derivable_release_payload(
    payload_root: Path,
    *,
    release_header: Mapping[str, Any],
    entity_refs: Sequence[str],
    header_bytes: bytes | None = None,
) -> Path:
    """Write header, desired_state and one object directory per cohort member.

    ``entity_refs`` 是 canonical ref（如 ``地点/景区/塘栖古镇``）；帖子从 header
    ``contents[].postRef`` 派生。返回 ``payload/release.json`` 路径。
    """

    release_id = str(release_header["releaseId"])
    payload_root.mkdir(parents=True, exist_ok=True)
    post_refs: list[str] = []
    for row in release_header.get("contents") or []:
        post_ref = str(row["postRef"])
        post_refs.append(post_ref)
        object_dir = payload_root / "objects" / "posts" / post_ref
        object_dir.mkdir(parents=True, exist_ok=True)
        (object_dir / "manifest.json").write_text(
            json.dumps({"postRef": post_ref, "contentId": row["contentId"]}, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
    for ref in entity_refs:
        object_dir = payload_root / "objects" / "entities" / ref
        object_dir.mkdir(parents=True, exist_ok=True)
        (object_dir / "_entity.json").write_text(
            json.dumps({"label": ref.rsplit("/", 1)[-1]}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    (payload_root / "desired_state.json").write_text(
        json.dumps(
            {
                "schema": "quwoquan_data.release_desired_state",
                "releaseId": release_id,
                "desiredRefs": {
                    "creators": [],
                    "entities": list(entity_refs),
                    "posts": post_refs,
                    "tags": [],
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    header_path = payload_root / "release.json"
    header_path.write_bytes(
        header_bytes
        if header_bytes is not None
        else (json.dumps(release_header, ensure_ascii=False, sort_keys=True) + "\n").encode(
            "utf-8"
        )
    )
    return header_path


def derive_fixture_release_uat_sample_plan(
    payload_root: Path,
    *,
    release_header: Mapping[str, Any],
    manifest_digest: str = "",
) -> tuple[dict[str, Any], str, str]:
    """Run the production derivation so fixtures embed the exact plan/ref/digest."""
    return load_or_derive_release_uat_sample_plan(
        payload_root=payload_root,
        release_header=release_header,
        manifest_digest=manifest_digest,
    )


__all__ = [
    "derive_fixture_release_uat_sample_plan",
    "release_payload_root",
    "release_header_fixture",
    "release_attestation_fixture",
    "write_derivable_release_payload",
]
