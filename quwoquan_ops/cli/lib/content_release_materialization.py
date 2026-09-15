"""Target-owned immutable content release materialization for container importers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
from typing import Any, Mapping

from content.release.canonical.producer_release_handoff import _artifact_inventory
from quwoquan_ops.cli.lib.output_paths import deployment_work_root

_HANDOFF_NAME = "producer_release_handoff.json"


class ContentReleaseMaterializationError(RuntimeError):
    """The admitted release cannot be represented as one exact managed copy."""


@dataclass(frozen=True, slots=True)
class MaterializedContentRelease:
    root: Path
    ref: str
    digest: str


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _safe_ref(value: object) -> str:
    ref = str(value or "")
    path = PurePosixPath(ref)
    if (
        not ref
        or path.is_absolute()
        or path.as_posix() != ref
        or "\\" in ref
        or any(part in {"", ".", ".."} for part in path.parts)
        or any(ord(character) < 32 or ord(character) == 127 for character in ref)
    ):
        raise ContentReleaseMaterializationError(
            f"OPS.CONTENT_RELEASE.MATERIALIZATION_REF_INVALID: {ref!r}"
        )
    return ref


def _assert_directory_chain(path: Path, *, root: Path) -> None:
    absolute_root = root.absolute()
    absolute_path = path.absolute()
    try:
        relative = absolute_path.relative_to(absolute_root)
    except ValueError as exc:
        raise ContentReleaseMaterializationError(
            "OPS.CONTENT_RELEASE.MATERIALIZATION_PATH_ESCAPE"
        ) from exc
    current = absolute_root
    for part in relative.parts:
        current = current / part
        if current.exists() or current.is_symlink():
            mode = os.lstat(current).st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise ContentReleaseMaterializationError(
                    f"OPS.CONTENT_RELEASE.MATERIALIZATION_UNSAFE_PARENT: {current}"
                )


def _handoff_document(admission: Any) -> tuple[dict[str, Any], bytes]:
    if getattr(admission, "admission_kind", "") != "producer_handoff":
        raise ContentReleaseMaterializationError(
            "OPS.CONTENT_RELEASE.MATERIALIZATION_HANDOFF_REQUIRED"
        )
    path = Path(admission.release) / _HANDOFF_NAME
    if path.is_symlink() or not path.is_file():
        raise ContentReleaseMaterializationError(
            "OPS.CONTENT_RELEASE.MATERIALIZATION_HANDOFF_UNSAFE"
        )
    raw = path.read_bytes()
    if _digest(raw) != admission.handoff_artifact_digest:
        raise ContentReleaseMaterializationError(
            "OPS.CONTENT_RELEASE.MATERIALIZATION_HANDOFF_DIGEST_DRIFT"
        )
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContentReleaseMaterializationError(
            "OPS.CONTENT_RELEASE.MATERIALIZATION_HANDOFF_INVALID"
        ) from exc
    if not isinstance(document, dict):
        raise ContentReleaseMaterializationError(
            "OPS.CONTENT_RELEASE.MATERIALIZATION_HANDOFF_INVALID"
        )
    release = document.get("release")
    if (
        document.get("releaseId") != admission.release_id
        or not isinstance(release, Mapping)
        or release.get("payloadDigest") != admission.manifest_digest
    ):
        raise ContentReleaseMaterializationError(
            "OPS.CONTENT_RELEASE.MATERIALIZATION_IDENTITY_DRIFT"
        )
    return document, raw


def _expected_inventory(admission: Any, document: Mapping[str, Any]) -> dict[str, Any]:
    expected = document.get("artifact")
    actual = _artifact_inventory(Path(admission.release))
    if not isinstance(expected, Mapping) or dict(expected) != actual:
        raise ContentReleaseMaterializationError(
            "OPS.CONTENT_RELEASE.MATERIALIZATION_SOURCE_INVENTORY_DRIFT"
        )
    if expected.get("rootRef") != f"data/releases/{admission.release_id}":
        raise ContentReleaseMaterializationError(
            "OPS.CONTENT_RELEASE.MATERIALIZATION_ROOT_IDENTITY_DRIFT"
        )
    return dict(expected)


def _verify_managed(
    root: Path, *, expected: Mapping[str, Any], handoff_raw: bytes
) -> None:
    _assert_directory_chain(root, root=root.parent.parent.parent)
    if root.is_symlink() or not root.is_dir():
        raise ContentReleaseMaterializationError(
            "OPS.CONTENT_RELEASE.MATERIALIZATION_TARGET_UNSAFE"
        )
    actual = _artifact_inventory(root)
    actual["rootRef"] = expected.get("rootRef")
    if actual != dict(expected):
        raise ContentReleaseMaterializationError(
            "OPS.CONTENT_RELEASE.MATERIALIZATION_TARGET_CONFLICT"
        )
    handoff = root / _HANDOFF_NAME
    if handoff.is_symlink() or not handoff.is_file() or handoff.read_bytes() != handoff_raw:
        raise ContentReleaseMaterializationError(
            "OPS.CONTENT_RELEASE.MATERIALIZATION_TARGET_CONFLICT"
        )


def _copy_inventory(
    source: Path,
    staging: Path,
    *,
    expected: Mapping[str, Any],
    handoff_raw: bytes,
) -> None:
    entries = expected.get("entries")
    if not isinstance(entries, list):
        raise ContentReleaseMaterializationError(
            "OPS.CONTENT_RELEASE.MATERIALIZATION_INVENTORY_INVALID"
        )
    for row in entries:
        if not isinstance(row, Mapping):
            raise ContentReleaseMaterializationError(
                "OPS.CONTENT_RELEASE.MATERIALIZATION_INVENTORY_INVALID"
            )
        ref = _safe_ref(row.get("ref"))
        source_path = source / PurePosixPath(ref)
        if source_path.is_symlink() or not source_path.is_file():
            raise ContentReleaseMaterializationError(
                f"OPS.CONTENT_RELEASE.MATERIALIZATION_SOURCE_UNSAFE: {ref}"
            )
        raw = source_path.read_bytes()
        if row.get("digest") != _digest(raw) or row.get("bytes") != len(raw):
            raise ContentReleaseMaterializationError(
                f"OPS.CONTENT_RELEASE.MATERIALIZATION_SOURCE_DIGEST_DRIFT: {ref}"
            )
        target = staging / PurePosixPath(ref)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    (staging / _HANDOFF_NAME).write_bytes(handoff_raw)


def materialize_content_release(admission: Any, *, target_name: str) -> MaterializedContentRelease:
    """Create-or-same one target-owned copy from the admitted portable inventory."""

    document, handoff_raw = _handoff_document(admission)
    expected = _expected_inventory(admission, document)
    tree_digest = str(expected.get("treeDigest") or "")
    if not tree_digest.startswith("sha256:") or len(tree_digest) != 71:
        raise ContentReleaseMaterializationError(
            "OPS.CONTENT_RELEASE.MATERIALIZATION_TREE_DIGEST_INVALID"
        )
    target_root = deployment_work_root(target_name)
    releases_root = target_root
    target_root.mkdir(parents=True, exist_ok=True)
    for segment in ("content-release", "releases", admission.release_id):
        releases_root = releases_root / segment
        if releases_root.exists() or releases_root.is_symlink():
            mode = os.lstat(releases_root).st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise ContentReleaseMaterializationError(
                    f"OPS.CONTENT_RELEASE.MATERIALIZATION_UNSAFE_PARENT: {releases_root}"
                )
        else:
            releases_root.mkdir()
    digest_root = releases_root / tree_digest.replace(":", "-")
    destination = digest_root / admission.release_id
    _assert_directory_chain(releases_root, root=target_root)
    if destination.exists() or destination.is_symlink():
        _verify_managed(destination, expected=expected, handoff_raw=handoff_raw)
    else:
        if digest_root.exists() or digest_root.is_symlink():
            mode = os.lstat(digest_root).st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise ContentReleaseMaterializationError(
                    f"OPS.CONTENT_RELEASE.MATERIALIZATION_UNSAFE_DIGEST_ROOT: {digest_root}"
                )
        else:
            digest_root.mkdir(mode=0o700)
        staging = Path(tempfile.mkdtemp(prefix=".materializing-", dir=digest_root))
        try:
            _copy_inventory(
                Path(admission.release), staging,
                expected=expected, handoff_raw=handoff_raw,
            )
            _verify_managed(staging, expected=expected, handoff_raw=handoff_raw)
            try:
                os.rename(staging, destination)
            except OSError:
                if not destination.exists() and not destination.is_symlink():
                    raise
                _verify_managed(destination, expected=expected, handoff_raw=handoff_raw)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    if (
        _artifact_inventory(Path(admission.release)) != expected
        or (Path(admission.release) / _HANDOFF_NAME).read_bytes() != handoff_raw
    ):
        raise ContentReleaseMaterializationError(
            "OPS.CONTENT_RELEASE.MATERIALIZATION_SOURCE_DRIFT"
        )
    ref = digest_root.relative_to(target_root).as_posix()
    return MaterializedContentRelease(destination, ref, tree_digest)
