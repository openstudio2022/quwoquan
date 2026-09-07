"""Downstream create-once derivation of ReleaseUatSamplePlan.

Producer handoff 不携带 UAT sample plan（multi-carrier-release GWT-034），而
premium-pool 首次激活、bind-content 与 app-content-uat 都要消费一份 release-bound
的 sample plan。本模块把该 plan 定义为环境消费侧从 immutable release exact bytes
确定性派生的下游 artifact：

- 输入只有 ``payload/release.json``、``payload/desired_state.json`` 与
  ``payload/objects/**``，不读任何环境状态；
- 每载体按 identity 升序取首个对象（``baseline_per_required_carrier``），
  ``milestone`` 恒为 ``null``；
- 落点固定为 ``<releaseRoot>/uat/sample_plan.json``（``payload/`` 之外，payload
  digest 不受影响），create-once：同字节幂等、字节漂移 fail closed；
- 派生回执 ``<releaseRoot>/uat/derivation.json`` 把 plan digest 绑到
  ``releaseId + manifestDigest``，跨 release 搬运 fail closed。

真相源：specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

CARRIERS = ("homepage", "article", "image", "video")
ENTRIES = ("feed", "search", "recommendation", "direct_or_object_route")
PLAN_SCHEMA = "quwoquan_data.release_uat_sample_plan"
PLAN_IDENTITY_SCHEMA = "quwoquan_data.release_uat_sample_plan_identity"
DERIVATION_SCHEMA = "quwoquan_ops.release_uat_sample_plan_derivation.v1"
PLAN_DIRNAME = "uat"
PLAN_FILENAME = "sample_plan.json"
DERIVATION_FILENAME = "derivation.json"
STRATEGY_NAME = "baseline_per_required_carrier"
OBJECT_DIGEST_ALGORITHM = "sha256-path-blob-merkle"
SPEC_REF = (
    "specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/"
    "spec.md#req-006"
)
_RELEASES_SEGMENTS = ("data", "releases")
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_POST_CARRIERS = frozenset({"article", "image", "video"})


class ReleaseUatSamplePlanDerivationError(ValueError):
    """The downstream sample plan cannot be derived or has drifted."""


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def exact_document_bytes(value: Mapping[str, Any]) -> bytes:
    """Exact bytes shared with Data's immutable JSON writer."""
    return (
        json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def payload_tree_digest(root: Path) -> str:
    """Data's canonical sha256-path-blob-merkle over one exact subtree."""

    entries: list[bytes] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ReleaseUatSamplePlanDerivationError(
                "immutable release subtree contains a symlink"
            )
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        raw = path.read_bytes()
        blob_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        entries.append(
            hashlib.sha256(
                b"blob\0"
                + relative.encode("utf-8")
                + b"\0"
                + blob_digest.encode("ascii")
                + b"\0"
                + str(len(raw)).encode("ascii")
            ).digest()
        )
    if not entries:
        return "sha256:" + hashlib.sha256(b"").hexdigest()
    level = entries
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            hashlib.sha256(b"node\0" + level[index] + level[index + 1]).digest()
            for index in range(0, len(level), 2)
        ]
    return "sha256:" + level[0].hex()


def release_uat_sample_plan_ref(release_id: str) -> str:
    """The only output-root-relative ref a derived plan may have."""
    return "/".join((*_RELEASES_SEGMENTS, release_id, PLAN_DIRNAME, PLAN_FILENAME))


