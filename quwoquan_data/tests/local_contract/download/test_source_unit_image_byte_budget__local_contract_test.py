from __future__ import annotations

from download import fetch as fetch_mod
from download.handler_plan import SOURCE_UNIT_MAX_IMAGE_BYTES


def test_source_unit_default_image_budget_keeps_wikimedia_sized_original(monkeypatch):
    body = b"\xff\xd8\xff\xe0" + (b"0" * (15 * 1024 * 1024))

    def fake_http_get_bytes(_url: str, *, max_bytes: int = 0, **_kwargs):
        return 200, body, "image/jpeg"

    monkeypatch.setattr(fetch_mod, "_http_get_bytes", fake_http_get_bytes)

    assert SOURCE_UNIT_MAX_IMAGE_BYTES >= len(body)
    accepted = fetch_mod.fetch_image_payload(
        "https://upload.wikimedia.org/wikipedia/commons/example.jpg",
        max_bytes=SOURCE_UNIT_MAX_IMAGE_BYTES,
    )
    rejected = fetch_mod.fetch_image_payload(
        "https://upload.wikimedia.org/wikipedia/commons/example.jpg",
        max_bytes=8 * 1024 * 1024,
    )

    assert accepted is not None
    assert accepted["ext"] == ".jpg"
    assert rejected is None
