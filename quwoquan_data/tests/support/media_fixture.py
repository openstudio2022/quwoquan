"""Small, decodable media payloads for contract tests."""
from __future__ import annotations

import base64


_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/"
    "iZk9HQAAAABJRU5ErkJggg=="
)


def tiny_png_bytes() -> bytes:
    return _TINY_PNG
