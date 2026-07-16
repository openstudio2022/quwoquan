from __future__ import annotations

from content.source import fetch_images as fetch_mod
from content.source.handler_plan import SOURCE_UNIT_MAX_IMAGE_BYTES


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


def test_page_image_fetch_retries_rate_limit_then_returns_typed_payload(monkeypatch):
    body = b"\xff\xd8\xff\xe0" + b"0" * 4096
    responses = iter(
        [
            (429, b"too many requests", "text/plain"),
            (200, body, "image/jpeg"),
        ]
    )
    monkeypatch.setattr(fetch_mod, "_http_get_bytes", lambda *_args, **_kwargs: next(responses))
    monkeypatch.setattr(fetch_mod.time, "sleep", lambda _seconds: None)

    result = fetch_mod.fetch_page_image_payload(
        "https://upload.wikimedia.org/wikipedia/commons/example.jpg",
        max_attempts=2,
    )

    assert result.succeeded is True
    assert result.attempt_count == 2
    assert result.status_code == 200
    assert result.payload is not None
    assert result.payload.ext == ".jpg"


def test_page_image_fetch_uses_independent_page_media_timeout(monkeypatch):
    body = b"\xff\xd8\xff\xe0" + b"0" * 4096
    observed: dict[str, int] = {}

    def fake_http_get_bytes(_url: str, *, timeout: int, **_kwargs):
        observed["timeout"] = timeout
        return 200, body, "image/jpeg"

    monkeypatch.setattr(fetch_mod, "_http_get_bytes", fake_http_get_bytes)

    result = fetch_mod.fetch_page_image_payload(
        "https://upload.wikimedia.org/wikipedia/commons/example.jpg",
        max_attempts=1,
        timeout_seconds=45,
    )

    assert result.succeeded is True
    assert observed == {"timeout": 45}


def test_page_image_fetch_returns_typed_rate_limit_after_retry_budget(monkeypatch):
    monkeypatch.setattr(
        fetch_mod,
        "_http_get_bytes",
        lambda *_args, **_kwargs: (429, b"too many requests", "text/plain"),
    )
    monkeypatch.setattr(fetch_mod.time, "sleep", lambda _seconds: None)

    result = fetch_mod.fetch_page_image_payload(
        "https://upload.wikimedia.org/wikipedia/commons/example.jpg",
        max_attempts=2,
    )

    assert result.succeeded is False
    assert result.failure is fetch_mod.PageImageFetchFailure.RATE_LIMITED
    assert result.attempt_count == 2
