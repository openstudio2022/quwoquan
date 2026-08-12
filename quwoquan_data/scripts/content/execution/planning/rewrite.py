"""Immutable planning binding for one targeted content rewrite execution."""

from __future__ import annotations

import argparse
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.io import read_json


REWRITE_REASONS = ("duplicate", "quality", "rights", "metadata")
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
_REWRITE_KEYS = frozenset(
    {
        "contentId",
        "expectedVersion",
        "nextVersion",
        "reason",
        "sourceObjectRef",
        "sourceTaskId",
        "sourcePayloadDigest",
        "targetName",
        "contentType",
        "variantPurpose",
    }
)


@dataclass(frozen=True, slots=True)
class RewriteBinding:
    """Facts frozen before a new retry execution authors replacement bytes."""

    content_id: str
    expected_version: int
    next_version: int
    reason: str
    source_object_ref: str
    source_task_id: str
    source_payload_digest: str
    target_name: str
    content_type: str
    variant_purpose: str

    def __post_init__(self) -> None:
        if not self.content_id.strip():
            raise ValueError("rewrite contentId must be non-empty")
        if (
            isinstance(self.expected_version, bool)
            or self.expected_version < 1
            or self.next_version != self.expected_version + 1
        ):
            raise ValueError("rewrite version must be exactly expectedVersion + 1")
        if self.reason not in REWRITE_REASONS:
            raise ValueError(
                "rewrite reason must be one of: " + ", ".join(REWRITE_REASONS)
            )
        if not self.source_object_ref.strip() or not self.source_task_id.strip():
            raise ValueError("rewrite source object and task bindings are required")
        if not _SHA256.fullmatch(self.source_payload_digest):
            raise ValueError("rewrite sourcePayloadDigest must be a canonical sha256 digest")
        if not self.target_name.strip():
            raise ValueError("rewrite targetName must be non-empty")
        if self.content_type not in {"article", "image", "video"}:
            raise ValueError("rewrite contentType must be article, image, or video")
        if self.variant_purpose not in {"original", "commercial_variant"}:
            raise ValueError("rewrite variantPurpose is invalid")

    @classmethod
    def from_document(cls, value: object) -> "RewriteBinding":
        if not isinstance(value, Mapping) or set(value) != _REWRITE_KEYS:
            raise ValueError("rewrite binding keys are incomplete or unknown")
        expected = value.get("expectedVersion")
        next_version = value.get("nextVersion")
        if (
            isinstance(expected, bool)
            or not isinstance(expected, int)
            or isinstance(next_version, bool)
            or not isinstance(next_version, int)
        ):
            raise ValueError("rewrite versions must be integers")
        return cls(
            content_id=str(value.get("contentId") or "").strip(),
            expected_version=expected,
            next_version=next_version,
            reason=str(value.get("reason") or "").strip(),
            source_object_ref=str(value.get("sourceObjectRef") or "").strip(),
            source_task_id=str(value.get("sourceTaskId") or "").strip(),
            source_payload_digest=str(value.get("sourcePayloadDigest") or "").strip(),
            target_name=str(value.get("targetName") or "").strip(),
            content_type=str(value.get("contentType") or "").strip(),
            variant_purpose=str(value.get("variantPurpose") or "").strip(),
        )

    def to_document(self) -> dict[str, object]:
        return {
            "contentId": self.content_id,
            "expectedVersion": self.expected_version,
            "nextVersion": self.next_version,
            "reason": self.reason,
            "sourceObjectRef": self.source_object_ref,
            "sourceTaskId": self.source_task_id,
            "sourcePayloadDigest": self.source_payload_digest,
            "targetName": self.target_name,
            "contentType": self.content_type,
            "variantPurpose": self.variant_purpose,
        }


