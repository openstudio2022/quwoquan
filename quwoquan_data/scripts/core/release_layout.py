"""Single immutable layout for environment-neutral data releases.

The release root is only a container.  Deployable objects and desired state live
under ``payload/``; verification evidence lives under ``attestations/``.  No
reader is allowed to fall back to a historical flat release tree.

A release holds two separable closures, and this module is the only place that
derives either of them:

``objects_merkle``
    The object closure the release decides: every selected object document under
    ``payload/objects``.  Two releases that decided the same objects share this
    digest regardless of when they were cut, which is what makes adoption and
    closure equality comparable across releases.

``media_holdings_digest``
    release 随体媒体的路径与摘要。``verify_release_holdings`` 从 media manifest
    校验实际包内字节，不再要求原作者机器的 content library 可达。
    该完整性校验不创建缓存、不补库，也不把 URL 可解析冒充网络可访问。

    Deliberately not named ``mediaClosureDigest``: that name already belongs to
    ``content/execution/closure/pool_delivery.py``, where it digests a delivery
    intent's asset manifest rows.  Two digests over different inputs must not
    share one name, so the release-side concept carries the narrower word it
    actually means -- the holdings it claims.
"""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from core.content_library import file_sha256
from core.tree_integrity import (
    holdings_merkle,
    tree_integrity_entries,
    tree_integrity_stats,
)


PAYLOAD_DIR = "payload"
ATTESTATIONS_DIR = "attestations"
RELEASE_HEADER = "release.json"
DESIRED_STATE = "desired_state.json"
OBJECT_INDEX = "index/objects.json"
SAMPLE_BUNDLE = "sample_bundle.json"
MEDIA_MANIFEST = "media_manifest.json"
MEDIA_DIR = "media"


def payload_root(release_root: Path) -> Path:
    return release_root / PAYLOAD_DIR


def attestation_root(release_root: Path) -> Path:
    return release_root / ATTESTATIONS_DIR


def payload_file(release_root: Path, relative_path: str) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe release payload path: {relative_path}")
    return payload_root(release_root) / relative


def payload_digest(release_root: Path) -> str:
    root = payload_root(release_root)
    if not root.is_dir():
        raise FileNotFoundError(f"release payload is missing: {root}")
    return str(tree_integrity_stats(root)["merkleRoot"])


def objects_merkle(release_root: Path, *, create: bool = False) -> str:
    """Return the Merkle root of only the immutable selected object closure."""
    root = payload_file(release_root, "objects")
    if create:
        root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise FileNotFoundError(f"release object closure is missing: {root}")
    return str(tree_integrity_stats(root)["merkleRoot"])


def release_holdings(release_root: Path) -> tuple[tuple[str, str, int], ...]:
    """Return the sorted ``(payload path, sha256, bytes)`` media holdings.

    A holding is a claim on a library entry: the digest is simultaneously the
    content identity and the library address, so no separate reference table can
    drift away from the bytes.
    """
    root = payload_file(release_root, MEDIA_DIR)
    if not root.is_dir():
        return ()
    return tuple(
        (str(row["path"]), str(row["sha256"]), int(row["bytes"]))
        for row in tree_integrity_entries(root)
    )


def media_holdings_digest(release_root: Path) -> str:
    """Return the digest binding which library entries this release holds.

    Derived from the holdings rather than from a second payload walk, so the
    digest stays a function of the addresses the release recorded and cannot
    disagree with ``release_holdings``.
    """
    return holdings_merkle(release_holdings(release_root))


def verify_release_holdings(release_root: Path) -> tuple[str, ...]:
    """逐项核实 manifest 声明的随包字节；不访问作者机器的 library，也不隐式修复。"""
    manifest = payload_file(release_root, MEDIA_MANIFEST)
    if any(path.is_symlink() for path in (manifest, *manifest.parents)):
        return ("DATA.RELEASE.MEDIA_SYMLINK: media_manifest.json",)
    try:
        document = json.loads(manifest.read_bytes())
    except (OSError, ValueError):
        return ("DATA.RELEASE.MEDIA_MANIFEST_MISSING_OR_INVALID",)
    if not isinstance(document, dict) or not isinstance(document.get("assets"), list):
        return ("DATA.RELEASE.MEDIA_MANIFEST_INVALID",)
    issues: list[str] = []
    seen: set[str] = set()
    for row in document["assets"]:
        issue = _verify_media_row(release_root, row, seen)
        if issue:
            issues.append(issue)
    return tuple(issues)


def _verify_media_row(release_root: Path, row: object, seen: set[str]) -> str:
    if not isinstance(row, dict):
        return "DATA.RELEASE.MEDIA_MANIFEST_INVALID"
    key = row.get("publicSliceKey")
    if (not isinstance(key, str) or not key.startswith("media/") or "\\\\" in key
            or any(part in {"", ".", ".."} for part in key.split("/"))
            or PurePosixPath(key).is_absolute() or key in seen):
        return "DATA.RELEASE.MEDIA_REF_INVALID"
    seen.add(key)
    media = payload_file(release_root, key)
    if any(part.is_symlink() for part in (media, *media.parents)):
        return f"DATA.RELEASE.MEDIA_SYMLINK: {key}"
    if not media.is_file():
        return f"DATA.RELEASE.MEDIA_MISSING: {key}"
    try:
        size = row.get("bytes")
        if (type(size) is not int or size <= 0 or media.stat().st_size != size
                or "sha256:" + file_sha256(media) != row.get("sha256")):
            return f"DATA.RELEASE.MEDIA_DRIFT: {key}"
    except OSError:
        return f"DATA.RELEASE.MEDIA_UNREADABLE: {key}"
    return ""


def required_payload_paths(release_root: Path) -> tuple[Path, ...]:
    return tuple(
        payload_file(release_root, name)
        for name in (RELEASE_HEADER, DESIRED_STATE, OBJECT_INDEX, SAMPLE_BUNDLE, MEDIA_MANIFEST)
    )


__all__ = [
    "ATTESTATIONS_DIR",
    "DESIRED_STATE",
    "MEDIA_DIR",
    "MEDIA_MANIFEST",
    "OBJECT_INDEX",
    "PAYLOAD_DIR",
    "RELEASE_HEADER",
    "SAMPLE_BUNDLE",
    "attestation_root",
    "media_holdings_digest",
    "objects_merkle",
    "payload_digest",
    "payload_file",
    "payload_root",
    "release_holdings",
    "required_payload_paths",
    "verify_release_holdings",
]
