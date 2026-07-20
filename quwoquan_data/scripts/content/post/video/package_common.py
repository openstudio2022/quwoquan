"""Shared deterministic helpers for video package writers."""
from __future__ import annotations

import hashlib
from pathlib import Path


def cas_object_key(sha256_value: str, extension: str) -> str:
    digest = str(sha256_value).removeprefix("sha256:")
    return f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}.{extension}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _vtt_timestamp(total_seconds: float) -> str:
    milliseconds = max(0, round(total_seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def subtitles(lines: tuple[str, ...], duration_seconds: float) -> str:
    rows = ["WEBVTT", ""]
    segment_seconds = duration_seconds / max(1, len(lines))
    for index, line in enumerate(lines):
        start = index * segment_seconds
        end = (index + 1) * segment_seconds
        rows.extend(
            (
                str(index + 1),
                f"{_vtt_timestamp(start)} --> {_vtt_timestamp(end)}",
                line.strip(),
                "",
            )
        )
    return "\n".join(rows)


__all__ = ["cas_object_key", "sha256_file", "subtitles"]
