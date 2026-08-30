"""Atomic CAS and create-once receipt storage for professional videos."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from core.io import write_json

from content.source.professional_video_receipt import (
    file_digest,
    load_professional_video_acquisition_receipt,
)


class ProfessionalVideoCasCollision(ValueError):
    """A content-addressed destination contains bytes for another digest."""


def put_video_cas(
    source: Path,
    suffix: str,
    *,
    output_root: Path,
) -> tuple[Path, str]:
    content_sha256 = file_digest(source)
    digest = content_sha256.removeprefix("sha256:")
    destination = output_root / "cas" / "sha256" / digest[:2] / f"{digest}{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file():
        if file_digest(destination) != content_sha256:
            raise ProfessionalVideoCasCollision(
                f"professional video CAS collision: {destination}"
            )
        return destination, content_sha256
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=destination.parent,
            prefix=f".{digest}.",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary = output.name
            with source.open("rb") as incoming:
                while chunk := incoming.read(1024 * 1024):
                    output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)
    return destination, content_sha256


def write_create_once_video_receipt(
    path: Path,
    receipt: dict[str, Any],
    *,
    output_root: Path,
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
        write_json(Path(temporary), receipt)
        try:
            os.link(temporary, path)
            return receipt
        except FileExistsError:
            existing = load_professional_video_acquisition_receipt(
                path.relative_to(output_root).as_posix(),
                root=output_root,
            )
            if existing != receipt:
                raise ValueError(
                    f"professional video acquisition receipt collision: {path}"
                )
            return existing
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


__all__ = [
    "ProfessionalVideoCasCollision",
    "put_video_cas",
    "write_create_once_video_receipt",
]
