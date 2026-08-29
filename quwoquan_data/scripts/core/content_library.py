"""Address content library entries.

The library replaces "每个阶段复制一份字节" with "一次入库、多处引用": an entry is
addressed by the sha256 of its content, is immutable once written, and every
stage keeps only a reference to it. `core.paths` owns where the library lives;
this module owns how an entry inside it is named and found.
"""

from __future__ import annotations

import errno
import hashlib
import os
import re
import shutil
from pathlib import Path

from core.paths import (
    LIBRARY_CAS_ROOT_BY_KIND,
    LIBRARY_ROOT,
    OUTPUT_ROOT,
    carried_media_root,
)

_DIGEST_RE = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$")
_SUFFIX_RE = re.compile(r"\.[A-Za-z0-9]+")
# Entries are immutable once admitted; a consumer that needs to change bytes must
# admit new content and re-point its reference.
# The kind every media body is addressed under, named once so a release, the
# collector and the retention policy cannot disagree about where bodies live.
MEDIA_KIND = "media"

_ENTRY_MODE = 0o444
_EXECUTABLE_ENTRY_MODE = 0o555


class MediaHoldingError(ValueError):
    """A recorded media reference cannot be honoured by the content library.

    Kept as the base so that a caller which only needs "not honoured" stays
    correct. Callers that act on the failure — a repair path, a closure report —
    must distinguish the subclasses below, because the three reasons do not share
    a recovery route.
    """


class ContentLibraryUnreachable(MediaHoldingError):
    """The library itself is not reachable, so no reference can be judged.

    This is a library-level fact and must not be reported once per reference:
    a detached volume or a moved data directory would otherwise surface as
    "every holding is absent", which reads as a content defect and sends the
    reader looking for bytes object by object.
    """


class MediaHoldingAbsent(MediaHoldingError):
    """The library is reachable but holds no entry for this digest."""


class MediaHoldingDrift(MediaHoldingError):
    """The library holds an entry for this digest whose size disagrees with the record."""


def library_root_for_output(output_root: Path) -> Path:
    """Resolve the content library that belongs to one output root.

    An explicit ``QWQ_LIBRARY_ROOT`` is a deliberate mount shared by every run
    and wins. A run on the canonical output root uses the canonical library,
    which lives outside the repository because its bytes cannot be rebuilt from
    version control. Any other output root is an isolated run: it gets its own
    library inside that root, so it can neither write into nor read entries from
    the canonical one.
    """

    if os.environ.get("QWQ_LIBRARY_ROOT"):
        return LIBRARY_ROOT
    resolved = Path(output_root).expanduser()
    if resolved.resolve() == OUTPUT_ROOT.expanduser().resolve():
        return LIBRARY_ROOT
    return resolved / "content_library"


def library_cas_root(kind: str, *, library_root: Path | None = None) -> Path:
    """Return the content-addressed store that owns one class of library bytes."""

    normalized = str(kind or "").strip()
    if normalized not in LIBRARY_CAS_ROOT_BY_KIND:
        raise ValueError(f"unsupported content library CAS kind: {kind}")
    if library_root is None:
        return LIBRARY_CAS_ROOT_BY_KIND[normalized]
    return Path(library_root) / LIBRARY_CAS_ROOT_BY_KIND[normalized].name


def library_cas_path(
    kind: str,
    sha256: str,
    *,
    library_root: Path | None = None,
    suffix: str = "",
) -> Path:
    """Resolve the immutable library location of one content-addressed entry."""

    match = _DIGEST_RE.fullmatch(str(sha256 or "").strip())
    if match is None:
        raise ValueError(f"content library entry requires a sha256 digest: {sha256}")
    digest = match.group(1)
    normalized_suffix = str(suffix or "")
    if normalized_suffix and not _SUFFIX_RE.fullmatch(normalized_suffix):
        raise ValueError(f"unsafe content library entry suffix: {suffix}")
    return (
        library_cas_root(kind, library_root=library_root)
        / digest[:2]
        / digest[2:4]
        / f"{digest}{normalized_suffix.lower()}"
    )


