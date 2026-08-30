"""Resolve an explicitly selected media-library CAS holding."""

from __future__ import annotations

from pathlib import Path

from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _digest_file,
)


def resolve_explicit_media_holding(
    root: Path,
    *,
    sha256: str,
    expected_bytes: int,
) -> Path:
    digest = str(sha256 or "").removeprefix("sha256:")
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ObjectTransactionError("DATA.POOL.LIBRARY_HOLDING_DIGEST_INVALID")
    entry = root / digest[:2] / digest[2:4] / digest
    if (
        entry.is_symlink()
        or not entry.is_file()
        or _digest_file(entry) != f"sha256:{digest}"
        or entry.stat().st_size != expected_bytes
    ):
        raise ObjectTransactionError("DATA.POOL.LIBRARY_HOLDING_DRIFT")
    return entry


__all__ = ["resolve_explicit_media_holding"]
