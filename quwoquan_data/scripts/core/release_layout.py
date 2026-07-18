"""Single immutable layout for environment-neutral data releases.

The release root is only a container.  Deployable objects and desired state live
under ``payload/``; verification evidence lives under ``attestations/``.  No
reader is allowed to fall back to a historical flat release tree.
"""
from __future__ import annotations

from pathlib import Path

from core.tree_integrity import tree_integrity_stats


PAYLOAD_DIR = "payload"
ATTESTATIONS_DIR = "attestations"
RELEASE_HEADER = "release.json"
DESIRED_STATE = "desired_state.json"
OBJECT_INDEX = "index/objects.json"
SAMPLE_BUNDLE = "sample_bundle.json"
MEDIA_MANIFEST = "media_manifest.json"


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


def object_closure_digest(release_root: Path, *, create: bool = False) -> str:
    """Return the Merkle root of only the immutable selected object closure."""
    root = payload_file(release_root, "objects")
    if create:
        root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise FileNotFoundError(f"release object closure is missing: {root}")
    return str(tree_integrity_stats(root)["merkleRoot"])


def required_payload_paths(release_root: Path) -> tuple[Path, ...]:
    return tuple(
        payload_file(release_root, name)
        for name in (RELEASE_HEADER, DESIRED_STATE, OBJECT_INDEX, SAMPLE_BUNDLE, MEDIA_MANIFEST)
    )


__all__ = [
    "ATTESTATIONS_DIR",
    "DESIRED_STATE",
    "MEDIA_MANIFEST",
    "OBJECT_INDEX",
    "PAYLOAD_DIR",
    "RELEASE_HEADER",
    "SAMPLE_BUNDLE",
    "attestation_root",
    "object_closure_digest",
    "payload_digest",
    "payload_file",
    "payload_root",
    "required_payload_paths",
]