def normalize_library_digest(sha256: str) -> str:
    """Return the bare hex digest that addresses a library entry."""

    match = _DIGEST_RE.fullmatch(str(sha256 or "").strip())
    if match is None:
        raise ValueError(f"content library entry requires a sha256 digest: {sha256}")
    return match.group(1)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def admit_library_entry(
    source: Path,
    *,
    kind: str,
    sha256: str,
    library_root: Path | None = None,
    suffix: str = "",
    executable: bool = False,
) -> Path:
    """Admit one content-addressed entry into the library, at most once.

    Admission verifies the bytes against ``sha256`` before the entry becomes
    visible, so a caller holding a frozen digest cannot admit different content
    under it. A concurrent admission of the same content is a no-op rather than a
    conflict, because both writers produce identical bytes.
    """

    digest = normalize_library_digest(sha256)
    entry = library_cas_path(kind, digest, library_root=library_root, suffix=suffix)
    if entry.exists():
        return entry
    entry.parent.mkdir(parents=True, exist_ok=True)
    staged = entry.with_name(f".{entry.name}.{os.getpid()}.staged")
    try:
        shutil.copyfile(source, staged)
        observed = file_sha256(staged)
        if observed != digest:
            raise ValueError(
                f"content library admission drift: declared={digest} observed={observed}"
            )
        staged.chmod(_EXECUTABLE_ENTRY_MODE if executable else _ENTRY_MODE)
        try:
            os.link(staged, entry)
        except FileExistsError:
            pass
    finally:
        staged.unlink(missing_ok=True)
    return entry


def admit_library_bytes(
    body: bytes,
    *,
    kind: str,
    library_root: Path | None = None,
) -> Path:
    """Admit an in-memory body into the library and return the entry that owns it.

    For producers that hold bytes rather than a file — a derived image, a fetched
    response — and need the library to own them without also materializing a copy
    somewhere else. Admission is idempotent: identical bytes converge on one entry.
    """

    digest = hashlib.sha256(body).hexdigest()
    entry = library_cas_path(kind, digest, library_root=library_root)
    if entry.exists():
        return entry
    entry.parent.mkdir(parents=True, exist_ok=True)
    staged = entry.with_name(f".{entry.name}.{os.getpid()}.staged")
    try:
        staged.write_bytes(body)
        staged.chmod(_ENTRY_MODE)
        try:
            os.link(staged, entry)
        except FileExistsError:
            pass
    finally:
        staged.unlink(missing_ok=True)
    return entry


def carried_media_entry(sha256: str) -> Path | None:
    """The version-controlled body carried for one digest, whatever container it took.

    Absent means no body is carried for that digest, which is a legitimate state a
    caller decides about — not a failure of this lookup.
    """

    digest = normalize_library_digest(sha256)
    root = carried_media_root()
    if not root.is_dir():
        return None
    for candidate in sorted(root.glob(f"{digest}.*")):
        if candidate.is_file():
            return candidate
    return None


def carry_media_reference(source: Path, *, sha256: str, suffix: str = "") -> Path:
    """Carry one media body in version control beside the canonical tree.

    The library that holds media bodies lives outside the working tree and cannot
    be rebuilt from version control, so an approved object whose bytes exist only
    there is not deliverable on any other checkout. Carrying the body here is what
    makes the digest recorded in the object resolvable from the repository alone.

    Carrying verifies bytes against ``sha256`` the same way admission does, so a
    substituted body cannot be carried under a digest it does not hash to. An
    already-carried digest is a no-op: bodies are immutable once carried.
    """

    digest = normalize_library_digest(sha256)
    carried = carried_media_entry(digest)
    if carried is not None:
        return carried
    extension = (suffix or Path(source).suffix or "").lstrip(".").lower() or "bin"
    entry = carried_media_root() / f"{digest}.{extension}"
    entry.parent.mkdir(parents=True, exist_ok=True)
    staged = entry.with_name(f".{entry.name}.{os.getpid()}.staged")
    try:
        shutil.copyfile(source, staged)
        observed = file_sha256(staged)
        if observed != digest:
            raise MediaHoldingError(
                f"carried media drift: declared={digest} observed={observed}"
            )
        staged.replace(entry)
    finally:
        staged.unlink(missing_ok=True)
    return entry


def library_reachable(*, library_root: Path | None = None) -> bool:
    """Whether the library itself can be consulted at all.

    Judged on the library root rather than on a CAS subtree: a reachable library
    that has never admitted this class of bytes has no CAS subtree yet, and every
    reference in it is legitimately absent. An unreachable root is the other
    thing entirely — no reference can be judged, so no reference is absent.
    """

    root = LIBRARY_ROOT if library_root is None else Path(library_root).expanduser()
    return root.is_dir() and os.access(root, os.R_OK)


