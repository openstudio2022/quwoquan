"""Secure public Pub mirror archive fallback for dependency sync."""

from __future__ import annotations

import hashlib
import json
import os
import tarfile
import tempfile
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from quwoquan_ops.cli.lib.package_reuse.dependency_fs import (
    read_regular_nofollow,
    write_fresh_relative_file,
)
from quwoquan_ops.cli.lib.package_reuse.pub_cache_capsule import _lock_model


PUBLIC_PUB_MIRROR = "https://pub.flutter-io.cn"
_PUBLIC_PUB_ORIGIN = "https://pub.dev"
_PUBLIC_PUB_MIRROR_ARCHIVE_PREFIX = (
    "https://storage.flutter-io.cn/dartlang-pub-exported-api/latest/api/archives/"
)


def public_pub_origin_archive_fallback(
    *,
    app_dir: Path,
    pub_cache: Path,
    log_path: Path,
    urlopen: Callable[..., Any] = urllib.request.urlopen,
) -> bool:
    """补齐公共 mirror 唯一缺失 archive；lock host 与 live source 均不改写。"""

    lock_path = app_dir / "pubspec.lock"
    _encoded, _lock_digest, hosted_packages = _lock_model(lock_path)
    hosted_root = pub_cache / "hosted" / "pub.flutter-io.cn"
    missing: list[tuple[str, str, str]] = []
    for package in hosted_packages:
        if package["url"] != PUBLIC_PUB_MIRROR:
            return False
        name = package["name"]
        version = package["version"]
        expected = package["archiveSha256"]
        if not (hosted_root / f"{name}-{version}").is_dir():
            missing.append((name, version, expected))
    if len(missing) != 1:
        return False
    name, version, expected = missing[0]
    metadata_path = hosted_root / ".cache" / f"{name}-versions.json"
    try:
        metadata = json.loads(
            read_regular_nofollow(metadata_path, label="public Pub mirror metadata")[0]
        )
    except (OSError, TypeError, UnicodeError, ValueError, json.JSONDecodeError):
        return False
    versions = metadata.get("versions") if isinstance(metadata, Mapping) else None
    selected = next(
        (
            item
            for item in versions or ()
            if isinstance(item, Mapping)
            and str(item.get("version") or "") == version
        ),
        None,
    )
    archive_url = str(selected.get("archive_url") or "") if selected else ""
    archive_sha = str(selected.get("archive_sha256") or "") if selected else ""
    if (
        not archive_url.startswith(_PUBLIC_PUB_MIRROR_ARCHIVE_PREFIX)
        or archive_sha != expected
    ):
        return False
    origin_url = f"{_PUBLIC_PUB_ORIGIN}/api/archives/{name}-{version}.tar.gz"
    request = urllib.request.Request(
        origin_url, headers={"User-Agent": "quwoquan-dependency-sync/1"}
    )
    try:
        with urlopen(request, timeout=30) as response:
            archive = response.read()
    except (OSError, urllib.error.URLError):
        return False
    if hashlib.sha256(archive).hexdigest() != expected:
        return False
    target = hosted_root / f"{name}-{version}"
    if target.exists() or target.is_symlink():
        return False
    with tempfile.TemporaryDirectory(prefix="qwq-pub-origin-fallback.", dir=pub_cache) as temporary:
        archive_path = Path(temporary) / "archive.tar.gz"
        archive_path.write_bytes(archive)
        extract_root = Path(temporary) / "extract"
        extract_root.mkdir(mode=0o700)
        with tarfile.open(archive_path, mode="r:gz") as tar:
            members = tar.getmembers()
            for member in members:
                member_path = Path(member.name)
                if (
                    member_path.is_absolute()
                    or ".." in member_path.parts
                    or member.issym()
                    or member.islnk()
                ):
                    return False
            tar.extractall(extract_root, members=members, filter="data")
        entries = list(extract_root.iterdir())
        source = (
            entries[0]
            if len(entries) == 1 and entries[0].is_dir()
            else extract_root
        )
        os.replace(source, target)
    # Canonical capsule 需要 archive SHA sidecar；它由 lock + mirror metadata +
    # origin archive 三方一致性校验后写入。fallback 后不再调用 Dart Pub，避免
    # Pub 将 origin 字节误判为 mirror cache 并再次命中同一个 403 archive。
    hash_root = pub_cache / "hosted-hashes" / "pub.flutter-io.cn"
    hash_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_fresh_relative_file(
        root=hash_root,
        relative=f"{name}-{version}.sha256",
        content=(expected + "\n").encode(),
        mode=0o600,
    )
    return True
