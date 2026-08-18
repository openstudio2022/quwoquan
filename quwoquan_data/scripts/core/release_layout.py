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
    The media holdings the release references: the addresses of the media bodies
    it claims, not the bodies themselves.  Media bodies are owned once by the
    content library and referenced into ``payload/media``, so this digest binds
    the holdings while ``verify_release_holdings`` proves each one is still
    reachable in the library at the address the release recorded.

    Deliberately not named ``mediaClosureDigest``: that name already belongs to
    ``content/execution/closure/pool_delivery.py``, where it digests a delivery
    intent's asset manifest rows.  Two digests over different inputs must not
    share one name, so the release-side concept carries the narrower word it
    actually means -- the holdings it claims.
"""
from __future__ import annotations

from pathlib import Path

from core.content_library import MediaHoldingError, resolve_media_holding
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
    """Return one issue per holding that the content library cannot honour.

    This is the immutable check for referenced media: the release is intact when
    every holding it declares is reachable in the library at the digest it
    recorded, which is strictly stronger than the payload bytes being present,
    because a reference and its library entry are the same bytes.
    """
    issues: list[str] = []
    for path, digest, size in release_holdings(release_root):
        try:
            resolve_media_holding(digest, expected_bytes=size)
        except MediaHoldingError as exc:
            issues.append(f"{exc}: {path}")
    return tuple(issues)


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
