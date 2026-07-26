"""Typed and warning-free image metadata probing for untrusted media bytes."""
from __future__ import annotations

import io
import warnings
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

try:  # pragma: no cover - dependency detection
    from PIL import Image, UnidentifiedImageError  # type: ignore

    _PIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]
    UnidentifiedImageError = OSError  # type: ignore[assignment,misc]
    _PIL_AVAILABLE = False


class ImageDecodeFailure(StrEnum):
    EMPTY = "empty"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    UNREADABLE = "unreadable"
    PIXEL_LIMIT_EXCEEDED = "pixel_limit_exceeded"


@dataclass(frozen=True, slots=True)
class ImageProbe:
    width: int = 0
    height: int = 0
    mime_type: str = ""
    failure: ImageDecodeFailure | None = None

    @property
    def succeeded(self) -> bool:
        return self.failure is None

    @property
    def pixels(self) -> int:
        return self.width * self.height


def pil_available() -> bool:
    return _PIL_AVAILABLE


def _probe(stream: io.BytesIO | Path) -> ImageProbe:
    if not _PIL_AVAILABLE:
        return ImageProbe(failure=ImageDecodeFailure.BACKEND_UNAVAILABLE)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(stream) as image:
                width, height = image.size
                mime_type = str(Image.MIME.get(image.format or "") or "")
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        return ImageProbe(failure=ImageDecodeFailure.PIXEL_LIMIT_EXCEEDED)
    except (UnidentifiedImageError, OSError, ValueError):
        return ImageProbe(failure=ImageDecodeFailure.UNREADABLE)
    if width < 1 or height < 1 or not mime_type.startswith("image/"):
        return ImageProbe(failure=ImageDecodeFailure.UNREADABLE)
    return ImageProbe(width=int(width), height=int(height), mime_type=mime_type)


def probe_image_bytes(data: bytes) -> ImageProbe:
    if not data:
        return ImageProbe(failure=ImageDecodeFailure.EMPTY)
    return _probe(io.BytesIO(data))


def probe_image_path(path: str | Path) -> ImageProbe:
    candidate = Path(path)
    if not candidate.is_file():
        return ImageProbe(failure=ImageDecodeFailure.UNREADABLE)
    return _probe(candidate)


__all__ = [
    "ImageDecodeFailure",
    "ImageProbe",
    "pil_available",
    "probe_image_bytes",
    "probe_image_path",
]
