"""Strict read surface for canonical EnvironmentAcceptanceFact v2.

Only ``quwoquan_ops.ci.environment_scheduler`` produces acceptance facts.  This
module loads exact canonical bytes and delegates all semantic checks to the v2
validator.  The retired profile-based builders, writers, predecessor adapter,
and promotion-order model are intentionally absent.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from quwoquan_ops.cli.lib.environment_acceptance_fact_contract import (
    ACCEPTANCE_PROFILES,
    ENVIRONMENTS,
    PREDECESSOR,
    SCHEMA,
    SCHEMA_PATH,
)
from quwoquan_ops.cli.lib.environment_acceptance_fact_validator import (
    validate_environment_acceptance_fact as _validate_v2,
)

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_INVALID = "OPS.ENVIRONMENT_ACCEPTANCE_FACT.invalid"
_EVIDENCE = "OPS.ENVIRONMENT_ACCEPTANCE_FACT.evidence_blocked"
_PATH_BLOCKED = "OPS.ENVIRONMENT_ACCEPTANCE_FACT.path_blocked"


class EnvironmentAcceptanceFactError(ValueError):
    """Stable typed failure from the canonical v2 read surface."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _block(code: str, detail: str) -> None:
    raise EnvironmentAcceptanceFactError(code, detail)


def canonical_fact_bytes(value: Mapping[str, Any]) -> bytes:
    """Return the one canonical JSON representation, without a trailing LF."""

    try:
        return json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EnvironmentAcceptanceFactError(
            _INVALID, "fact is not canonical JSON"
        ) from exc


def exact_byte_digest(value: bytes | Path) -> str:
    raw = value if isinstance(value, bytes) else Path(value).read_bytes()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _text(value: object, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character in value for character in ("\x00", "\n", "\r"))
    ):
        _block(_INVALID, f"{field} must be non-empty canonical text")
    return value


def _digest(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    if _DIGEST_RE.fullmatch(text) is None:
        _block(_INVALID, f"{field} must be sha256:<64 lowercase hex>")
    return text


def _identity(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    if _IDENTITY_RE.fullmatch(text) is None:
        _block(_INVALID, f"{field} has invalid identity format")
    return text


def _relative_ref(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    ref = PurePosixPath(text)
    if (
        ref.is_absolute()
        or ref.as_posix() != text
        or any(part in {"", ".", ".."} for part in ref.parts)
        or "\\" in text
        or text.endswith("/latest")
        or "/latest/" in text
        or ref.name.startswith("latest.")
    ):
        _block(_PATH_BLOCKED, f"{field} must be an immutable contained relative ref")
    return text


def _absolute_real_root(root: Path) -> Path:
    expanded = Path(root).expanduser()
    absolute = expanded if expanded.is_absolute() else Path.cwd() / expanded
    absolute = Path(os.path.abspath(absolute))
    try:
        metadata = absolute.lstat()
        resolved = absolute.resolve(strict=True)
    except OSError as exc:
        raise EnvironmentAcceptanceFactError(
            _PATH_BLOCKED, "store root is unavailable"
        ) from exc
    if absolute.is_symlink() or resolved != absolute or not stat.S_ISDIR(metadata.st_mode):
        _block(_PATH_BLOCKED, "store root must be a real non-symlink directory")
    return absolute


def _directory_flags() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        _block(_PATH_BLOCKED, "platform lacks no-follow directory support")
    return os.O_RDONLY | nofollow | directory | getattr(os, "O_CLOEXEC", 0)


def _file_flags() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        _block(_PATH_BLOCKED, "platform lacks no-follow file support")
    return os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0)


def _secure_read(root: Path, ref: str) -> bytes:
    real_root = _absolute_real_root(root)
    relative = PurePosixPath(_relative_ref(ref, field="acceptanceRef"))
    directory = os.open(real_root, _directory_flags())
    descriptor = -1
    try:
        for part in relative.parts[:-1]:
            try:
                child = os.open(part, _directory_flags(), dir_fd=directory)
            except OSError as exc:
                raise EnvironmentAcceptanceFactError(
                    _PATH_BLOCKED, "acceptance ref parent is missing, linked, or unsafe"
                ) from exc
            os.close(directory)
            directory = child
        try:
            before = os.stat(relative.name, dir_fd=directory, follow_symlinks=False)
            descriptor = os.open(relative.name, _file_flags(), dir_fd=directory)
        except OSError as exc:
            raise EnvironmentAcceptanceFactError(
                _PATH_BLOCKED, "acceptance ref is missing, linked, or unreadable"
            ) from exc
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or not stat.S_ISREG(opened.st_mode)
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            _block(_PATH_BLOCKED, "acceptance ref must be a stable regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        ):
            _block(_PATH_BLOCKED, "acceptance ref changed while being read")
        raw = b"".join(chunks)
        if len(raw) != opened.st_size:
            _block(_PATH_BLOCKED, "acceptance ref changed while being read")
        return raw
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(directory)


def _decode_canonical_fact(raw: bytes) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                _block(_INVALID, f"acceptance fact contains duplicate JSON key {key!r}")
            value[key] = item
        return value

    try:
        text = raw.decode("utf-8")
        decoder = json.JSONDecoder(
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: _block(
                _INVALID, f"acceptance fact contains invalid JSON constant {value}"
            ),
        )
        fact, end = decoder.raw_decode(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EnvironmentAcceptanceFactError(
            _INVALID, "acceptance fact is not UTF-8 JSON"
        ) from exc
    if text[end:].strip() or not isinstance(fact, dict):
        _block(_INVALID, "acceptance fact must contain exactly one JSON object")
    if raw != canonical_fact_bytes(fact) + b"\n":
        _block(_INVALID, "acceptance fact bytes are not canonical JSON")
    return fact


def validate_environment_acceptance_fact(
    payload: Mapping[str, Any],
    *,
    store_root: Path | None = None,
    verify_references: bool = True,
    accepted_at: datetime | None = None,
    signature_verifier: Callable[[str, bytes, str], bool] | None = None,
) -> dict[str, Any]:
    """Validate exactly the v2 schema; retired dependency kwargs are rejected."""

    return _validate_v2(
        payload,
        store_root=store_root,
        verify_references=verify_references,
        accepted_at=accepted_at,
        error_type=EnvironmentAcceptanceFactError,
        invalid_code=_INVALID,
        evidence_code=_EVIDENCE,
        signature_verifier=signature_verifier,
    )


def load_environment_acceptance_fact(
    ref: str,
    *,
    store_root: Path,
    verify_references: bool = True,
    accepted_at: datetime | None = None,
    signature_verifier: Callable[[str, bytes, str], bool] | None = None,
) -> tuple[dict[str, Any], str]:
    """Load canonical bytes from one explicit immutable ref and validate v2."""

    raw = _secure_read(store_root, ref)
    fact = _decode_canonical_fact(raw)
    validated = validate_environment_acceptance_fact(
        fact,
        store_root=store_root,
        verify_references=verify_references,
        accepted_at=accepted_at,
        signature_verifier=signature_verifier,
    )
    return validated, exact_byte_digest(raw)


__all__ = [
    "ACCEPTANCE_PROFILES",
    "ENVIRONMENTS",
    "PREDECESSOR",
    "SCHEMA",
    "SCHEMA_PATH",
    "EnvironmentAcceptanceFactError",
    "canonical_fact_bytes",
    "exact_byte_digest",
    "load_environment_acceptance_fact",
    "validate_environment_acceptance_fact",
]