def _required_text(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ReleaseUatSamplePlanDerivationError(f"release {label} is missing")
    return text


def _required_digest(value: object, *, label: str) -> str:
    digest = _required_text(value, label=label)
    if _DIGEST_PATTERN.fullmatch(digest) is None:
        raise ReleaseUatSamplePlanDerivationError(
            f"release {label} is not a canonical sha256 digest"
        )
    return digest


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ReleaseUatSamplePlanDerivationError(f"{label} is missing or unsafe")
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseUatSamplePlanDerivationError(f"{label} is not readable JSON") from exc
    if not isinstance(value, dict):
        raise ReleaseUatSamplePlanDerivationError(f"{label} must be an object")
    return value


def _object_digest(payload_root: Path, object_ref: str) -> str:
    object_path = payload_root / object_ref
    if object_path.is_symlink() or not object_path.is_dir():
        raise ReleaseUatSamplePlanDerivationError(
            f"release object {object_ref} is missing from payload"
        )
    try:
        object_path.resolve(strict=True).relative_to(payload_root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise ReleaseUatSamplePlanDerivationError(
            f"release object {object_ref} escapes payload root"
        ) from exc
    return payload_tree_digest(object_path)


def _entity_refs(payload_root: Path, *, release_id: str) -> list[str]:
    desired = _read_json_object(
        payload_root / "desired_state.json", label="release desired_state"
    )
    if (
        desired.get("schema") != "quwoquan_data.release_desired_state"
        or desired.get("releaseId") != release_id
    ):
        raise ReleaseUatSamplePlanDerivationError("release desired_state identity drifted")
    desired_refs = desired.get("desiredRefs")
    entities = desired_refs.get("entities") if isinstance(desired_refs, Mapping) else None
    if not isinstance(entities, list):
        raise ReleaseUatSamplePlanDerivationError("release desired_state entities are missing")
    refs = [_required_text(ref, label="desired entity ref") for ref in entities]
    if len(refs) != len(set(refs)):
        raise ReleaseUatSamplePlanDerivationError("release desired_state entities are duplicated")
    return refs


def _release_contents(release_header: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = release_header.get("contents")
    if not isinstance(raw, list):
        raise ReleaseUatSamplePlanDerivationError("release header contents are missing")
    contents: list[dict[str, Any]] = []
    for index, row in enumerate(raw):
        if not isinstance(row, Mapping):
            raise ReleaseUatSamplePlanDerivationError(
                f"release header contents[{index}] is invalid"
            )
        _required_text(row.get("contentId"), label=f"contents[{index}].contentId")
        _required_text(row.get("postRef"), label=f"contents[{index}].postRef")
        contents.append(dict(row))
    return contents


def _populations(
    *,
    payload_root: Path,
    entity_refs: Sequence[str],
    contents: Sequence[Mapping[str, Any]],
) -> dict[str, list[tuple[str, str, str]]]:
    populations: dict[str, list[tuple[str, str, str]]] = {
        carrier: [] for carrier in CARRIERS
    }
    for ref in entity_refs:
        object_ref = f"objects/entities/{ref}"
        populations["homepage"].append(
            (f"/entity/{ref}", object_ref, _object_digest(payload_root, object_ref))
        )
    for row in contents:
        post_ref = str(row["postRef"]).strip()
        carrier = post_ref.partition("/")[0]
        if carrier not in _POST_CARRIERS:
            raise ReleaseUatSamplePlanDerivationError(
                f"release content postRef {post_ref!r} has an unknown carrier"
            )
        object_ref = f"objects/posts/{post_ref}"
        populations[carrier].append(
            (str(row["contentId"]).strip(), object_ref, _object_digest(payload_root, object_ref))
        )
    for carrier in CARRIERS:
        rows = sorted(populations[carrier])
        identities = [identity for identity, _ref, _digest in rows]
        refs = [ref for _identity, ref, _digest in rows]
        if len(identities) != len(set(identities)) or len(refs) != len(set(refs)):
            raise ReleaseUatSamplePlanDerivationError(
                f"release {carrier} cohort identities are duplicated"
            )
        populations[carrier] = rows
    return populations


def _matrix() -> list[dict[str, str]]:
    return [
        {
            "entry": entry,
            "carrier": carrier,
            "applicability": "required",
            "specRef": SPEC_REF,
            "runnerClass": f"qwq.content_consumer.{entry}.{carrier}.v1",
        }
        for entry in ENTRIES
        for carrier in CARRIERS
    ]


def derive_release_uat_sample_plan(
    *,
    payload_root: Path,
    release_header: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive the baseline plan deterministically from immutable payload bytes."""

    payload_root = payload_root.expanduser()
    if payload_root.is_symlink() or not payload_root.is_dir():
        raise ReleaseUatSamplePlanDerivationError("release payload root is missing or unsafe")
    if release_header.get("schema") != "quwoquan_data.release":
        raise ReleaseUatSamplePlanDerivationError("release header schema is invalid")
    release_id = _required_text(release_header.get("releaseId"), label="header releaseId")
    pool_digest = _required_digest(release_header.get("poolDigest"), label="header poolDigest")
    source_identity_set_digest = _required_digest(
        release_header.get("sourceIdentitySetDigest"),
        label="header sourceIdentitySetDigest",
    )
    canonical_merkle = _required_digest(
        release_header.get("canonicalMerkle"), label="header canonicalMerkle"
    )
    contents = _release_contents(release_header)
    entity_refs = _entity_refs(payload_root, release_id=release_id)
    populations = _populations(
        payload_root=payload_root, entity_refs=entity_refs, contents=contents
    )
    selection_evidence = {
        "poolDigest": pool_digest,
        "sourceIdentitySetDigest": source_identity_set_digest,
        "canonicalMerkle": canonical_merkle,
        "releaseContentsDigest": canonical_digest(
            sorted(
                contents,
                key=lambda row: (
                    str(row.get("contentId") or ""),
                    int(row.get("version") or 0),
                    str(row.get("postRef") or ""),
                ),
            )
        ),
        "releaseEntityCohortDigest": canonical_digest(sorted(entity_refs)),
    }
    release_digest = canonical_digest(
        {
            "schema": PLAN_IDENTITY_SCHEMA,
            "releaseId": release_id,
            "canonicalMerkle": canonical_merkle,
            "selectionEvidence": dict(selection_evidence),
        }
    )
    distribution = {carrier: (1 if populations[carrier] else 0) for carrier in CARRIERS}
    samples: list[dict[str, str]] = []
    for carrier in CARRIERS:
        for ordinal, (identity, object_ref, object_digest) in enumerate(
            populations[carrier][: distribution[carrier]], start=1
        ):
            samples.append(
                {
                    "sampleId": f"baseline-{carrier}-{ordinal:03d}",
                    "carrier": carrier,
                    "objectId": identity,
                    "objectRef": object_ref,
                    "objectDigest": object_digest,
                }
            )
    exact_counts = {carrier: len(populations[carrier]) for carrier in CARRIERS}
    return {
        "schema": PLAN_SCHEMA,
        "releaseId": release_id,
        "releaseDigest": release_digest,
        "milestone": None,
        "selectionEvidence": selection_evidence,
        # 下游只看得到 release cohort 本身；eligible 与 exact 同值是唯一诚实取值。
        "eligiblePopulationCounts": dict(exact_counts),
        "exactCohortCounts": exact_counts,
        "entryCarrierCells": _matrix(),
        "sampleStrategy": {
            "authority": None,
            "name": STRATEGY_NAME,
            "version": 1,
            "seedDigest": canonical_digest(
                {"releaseDigest": release_digest, "sampleDistribution": distribution}
            ),
            "carrierOrder": list(CARRIERS),
            "sortKey": "identity",
            "direction": "ascending",
            "objectDigestAlgorithm": OBJECT_DIGEST_ALGORITHM,
            "sampleDistribution": distribution,
        },
        "sampleCount": len(samples),
        "samples": samples,
    }


def _canonical_release_root(payload_root: Path, *, release_id: str) -> Path:
    """Release root 必须是 ``<outputRoot>/data/releases/<releaseId>/payload`` 的父目录。

    只按路径段名判定，不依赖进程内的 output-root 解析；ref 因此是 releaseId 的
    纯函数，消费方再按各自 authority root 解析并 fail closed。
    """
    resolved = payload_root.resolve(strict=True)
    release_root = resolved.parent
    if (
        resolved.name != "payload"
        or release_root.name != release_id
        or tuple(release_root.parts[-3:-1]) != _RELEASES_SEGMENTS
    ):
        raise ReleaseUatSamplePlanDerivationError(
            "release root is not the canonical data/releases/<releaseId> location"
        )
    return release_root


def _write_create_once(path: Path, raw: bytes, *, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o644,
        )
    except FileExistsError as exc:
        raise ReleaseUatSamplePlanDerivationError(
            f"{label} derivation is already in progress"
        ) from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def load_or_derive_release_uat_sample_plan(
    *,
    payload_root: Path,
    release_header: Mapping[str, Any],
    manifest_digest: str = "",
) -> tuple[dict[str, Any], str, str]:
    """Return ``(plan, output-root-relative ref, plan digest)`` create-once.

    首次调用把派生结果写到 ``<releaseRoot>/uat/``；之后每次调用都重新派生并与
    已落盘字节逐字节比对，任何漂移或跨 release 搬运均 fail closed。
    """

    release_id = _required_text(release_header.get("releaseId"), label="header releaseId")
    release_root = _canonical_release_root(payload_root, release_id=release_id)
    expected_manifest = (
        _required_digest(manifest_digest, label="manifestDigest")
        if str(manifest_digest or "").strip()
        else payload_tree_digest(payload_root)
    )
    plan = derive_release_uat_sample_plan(
        payload_root=payload_root, release_header=release_header
    )
    raw = exact_document_bytes(plan)
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    ref = release_uat_sample_plan_ref(release_id)
    plan_path = release_root / PLAN_DIRNAME / PLAN_FILENAME
    receipt_path = release_root / PLAN_DIRNAME / DERIVATION_FILENAME
    receipt = {
        "schema": DERIVATION_SCHEMA,
        "releaseId": release_id,
        "manifestDigest": expected_manifest,
        "planRef": ref,
        "planDigest": digest,
        "strategy": STRATEGY_NAME,
        "inputs": [
            "payload/release.json",
            "payload/desired_state.json",
            "payload/objects/**",
        ],
    }
    if plan_path.is_symlink() or receipt_path.is_symlink():
        raise ReleaseUatSamplePlanDerivationError("derived sample plan path is unsafe")
    if plan_path.exists() or receipt_path.exists():
        if not (plan_path.is_file() and receipt_path.is_file()):
            raise ReleaseUatSamplePlanDerivationError(
                "derived sample plan and its derivation receipt must exist together"
            )
        if plan_path.read_bytes() != raw:
            raise ReleaseUatSamplePlanDerivationError(
                "derived ReleaseUatSamplePlan drifted from immutable release bytes"
            )
        stored = _read_json_object(receipt_path, label="sample plan derivation receipt")
        if stored != receipt:
            raise ReleaseUatSamplePlanDerivationError(
                "sample plan derivation receipt is not bound to this exact release"
            )
        return plan, ref, digest
    _write_create_once(plan_path, raw, label="ReleaseUatSamplePlan")
    _write_create_once(
        receipt_path, exact_document_bytes(receipt), label="sample plan derivation receipt"
    )
    return plan, ref, digest


__all__ = [
    "CARRIERS",
    "DERIVATION_SCHEMA",
    "ENTRIES",
    "PLAN_SCHEMA",
    "ReleaseUatSamplePlanDerivationError",
    "canonical_digest",
    "derive_release_uat_sample_plan",
    "exact_document_bytes",
    "load_or_derive_release_uat_sample_plan",
    "payload_tree_digest",
    "release_uat_sample_plan_ref",
]
