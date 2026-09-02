"""Digest, file, and output-root helpers for source-pool bindings."""
from __future__ import annotations

import hashlib
import json
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.content_library import (
    MEDIA_KIND,
    link_from_library,
)

from content.source.media_source_admission import MediaSourceAdmissionQuery
from content.source.research.scale_source_pool import SOURCE_POOL_SHORTFALL


def digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return "sha256:" + value.hexdigest()


def relative_to_output(path: Path, root: Path, *, label: str) -> str:
    resolved = path.expanduser().resolve()
    try:
        relative = resolved.relative_to(root.expanduser().resolve())
    except ValueError as exc:
        raise ValueError(
            f"{SOURCE_POOL_SHORTFALL}: {label} must be inside output root"
        ) from exc
    if not relative.parts:
        raise ValueError(f"{SOURCE_POOL_SHORTFALL}: {label} cannot equal output root")
    return relative.as_posix()


def shortfall(exc: BaseException) -> ValueError:
    return ValueError(f"{SOURCE_POOL_SHORTFALL}: {exc}")


def safe_evidence_file(root: Path, ref: str) -> Path:
    relative = Path(ref)
    if not ref or relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe source-pool evidence ref: {ref!r}")
    current = root
    for index, part in enumerate(relative.parts):
        current = current / part
        mode = current.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise ValueError(f"source-pool evidence ref traverses symlink: {ref}")
        final = index == len(relative.parts) - 1
        if (final and not stat.S_ISREG(mode)) or (
            not final and not stat.S_ISDIR(mode)
        ):
            raise ValueError(f"source-pool evidence ref is not a file: {ref}")
    return current


def safe_evidence_directory(root: Path, ref: str) -> Path:
    relative = Path(ref)
    if not ref or relative.is_absolute() or (ref != "." and ".." in relative.parts):
        raise ValueError(f"unsafe source-ready evidence root ref: {ref!r}")
    current = root
    if ref == ".":
        return current
    for part in relative.parts:
        current = current / part
        mode = current.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise ValueError(
                f"source-ready evidence root traverses symlink or non-directory: {ref}"
            )
    return current


def media_source_admission_refs(
    candidate: Mapping[str, Any], *, evidence_root: Path
) -> dict[str, str]:
    result = MediaSourceAdmissionQuery(evidence_root).require_accepted(
        str(candidate.get("sourceAdmissionRef") or "")
    )
    receipt = result["receipt"]
    if (
        result["receiptDigest"] != candidate.get("sourceAdmissionDigest")
        or receipt.get("assetKind") != candidate.get("carrier")
        or (
            candidate.get("objectRef") is not None
            and receipt.get("objectRef") != candidate.get("objectRef")
        )
    ):
        raise ValueError("selected media source admission projection drift")
    refs = {
        result["receiptRef"]: file_sha256(
            safe_evidence_file(evidence_root, result["receiptRef"])
        )
    }
    for binding in receipt["evidenceBindings"]:
        previous = refs.setdefault(binding["ref"], binding["fileSha256"])
        if previous != binding["fileSha256"]:
            raise ValueError(f"source-pool evidence digest collision: {binding['ref']}")
        # host review result 的可复验闭包包含其冻结 request 与 request 绑定的证据。
        if binding.get("role") == "source_semantic_review":
            _add_host_review_closure_refs(
                refs, evidence_root=evidence_root, result_ref=str(binding["ref"])
            )
    asset_ref = str(receipt["assetSnapshot"]["assetRef"])
    asset_sha = file_sha256(safe_evidence_file(evidence_root, asset_ref))
    previous = refs.setdefault(asset_ref, asset_sha)
    if previous != asset_sha:
        raise ValueError(f"source-pool evidence digest collision: {asset_ref}")
    return refs


def _add_host_review_closure_refs(
    refs: dict[str, str], *, evidence_root: Path, result_ref: str
) -> None:
    result_doc = json.loads(
        safe_evidence_file(evidence_root, result_ref).read_text(encoding="utf-8")
    )
    request_ref = str(result_doc.get("requestRef") or "")
    if not request_ref:
        raise ValueError(f"host source review result lacks requestRef: {result_ref}")
    request_path = safe_evidence_file(evidence_root, request_ref)
    request_sha = file_sha256(request_path)
    if refs.setdefault(request_ref, request_sha) != request_sha:
        raise ValueError(f"source-pool evidence digest collision: {request_ref}")
    request_doc = json.loads(request_path.read_text(encoding="utf-8"))
    for row in request_doc.get("evidenceBindings") or ():
        ref = str(row.get("ref") or "")
        sha = str(row.get("fileSha256") or "")
        if not ref or not sha:
            raise ValueError(f"host source review request binding is incomplete: {request_ref}")
        if refs.setdefault(ref, sha) != sha:
            raise ValueError(f"source-pool evidence digest collision: {ref}")


def link_evidence_surface_from_library(
    refs: Mapping[str, str],
    *,
    source_evidence: Path,
    target_evidence: Path,
    library_root: Path,
) -> None:
    """Materialize a capsule's evidence surface by reference, not by copy.

    多个 capsule 选中同一候选时复制的是完全相同的字节。入库一次后按 digest 引用：
    capsule 表面的路径、大小与内容摘要不变，字节只由内容库单一持有。
    """
    for ref, expected in sorted(refs.items()):
        source = safe_evidence_file(source_evidence, ref)
        if file_sha256(source) != expected:
            raise ValueError(f"{SOURCE_POOL_SHORTFALL}: evidence drift: {ref}")
        target = target_evidence / ref
        target.parent.mkdir(parents=True, exist_ok=True)
        link_from_library(
            source,
            target,
            kind=MEDIA_KIND,
            library_root=library_root,
            expected_sha256=expected,
        )


__all__ = [
    "digest",
    "file_sha256",
    "link_evidence_surface_from_library",
    "media_source_admission_refs",
    "relative_to_output",
    "safe_evidence_directory",
    "safe_evidence_file",
    "shortfall",
]