def _content_records(
    publish_root: Path,
    content_id: str,
) -> list[tuple[int, Path, dict[str, Any]]]:
    rows: list[tuple[int, Path, dict[str, Any]]] = []
    posts_root = publish_root.resolve() / "posts"
    if not posts_root.is_dir():
        raise ValueError("DATA.POOL.CONTENT_NOT_FOUND: canonical posts pool is missing")
    for path in posts_root.rglob("_pool/versions/*.json"):
        payload = read_json(path)
        if not isinstance(payload, dict):
            continue
        if payload.get("objectType") != "content" or payload.get("objectId") != content_id:
            continue
        version = payload.get("version")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError(
                f"DATA.POOL.VERSION_CONFLICT: contentId={content_id} has invalid version"
            )
        rows.append((version, path, payload))
    return sorted(rows, key=lambda row: (row[0], row[1].as_posix()))


def resolve_rewrite_binding(
    *,
    content_id: str,
    expected_version: int,
    reason: str,
    retry_of: str,
    content_type: str,
    publish_root: Path,
) -> RewriteBinding:
    """Resolve one current pool object without changing the pool or a release."""

    normalized_id = str(content_id or "").strip()
    normalized_retry = str(retry_of or "").strip()
    if not normalized_id:
        raise ValueError("rewrite contentId must be non-empty")
    if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 1:
        raise ValueError("rewrite expectedVersion must be a positive integer")
    if reason not in REWRITE_REASONS:
        raise ValueError("rewrite reason must be one of: " + ", ".join(REWRITE_REASONS))
    if not normalized_retry:
        raise ValueError("targeted rewrite requires --retry-of")
    rows = _content_records(publish_root, normalized_id)
    if not rows:
        raise ValueError(f"DATA.POOL.CONTENT_NOT_FOUND: contentId={normalized_id}")
    latest_version = rows[-1][0]
    latest_rows = [row for row in rows if row[0] == latest_version]
    if len(latest_rows) != 1 or latest_version != expected_version:
        raise ValueError(
            "DATA.POOL.VERSION_CONFLICT: "
            f"contentId={normalized_id} expected={expected_version} actual={latest_version}"
        )
    _, record_path, record = latest_rows[0]
    if (
        record.get("processResult") != "completed"
        or record.get("qualityResult") != "passed"
        or record.get("eligibilityResult") != "passed"
        or record.get("status") != "active"
    ):
        raise ValueError(
            f"DATA.POOL.CONTENT_NOT_REWRITEABLE: contentId={normalized_id} is not active and admitted"
        )
    payload_digest = str(record.get("payloadDigest") or "").strip()
    if not _SHA256.fullmatch(payload_digest):
        raise ValueError("rewrite source pool record has invalid payloadDigest")
    object_root = record_path.parents[2]
    object_ref = object_root.relative_to(publish_root.resolve() / "posts").as_posix()
    if str(record.get("objectRef") or "").strip() != object_ref:
        raise ValueError("rewrite source pool record objectRef drift")
    manifest = read_json(object_root / "manifest.json")
    if not isinstance(manifest, dict):
        raise ValueError("rewrite source manifest must be an object")
    manifest_id = str(manifest.get("contentId") or "").strip()
    if manifest_id and manifest_id != normalized_id:
        raise ValueError("rewrite source manifest contentId drift")
    manifest_version = manifest.get("version")
    if manifest_version is not None and manifest_version != expected_version:
        raise ValueError("rewrite source manifest version drift")
    actual_type = str(manifest.get("contentType") or manifest.get("carrier") or "").strip()
    if actual_type != content_type:
        raise ValueError(
            f"rewrite contentType mismatch: requested={content_type} actual={actual_type}"
        )
    source_task_id = str(
        manifest.get("sourceTaskId") or manifest.get("executionId") or ""
    ).strip()
    if source_task_id != normalized_retry:
        raise ValueError(
            "targeted rewrite --retry-of must equal the current version sourceTaskId"
        )
    target_name = str(manifest.get("topicId") or "").strip()
    if not target_name:
        raise ValueError("rewrite source manifest topicId is required")
    return RewriteBinding(
        content_id=normalized_id,
        expected_version=expected_version,
        next_version=expected_version + 1,
        reason=reason,
        source_object_ref=object_ref,
        source_task_id=source_task_id,
        source_payload_digest=payload_digest,
        target_name=target_name,
        content_type=content_type,
        variant_purpose=str(manifest.get("variantPurpose") or "original").strip(),
    )