def resolve_media_holding(
    sha256: str,
    *,
    expected_bytes: int | None = None,
    library_root: Path | None = None,
) -> Path:
    """Resolve one media reference record to the library entry that owns its bytes.

    A canonical object records a media body by digest instead of carrying it, so
    every consumer that needs the bytes resolves them here. Each of the three ways
    this can fail raises its own type: returning an empty or missing path would
    turn a failure into a silent hole downstream, and collapsing the three into
    one would hide that a detached library needs reattaching rather than a hunt
    for individual bytes.
    """

    entry = library_cas_path(MEDIA_KIND, sha256, library_root=library_root)
    if not entry.is_file():
        if not library_reachable(library_root=library_root):
            raise ContentLibraryUnreachable(
                "content library is not reachable: "
                f"{LIBRARY_ROOT if library_root is None else library_root}"
            )
        raise MediaHoldingAbsent(
            f"media holding is not reachable in the content library: {sha256}"
        )
    if expected_bytes is not None and entry.stat().st_size != expected_bytes:
        raise MediaHoldingDrift(
            f"media holding size drifted from its library entry: {sha256}"
        )
    return entry


def reference_library_entry(entry: Path, destination: Path) -> None:
    """Expose one library entry at ``destination`` without copying its bytes.

    The reference is a hard link, so the destination is an ordinary file to every
    reader and to tree integrity: path, content digest and size are unchanged
    from a physical copy, while the bytes stay singly owned by the library.

    Re-materializing an existing destination replaces the reference rather than
    failing, because callers stage the same surface more than once per run.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        destination.unlink()
    try:
        os.link(entry, destination)
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise
        raise ValueError(
            "content library and reference must share one filesystem: "
            f"entry={entry} destination={destination}"
        ) from error


def link_from_library(
    source: Path,
    destination: Path,
    *,
    kind: str,
    library_root: Path | None = None,
    expected_sha256: str | None = None,
    suffix: str = "",
    executable: bool = False,
) -> str:
    """Admit ``source`` into the library once, then reference it at ``destination``.

    Returns the sha256 that addresses the entry. ``expected_sha256`` is for
    callers that already froze a digest: admission is refused when the source
    does not match it, instead of silently admitting the current bytes.
    """

    source = Path(source)
    digest = (
        normalize_library_digest(expected_sha256)
        if expected_sha256
        else file_sha256(source)
    )
    entry = admit_library_entry(
        source,
        kind=kind,
        sha256=digest,
        library_root=library_root,
        suffix=suffix,
        executable=executable,
    )
    reference_library_entry(entry, destination)
    return digest


def link_bytes_from_library(
    body: bytes,
    destination: Path,
    *,
    kind: str,
    library_root: Path | None = None,
) -> str:
    """Admit freshly acquired bytes into the library, then reference them.

    For acquisition paths that hold a response body rather than a file: two units
    that download identical bytes converge on one entry instead of two copies.
    """

    entry = admit_library_bytes(body, kind=kind, library_root=library_root)
    reference_library_entry(entry, destination)
    return hashlib.sha256(body).hexdigest()


def link_tree_from_library(
    source_root: Path,
    destination_root: Path,
    *,
    kind: str,
    library_root: Path | None = None,
) -> int:
    """Reference a whole subtree through the library instead of copying it.

    Stands in for ``shutil.copytree``: the destination keeps the same relative
    paths, contents and sizes, so tree integrity is unchanged, but each file body
    is owned once by the library. Returns the number of referenced files.
    """

    source_root = Path(source_root)
    destination_root = Path(destination_root)
    referenced = 0
    for path in sorted(source_root.rglob("*")):
        relative = path.relative_to(source_root)
        if path.is_dir():
            (destination_root / relative).mkdir(parents=True, exist_ok=True)
            continue
        if not path.is_file():
            continue
        destination = destination_root / relative
        link_from_library(path, destination, kind=kind, library_root=library_root)
        referenced += 1
    return referenced


__all__ = [
    "MEDIA_KIND",
    "ContentLibraryUnreachable",
    "MediaHoldingAbsent",
    "MediaHoldingDrift",
    "MediaHoldingError",
    "library_reachable",
    "admit_library_bytes",
    "admit_library_entry",
    "carried_media_entry",
    "carry_media_reference",
    "link_tree_from_library",
    "normalize_library_digest",
    "file_sha256",
    "library_cas_path",
    "library_cas_root",
    "library_root_for_output",
    "link_from_library",
    "reference_library_entry",
    "resolve_media_holding",
]
