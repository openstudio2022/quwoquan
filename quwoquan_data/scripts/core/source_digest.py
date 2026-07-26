"""Derive the immutable repository-input digest for data executions and releases.

The digest is evidence, not a second source of truth.  It names only tracked
input roots and hashes their files in a deterministic order, so deleting
``.qwq_output`` never removes configuration required to rebuild an execution.
"""
from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
import subprocess
import tarfile
from typing import Mapping

from core.paths import REPO_ROOT


_INPUT_ROOTS = (
    "quwoquan_data/scripts",
    "quwoquan_data/schema",
    "quwoquan_data/control_plane",
    "quwoquan_data/prompts",
    "quwoquan_data/templates",
    "quwoquan_data/verticals/travel",
    "quwoquan_data/reference",
    "quwoquan_data/requirements.txt",
    "quwoquan_service/services/content-service/contracts/media/media_asset",
)
# Data execution identity is deliberately environment-neutral. Environment
# topology and readiness policy apply only when an immutable release is shipped.
_DIGEST_PREFIX = "sha256:"
_EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".DS_Store", ".gitkeep"}


class SourceDigestError(ValueError):
    """The repository inputs cannot be represented by the fixed digest contract."""


@dataclass(frozen=True, slots=True)
class SourceDigest:
    """A compact, reproducible fingerprint of the data production inputs."""

    digest: str

    @classmethod
    def build(cls, *, repo_root: Path = REPO_ROOT) -> "SourceDigest":
        digest = hashlib.sha256()
        for relative_root in _INPUT_ROOTS:
            root = repo_root / relative_root
            if not root.exists():
                raise SourceDigestError(f"source digest input is missing: {relative_root}")
            for path in _iter_files(root):
                relative = path.relative_to(repo_root).as_posix()
                digest.update(relative.encode("utf-8"))
                digest.update(b"\0")
                digest.update(_file_sha256(path).encode("ascii"))
                digest.update(b"\n")
        return cls(digest=_DIGEST_PREFIX + digest.hexdigest())

    @classmethod
    def from_document(cls, value: object) -> "SourceDigest":
        if not isinstance(value, Mapping):
            raise SourceDigestError("sourceDigest must be an object")
        if set(value) != {"algorithm", "digest", "inputs"}:
            raise SourceDigestError("sourceDigest fields are invalid")
        if value.get("algorithm") != "sha256":
            raise SourceDigestError("sourceDigest.algorithm must be sha256")
        digest = value.get("digest")
        if not isinstance(digest, str) or not _is_sha256(digest):
            raise SourceDigestError("sourceDigest.digest must be a sha256 digest")
        inputs = value.get("inputs")
        if not isinstance(inputs, list) or tuple(inputs) != _INPUT_ROOTS:
            raise SourceDigestError("sourceDigest.inputs must name the fixed repository inputs")
        return cls(digest=digest)

    def to_document(self) -> dict[str, object]:
        return {
            "algorithm": "sha256",
            "digest": self.digest,
            "inputs": list(_INPUT_ROOTS),
        }


def current_source_digest(*, repo_root: Path = REPO_ROOT) -> SourceDigest:
    """Return the only source digest used by execution and release evidence."""
    return SourceDigest.build(repo_root=repo_root)


def source_digest_at_git_revision(
    revision: str,
    *,
    repo_root: Path = REPO_ROOT,
) -> SourceDigest:
    """按 Git 提交中的固定输入计算可审计的历史 source digest。

    仅供旧 canonical 对象的 provenance 补全使用；正常执行仍必须调用
    ``current_source_digest``，不能把历史 revision 当作当前输入。
    """
    normalized_revision = str(revision or "").strip()
    if not normalized_revision:
        raise SourceDigestError("source revision is required")
    try:
        archived = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "archive",
                "--format=tar",
                normalized_revision,
                *_INPUT_ROOTS,
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise SourceDigestError("git archive is unavailable") from exc
    if archived.returncode != 0:
        detail = archived.stderr.decode("utf-8", errors="replace").strip()
        raise SourceDigestError(
            f"source revision cannot be archived: {normalized_revision}: {detail}"
        )

    archived_files: dict[str, str] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(archived.stdout), mode="r:") as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                path = Path(member.name)
                if any(part in _EXCLUDED_PARTS for part in path.parts):
                    continue
                content = archive.extractfile(member)
                if content is None:
                    raise SourceDigestError(
                        f"source revision archive entry is unreadable: {member.name}"
                    )
                archived_files[path.as_posix()] = hashlib.sha256(content.read()).hexdigest()
    except (tarfile.TarError, OSError) as exc:
        raise SourceDigestError(
            f"source revision archive is invalid: {normalized_revision}"
        ) from exc
    if not archived_files:
        raise SourceDigestError(
            f"source revision archive contains no digest inputs: {normalized_revision}"
        )

    digest = hashlib.sha256()
    for relative_root in _INPUT_ROOTS:
        prefix = f"{relative_root.rstrip('/')}/"
        if relative_root in archived_files:
            entries = ((relative_root, archived_files[relative_root]),)
        else:
            entries = tuple(
                sorted(
                    (path, file_digest)
                    for path, file_digest in archived_files.items()
                    if path.startswith(prefix)
                )
            )
        for relative, file_digest in entries:
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(file_digest.encode("ascii"))
            digest.update(b"\n")
    return SourceDigest(digest=_DIGEST_PREFIX + digest.hexdigest())


def _iter_files(root: Path) -> tuple[Path, ...]:
    if root.is_file():
        return (root,)
    return tuple(
        path
        for path in sorted(root.rglob("*"))
        if path.is_file() and not any(part in _EXCLUDED_PARTS for part in path.parts)
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sha256(value: str) -> bool:
    if not value.startswith(_DIGEST_PREFIX):
        return False
    raw = value.removeprefix(_DIGEST_PREFIX)
    return len(raw) == hashlib.sha256().digest_size * 2 and all(
        character in "0123456789abcdef" for character in raw
    )


__all__ = [
    "SourceDigest",
    "SourceDigestError",
    "current_source_digest",
    "source_digest_at_git_revision",
]