def resolve_rewrite_from_args(
    args: argparse.Namespace,
    *,
    publish_root: Path,
) -> RewriteBinding | None:
    raw_id = str(getattr(args, "rewrite_content_id", "") or "").strip()
    raw_version = getattr(args, "expected_version", None)
    raw_reason = str(getattr(args, "rewrite_reason", "") or "").strip()
    supplied = (bool(raw_id), raw_version is not None, bool(raw_reason))
    if not any(supplied):
        return None
    if not all(supplied):
        raise SystemExit(
            "[task execute] GATE_BLOCK --rewrite-content-id, --expected-version "
            "and --rewrite-reason must be provided together"
        )
    try:
        return resolve_rewrite_binding(
            content_id=raw_id,
            expected_version=raw_version,
            reason=raw_reason,
            retry_of=str(getattr(args, "retry_of", "") or ""),
            content_type=str(getattr(args, "content_type", "") or ""),
            publish_root=publish_root,
        )
    except ValueError as exc:
        raise SystemExit(f"[task execute] GATE_BLOCK {exc}") from exc


def rewrite_target_rows(
    binding: RewriteBinding,
    *,
    retry_of: str,
    load_frozen_target_set: Callable[[str], dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    target_set = load_frozen_target_set(retry_of)
    targets = target_set.get("targets")
    if not isinstance(targets, list):
        raise SystemExit("[task execute] GATE_BLOCK rewrite predecessor target set is invalid")
    matches = [
        dict(row)
        for row in targets
        if isinstance(row, Mapping)
        and str(row.get("name") or "").strip() == binding.target_name
    ]
    if len(matches) != 1:
        raise SystemExit(
            "[task execute] GATE_BLOCK rewrite target must resolve exactly once "
            "in the predecessor target set"
        )
    return tuple(matches)


def apply_rewrite_identity(
    manifest: Mapping[str, Any],
    *,
    ref: str,
    binding: RewriteBinding,
) -> dict[str, Any]:
    """Bind generated bytes to the old work ID and exactly one new version."""

    if str(ref or "").strip() != binding.target_name:
        raise ValueError(
            "targeted rewrite may only materialize the only target object "
            f"{binding.target_name!r}"
        )
    actual_type = str(manifest.get("contentType") or manifest.get("carrier") or "").strip()
    if actual_type != binding.content_type:
        raise ValueError("targeted rewrite materialized a different contentType")
    rewritten = dict(manifest)
    rewritten.update(
        {
            "contentId": binding.content_id,
            "version": binding.next_version,
            "sourceType": "data",
            "variantPurpose": binding.variant_purpose,
            "status": "active",
        }
    )
    return rewritten


def execution_rewrite_binding(execution_id: str) -> RewriteBinding | None:
    from content.execution.workspace import execution_request_path

    request = read_json(execution_request_path(execution_id))
    if not isinstance(request, dict) or request.get("rewrite") is None:
        return None
    return RewriteBinding.from_document(request["rewrite"])


def apply_execution_rewrite_identity(
    manifest: Mapping[str, Any],
    *,
    execution_id: str,
    ref: str,
) -> dict[str, Any]:
    binding = execution_rewrite_binding(execution_id)
    if binding is None:
        return dict(manifest)
    return apply_rewrite_identity(manifest, ref=ref, binding=binding)


__all__ = [
    "REWRITE_REASONS",
    "RewriteBinding",
    "apply_execution_rewrite_identity",
    "apply_rewrite_identity",
    "execution_rewrite_binding",
    "resolve_rewrite_binding",
    "resolve_rewrite_from_args",
    "rewrite_target_rows",
]
