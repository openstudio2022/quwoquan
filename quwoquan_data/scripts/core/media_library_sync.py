"""Immutable release payload → 环境媒体根增量同步（sha256 校验）。

source_root 是 immutable release payload 根，只读取 manifest 选中的交付 key：
commercial release 交付 avatar/image/video public slice；research release 交付
CAS objectKey（media/objects/sha256/...），字节只经短签 URL 服务，不产生公开
slice。两种形态都以 release 冻结的 manifest 作为唯一同步入口。

同步语义（fail closed）：
- public slice 源对象内容必须等于 manifest 中对应 MediaAsset.sha256；
- 目标已存在且内容 sha256 一致 → skip（增量）；
- 目标存在但内容不一致 → 重新拷贝并记 repaired；
- 拷贝走临时文件 + rename（同目录原子替换），拷贝后再校验一次。
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Mapping

from core.content_library import MEDIA_KIND, link_from_library
from core.paths import REPO_ROOT, now_iso

MEDIA_SYNC_SCHEMA_VERSION = "quwoquan_data.media_library_sync"
_PUBLIC_SLICE_PREFIXES = (
    "media/avatar/s/",
    "media/image/s/",
    "media/video/s/",
)
# research release 的交付 key 复用 CAS objectKey（DEC-031）；环境上传媒体共用
# 该前缀，因此 prune 永不触及 CAS 根，只回收 public slice。
_DELIVERY_KEY_PREFIXES = _PUBLIC_SLICE_PREFIXES + ("media/objects/sha256/",)
_SHA256_RE = re.compile(r"^sha256:([0-9a-f]{64})$")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_verified(source: Path, target: Path, expected_hash: str) -> None:
    """Expose one media body at ``target`` as a reference to its library entry.

    The public slice a release ships is the same bytes as the private body it was
    selected from, so the library owns them once and the slice is a reference.
    Admission refuses a source that does not match ``expected_hash``, which is the
    check the previous post-copy comparison performed.
    """
    link_from_library(source, target, kind=MEDIA_KIND, expected_sha256=expected_hash)


def sync_media_library(
    source_root: Path,
    dest_root: Path,
    *,
    verify_existing: bool = True,
    object_digests: Mapping[str, str],
    prune_unselected: bool = False,
) -> dict[str, Any]:
    """把 release 冻结的 public slice 增量同步进环境媒体根。

    ``object_digests`` is the release closure: the public slice keys the release
    ships and the digest each one must carry, so a slice filename never needs to
    encode or expose the private identity of the body behind it.
    ``prune_unselected`` removes stale slices after every selected object passes
    checksum verification, so a full-sync release cannot inherit fixture or
    prior-release media.
    """
    source_root = Path(source_root)
    dest_root = Path(dest_root)
    selected_digests = dict(object_digests)
    report: dict[str, Any] = {
        "schema": MEDIA_SYNC_SCHEMA_VERSION,
        "sourceRoot": _portable_path(source_root),
        "destRoot": _portable_path(dest_root),
        "copied": 0,
        "skipped": 0,
        "repaired": 0,
        "pruned": 0,
        "failed": 0,
        "bytesCopied": 0,
        "objects": 0,
        "scope": "public-slices",
        "requestedObjects": 0,
        "issues": [],
        "syncedAt": now_iso(),
    }
    if not selected_digests:
        if prune_unselected:
            _prune_public_slices(dest_root, expected=set(), report=report)
        return report

    expected_by_source: dict[Path, str] = {}
    selected: set[Path] = set()
    for raw_key, raw_digest in selected_digests.items():
        key = str(raw_key or "").strip()
        digest_match = _SHA256_RE.fullmatch(str(raw_digest or "").strip())
        candidate = Path(key)
        if (
            not key
            or candidate.is_absolute()
            or ".." in candidate.parts
            or not key.startswith(_DELIVERY_KEY_PREFIXES)
            or digest_match is None
        ):
            report["issues"].append(f"unsafe selected media delivery key: {key}")
            continue
        source_file = source_root / candidate
        if not source_file.is_file() or source_file.name.endswith(".sync-tmp"):
            report["issues"].append(f"selected media delivery body missing: {key}")
            continue
        selected.add(source_file)
        expected_by_source[source_file] = digest_match.group(1)
    report["requestedObjects"] = len(selected)
    source_files = sorted(selected)

    for source_file in source_files:
        report["objects"] += 1
        rel = source_file.relative_to(source_root)
        expected_hash = expected_by_source[source_file]
        source_hash = _file_sha256(source_file)
        if source_hash != expected_hash:
            report["failed"] += 1
            report["issues"].append(
                f"source object corrupt (name/content hash mismatch): {rel} content={source_hash}"
            )
            continue
        target = dest_root / rel
        if target.is_file():
            if not verify_existing or _file_sha256(target) == expected_hash:
                report["skipped"] += 1
                continue
            try:
                _copy_verified(source_file, target, expected_hash)
            except (OSError, ValueError) as exc:
                report["failed"] += 1
                report["issues"].append(f"repair failed: {rel}: {exc}")
                continue
            report["repaired"] += 1
            report["bytesCopied"] += source_file.stat().st_size
            continue
        try:
            _copy_verified(source_file, target, expected_hash)
        except (OSError, ValueError) as exc:
            report["failed"] += 1
            report["issues"].append(f"copy failed: {rel}: {exc}")
            continue
        report["copied"] += 1
        report["bytesCopied"] += source_file.stat().st_size
    if prune_unselected and not report["failed"] and not report["issues"]:
        _prune_public_slices(
            dest_root,
            expected={Path(key) for key in selected_digests},
            report=report,
        )
    return report


def _prune_public_slices(
    dest_root: Path,
    *,
    expected: set[Path],
    report: dict[str, Any],
) -> None:
    for prefix in _PUBLIC_SLICE_PREFIXES:
        slice_root = dest_root / prefix.rstrip("/")
        if not slice_root.is_dir():
            continue
        for path in sorted(slice_root.rglob("*"), reverse=True):
            if path.is_file():
                if path.relative_to(dest_root) not in expected:
                    path.unlink()
                    report["pruned"] += 1
                continue
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()


def _portable_path(path: Path) -> str:
    try:
        resolved = Path(path).resolve()
    except OSError:
        resolved = Path(path).absolute()
    try:
        return resolved.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)
