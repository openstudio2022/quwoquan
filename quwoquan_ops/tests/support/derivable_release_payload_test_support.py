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
    "write_derivable_release_payload",
]
