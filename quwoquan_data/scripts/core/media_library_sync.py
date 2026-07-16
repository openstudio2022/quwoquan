"""Canonical media/objects CAS → 环境媒体根增量同步（sha256 校验）。

source_root 是 canonical publish 根，唯一 CAS 布局：
  media/objects/sha256/{aa}/{bb}/{fullhash}.{ext}

环境媒体根（gamma-local: `env/gamma/local/gamma-local/process/media`；prod-hosted: host bind 的
`env/prod/local/prod-hosted/process/media`，边缘 root=/srv/media）以同一相对布局承载对象文件，
media edge 直接 file_server 提供 `<base>/media/objects/...`。

同步语义（fail closed）：
- 源对象文件名 stem 必须等于内容 sha256，否则记 issue 且不搬运；
- 目标已存在且内容 sha256 与文件名一致 → skip（增量）；
- 目标存在但内容不一致 → 重新拷贝并记 repaired；
- 拷贝走临时文件 + rename（同目录原子替换），拷贝后再校验一次。
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from collections.abc import Iterable
from typing import Any

from core.paths import REPO_ROOT, now_iso

MEDIA_SYNC_SCHEMA_VERSION = "quwoquan_data.media_library_sync/1"
_CAS_RELATIVE_ROOT = Path("media") / "objects" / "sha256"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_verified(source: Path, target: Path, expected_hash: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".sync-tmp")
    shutil.copy2(source, tmp)
    actual = _file_sha256(tmp)
    if actual != expected_hash:
        tmp.unlink(missing_ok=True)
        raise ValueError(f"post-copy hash mismatch: expected {expected_hash}, got {actual}")
    tmp.replace(target)


def sync_media_library(
    source_root: Path,
    dest_root: Path,
    *,
    verify_existing: bool = True,
    object_keys: Iterable[str] | None = None,
) -> dict[str, Any]:
    """把 CAS 库对象增量同步进环境媒体根，返回可归档的同步报告。

    ``object_keys`` is the required release closure for ship/import.  The
    unscoped form remains available only to the explicit media-library command.
    """
    source_root = Path(source_root)
    dest_root = Path(dest_root)
    cas_root = source_root / _CAS_RELATIVE_ROOT
    report: dict[str, Any] = {
        "schemaVersion": MEDIA_SYNC_SCHEMA_VERSION,
        "sourceRoot": _portable_path(source_root),
        "destRoot": _portable_path(dest_root),
        "copied": 0,
        "skipped": 0,
        "repaired": 0,
        "failed": 0,
        "bytesCopied": 0,
        "objects": 0,
        "scope": "selected" if object_keys is not None else "all",
        "requestedObjects": 0,
        "issues": [],
        "syncedAt": now_iso(),
    }
    if not cas_root.is_dir():
        report["issues"].append(f"source CAS root missing: {cas_root}")
        return report

    if object_keys is None:
        source_files = [
            path for path in sorted(cas_root.rglob("*"))
            if path.is_file() and not path.name.endswith(".sync-tmp")
        ]
    else:
        selected: set[Path] = set()
        for raw_key in object_keys:
            key = str(raw_key or "").strip()
            candidate = Path(key)
            if (
                not key
                or candidate.is_absolute()
                or ".." in candidate.parts
                or not candidate.as_posix().startswith(_CAS_RELATIVE_ROOT.as_posix() + "/")
            ):
                report["issues"].append(f"unsafe selected CAS object key: {key}")
                continue
            source_file = source_root / candidate
            if not source_file.is_file() or source_file.name.endswith(".sync-tmp"):
                report["issues"].append(f"selected CAS object missing: {key}")
                continue
            selected.add(source_file)
        report["requestedObjects"] = len(selected)
        source_files = sorted(selected)

    for source_file in source_files:
        report["objects"] += 1
        rel = source_file.relative_to(source_root)
        expected_hash = source_file.name.split(".", 1)[0]
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
    return report


def _portable_path(path: Path) -> str:
    try:
        resolved = Path(path).resolve()
    except OSError:
        resolved = Path(path).absolute()
    try:
        return resolved.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)
