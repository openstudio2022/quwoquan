"""Derive the immutable repository-input digest for data executions and releases.

The digest is evidence, not a second source of truth. It names only fixed
repository input roots and hashes their files in a deterministic order, so deleting
``.qwq_output`` never removes configuration required to rebuild an execution.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path

from core.paths import DATA_CACHE_ROOT, REPO_ROOT

_SOURCE_DEFINITION_INPUT_ROOTS = (
    "quwoquan_data/schema",
    "quwoquan_data/control_plane",
    "quwoquan_data/prompts",
    "quwoquan_data/templates",
    "quwoquan_data/verticals/travel",
    "quwoquan_data/reference",
    "quwoquan_data/requirements.txt",
    "quwoquan_service/services/content-service/contracts/media/media_asset",
    "quwoquan_service/services/content-service/contracts/content/post/ui_config.yaml",
    "quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_feature_profile_view/projections/intersection_reason.yaml",
)
_EXECUTION_BUNDLE_INPUT_ROOTS = (
    "quwoquan_data/scripts",
    "quwoquan_data/requirements.txt",
    "quwoquan_ops/policies/branch_policy.yaml",
    "specs/feature-tree/discovery-content/object-homepage-coverage-scaling/spec.md",
    "specs/feature-tree/discovery-content/object-homepage-coverage-scaling/design.md",
    "specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md",
)
# Kept for terminal legacy evidence only. New candidates bind the two identities
# separately so executor refactors do not pretend that content semantics changed.
_INPUT_ROOTS = ("quwoquan_data/scripts", *_SOURCE_DEFINITION_INPUT_ROOTS)
# Data execution identity is deliberately environment-neutral. Environment
# topology and readiness policy apply only when an immutable release is shipped.
_DIGEST_PREFIX = "sha256:"
_EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".DS_Store", ".gitkeep"}
_CACHE_VERSION = 1


class SourceDigestError(ValueError):
    """The repository inputs cannot be represented by the fixed digest contract."""


@dataclass(frozen=True, slots=True)
class SourceDigest:
    """A compact, reproducible fingerprint of the data production inputs."""

    digest: str

    @classmethod
    def build(
        cls,
        *,
        repo_root: Path = REPO_ROOT,
        cache_path: Path | None = None,
    ) -> SourceDigest:
        normalized_root = repo_root.expanduser().resolve()
        selected_cache = (
            cache_path
            if cache_path is not None
            else _default_cache_path(normalized_root)
        )
        cache_guard = (
            _cache_lock(selected_cache)
            if selected_cache is not None
            else nullcontext()
        )
        with cache_guard:
            cache = (
                _load_cache(selected_cache)
                if selected_cache is not None
                else {"version": _CACHE_VERSION, "entries": {}}
            )
            previous_entries = cache.get("entries")
            if not isinstance(previous_entries, Mapping):
                previous_entries = {}
            next_entries: dict[str, dict[str, object]] = {}
            digest = hashlib.sha256()
            for relative_root in _INPUT_ROOTS:
                root = normalized_root / relative_root
                if not root.exists():
                    raise SourceDigestError(
                        f"source digest input is missing: {relative_root}"
                    )
                for path in _iter_files(root):
                    relative = path.relative_to(normalized_root).as_posix()
                    stat = path.stat()
                    identity = {
                        "size": int(stat.st_size),
                        "mtimeNs": int(stat.st_mtime_ns),
                        "ctimeNs": int(stat.st_ctime_ns),
                        "device": int(stat.st_dev),
                        "inode": int(stat.st_ino),
                    }
                    cached = previous_entries.get(relative)
                    file_digest = ""
                    if isinstance(cached, Mapping) and all(
                        cached.get(key) == value for key, value in identity.items()
                    ):
                        candidate = cached.get("sha256")
                        if isinstance(candidate, str) and _is_raw_sha256(candidate):
                            file_digest = candidate
                    if not file_digest:
                        file_digest = _file_sha256(path)
                    next_entries[relative] = {**identity, "sha256": file_digest}
                    digest.update(relative.encode("utf-8"))
                    digest.update(b"\0")
                    digest.update(file_digest.encode("ascii"))
                    digest.update(b"\n")
            if selected_cache is not None:
                _write_cache(
                    selected_cache,
                    {"version": _CACHE_VERSION, "entries": next_entries},
                )
        return cls(digest=_DIGEST_PREFIX + digest.hexdigest())

    @classmethod
    def from_document(cls, value: object) -> SourceDigest:
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


@dataclass(frozen=True, slots=True)
class ExecutionBundleIdentity:
    """Immutable identity of the code/policy bundle that executes a snapshot."""

    digest: str

    @classmethod
    def build(cls, *, repo_root: Path = REPO_ROOT) -> ExecutionBundleIdentity:
        return cls(
            digest=_digest_roots(
                repo_root.expanduser().resolve(),
                _EXECUTION_BUNDLE_INPUT_ROOTS,
            )
        )

    @classmethod
    def from_document(cls, value: object) -> ExecutionBundleIdentity:
        if not isinstance(value, Mapping):
            raise SourceDigestError("executionBundle must be an object")
        if set(value) != {"algorithm", "digest", "inputs"}:
            raise SourceDigestError("executionBundle fields are invalid")
        if value.get("algorithm") != "sha256":
            raise SourceDigestError("executionBundle.algorithm must be sha256")
        digest = value.get("digest")
        if not isinstance(digest, str) or not _is_sha256(digest):
            raise SourceDigestError("executionBundle.digest must be a sha256 digest")
        if tuple(value.get("inputs") or ()) != _EXECUTION_BUNDLE_INPUT_ROOTS:
            raise SourceDigestError(
                "executionBundle.inputs must name the fixed execution inputs"
            )
        return cls(digest=digest)

    def to_document(self) -> dict[str, object]:
        return {
            "algorithm": "sha256",
            "digest": self.digest,
            "inputs": list(_EXECUTION_BUNDLE_INPUT_ROOTS),
        }


@dataclass(frozen=True, slots=True)
class SourceDefinitionSnapshot:
    """Content-semantic and physical-source definitions frozen for a candidate."""

    digest: str

    @classmethod
    def build(cls, *, repo_root: Path = REPO_ROOT) -> SourceDefinitionSnapshot:
        return cls(
            digest=_digest_roots(
                repo_root.expanduser().resolve(),
                _SOURCE_DEFINITION_INPUT_ROOTS,
            )
        )

    @classmethod
    def from_document(cls, value: object) -> SourceDefinitionSnapshot:
        if not isinstance(value, Mapping):
            raise SourceDigestError("sourceDigest must be an object")
        if set(value) != {"algorithm", "digest", "inputs"}:
            raise SourceDigestError("sourceDigest fields are invalid")
        if value.get("algorithm") != "sha256":
            raise SourceDigestError("sourceDigest.algorithm must be sha256")
        digest = value.get("digest")
        if not isinstance(digest, str) or not _is_sha256(digest):
            raise SourceDigestError("sourceDigest.digest must be a sha256 digest")
        if tuple(value.get("inputs") or ()) != _SOURCE_DEFINITION_INPUT_ROOTS:
            raise SourceDigestError(
                "sourceDigest.inputs must name the fixed source-definition inputs"
            )
        return cls(digest=digest)

    def to_document(self) -> dict[str, object]:
        return {
            "algorithm": "sha256",
            "digest": self.digest,
            "inputs": list(_SOURCE_DEFINITION_INPUT_ROOTS),
        }


@dataclass(frozen=True, slots=True)
class FrozenSourceDigest:
    """A validated historical input closure bound to pre-snapshot object evidence."""

    digest: str
    inputs: tuple[str, ...]

    @classmethod
    def from_document(cls, value: object) -> FrozenSourceDigest:
        if not isinstance(value, Mapping):
            raise SourceDigestError("frozen sourceDigest must be an object")
        if set(value) != {"algorithm", "digest", "inputs"}:
            raise SourceDigestError("frozen sourceDigest fields are invalid")
        if value.get("algorithm") != "sha256":
            raise SourceDigestError("frozen sourceDigest.algorithm must be sha256")
        digest = value.get("digest")
        if not isinstance(digest, str) or not _is_sha256(digest):
            raise SourceDigestError(
                "frozen sourceDigest.digest must be a sha256 digest"
            )
        raw_inputs = value.get("inputs")
        if not isinstance(raw_inputs, list) or not raw_inputs:
            raise SourceDigestError("frozen sourceDigest.inputs must not be empty")
        inputs = tuple(str(item or "").strip() for item in raw_inputs)
        if (
            any(
                not item
                or item.startswith("/")
                or any(part in {".", ".."} for part in item.split("/"))
                for item in inputs
            )
            or len(inputs) != len(set(inputs))
        ):
            raise SourceDigestError("frozen sourceDigest.inputs are invalid")
        return cls(digest=digest, inputs=inputs)

    def to_document(self) -> dict[str, object]:
        return {
            "algorithm": "sha256",
            "digest": self.digest,
            "inputs": list(self.inputs),
        }


def parse_source_digest_document(value: object) -> SourceDigest:
    """Parse the current input truth for one source digest document."""
    return SourceDigest.from_document(value)


def parse_immutable_source_digest_document(
    value: object,
) -> SourceDigest | SourceDefinitionSnapshot:
    """Parse either immutable identity generation from frozen release evidence.

    Frozen evidence cannot be migrated, so both generations must stay readable:
    current producers bind the source-definition identity on its own, while
    terminal historical evidence still carries the retired combined closure.
    The generation is decided by the named inputs, never by a version field.
    """

    raw_inputs = value.get("inputs") if isinstance(value, Mapping) else None
    if (
        isinstance(raw_inputs, list)
        and tuple(raw_inputs) == _SOURCE_DEFINITION_INPUT_ROOTS
    ):
        return SourceDefinitionSnapshot.from_document(value)
    return SourceDigest.from_document(value)


def current_source_digest(*, repo_root: Path = REPO_ROOT) -> SourceDigest:
    """Return the only source digest used by execution and release evidence."""
    return SourceDigest.build(repo_root=repo_root)


def current_source_definition_snapshot(
    *, repo_root: Path = REPO_ROOT
) -> SourceDefinitionSnapshot:
    return SourceDefinitionSnapshot.build(repo_root=repo_root)


def current_execution_bundle_identity(
    *, repo_root: Path = REPO_ROOT
) -> ExecutionBundleIdentity:
    return ExecutionBundleIdentity.build(repo_root=repo_root)


def content_source_revision(
    *,
    source_digest: str,
    entity_catalog_digest: str,
) -> str:
    """Derive the one content revision shared by campaign and release evidence."""
    if not _is_sha256(source_digest):
        raise SourceDigestError("sourceDigest must be a sha256 digest")
    if not _is_sha256(entity_catalog_digest):
        raise SourceDigestError("entityCatalogDigest must be a sha256 digest")
    encoded = json.dumps(
        {
            "schema": "quwoquan_data.campaign_content_source_revision",
            "sourceDigest": source_digest,
            "entityCatalogDigest": entity_catalog_digest,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _DIGEST_PREFIX + hashlib.sha256(encoded).hexdigest()


def _iter_files(root: Path) -> tuple[Path, ...]:
    if root.is_file():
        return (root,)
    return tuple(
        path
        for path in sorted(root.rglob("*"))
        if path.is_file() and not any(part in _EXCLUDED_PARTS for part in path.parts)
    )


def _digest_roots(repo_root: Path, roots: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for relative_root in roots:
        root = repo_root / relative_root
        if not root.exists():
            raise SourceDigestError(
                f"source identity input is missing: {relative_root}"
            )
        for path in _iter_files(root):
            relative = path.relative_to(repo_root).as_posix()
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(_file_sha256(path).encode("ascii"))
            digest.update(b"\n")
    return _DIGEST_PREFIX + digest.hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _default_cache_path(repo_root: Path) -> Path | None:
    if repo_root == REPO_ROOT.resolve():
        return DATA_CACHE_ROOT / "source-digest" / "file-hashes-v1.json"
    # A source capsule/snapshot is deliberately not a Git worktree and may be
    # read-only.  Persistent caching is an optimization for normal repositories,
    # never part of the immutable source identity or capsule tree.
    if not (repo_root / ".git").exists():
        return None
    return (
        repo_root
        / ".qwq_output"
        / "data"
        / "local"
        / "cache"
        / "source-digest"
        / "file-hashes-v1.json"
    )


def _load_cache(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"version": _CACHE_VERSION, "entries": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"version": _CACHE_VERSION, "entries": {}}
    if not isinstance(value, dict) or value.get("version") != _CACHE_VERSION:
        return {"version": _CACHE_VERSION, "entries": {}}
    return value


def _write_cache(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _cache_lock(cache_path: Path) -> Iterator[None]:
    lock_path = cache_path.with_suffix(cache_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _is_raw_sha256(value: str) -> bool:
    return len(value) == hashlib.sha256().digest_size * 2 and all(
        character in "0123456789abcdef" for character in value
    )


def _is_sha256(value: str) -> bool:
    if not value.startswith(_DIGEST_PREFIX):
        return False
    raw = value.removeprefix(_DIGEST_PREFIX)
    return _is_raw_sha256(raw)


__all__ = [
    "ExecutionBundleIdentity",
    "FrozenSourceDigest",
    "SourceDigest",
    "SourceDefinitionSnapshot",
    "SourceDigestError",
    "content_source_revision",
    "current_execution_bundle_identity",
    "current_source_definition_snapshot",
    "current_source_digest",
    "parse_immutable_source_digest_document",
    "parse_source_digest_document",
]
