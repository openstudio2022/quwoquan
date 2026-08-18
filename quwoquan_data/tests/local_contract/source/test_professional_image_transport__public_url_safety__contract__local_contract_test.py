from __future__ import annotations

import pytest

from content.source import professional_image_transport as image_transport


def test_public_image_transport_rejects_credentials_and_non_public_hosts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for url in (
        "https://user:password@images.example.test/photo.jpg",
        "https://127.0.0.1/photo.jpg",
        "https://169.254.169.254/latest/meta-data",
        "https://192.0.2.1/photo.jpg",
        "https://224.0.0.1/photo.jpg",
        "https://[::1]/photo.jpg",
        "https://assets.local/photo.jpg",
    ):
        with pytest.raises(ValueError):
            image_transport._validated_https_url(url, allow_signed_query=False)
    with pytest.raises(ValueError, match="credential-like"):
        image_transport._validated_https_url(
            "https://images.example.test/photo.jpg?access_token=secret",
            allow_signed_query=False,
        )
    assert image_transport._validated_https_url(
        "https://images.example.test/photo.jpg?signature=api-issued",
        allow_signed_query=True,
    ).startswith("https://images.example.test/")

    monkeypatch.setattr(
        image_transport.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("10.0.0.8", 443))],
    )
    with pytest.raises(ValueError, match="non-public address"):
        image_transport._assert_public_resolution(
            "https://images.example.test/photo.jpg"
        )
    redirect_handler = image_transport._PublicImageRedirects(
        allow_signed_query=False
    )
    with pytest.raises(ValueError, match="non-public address"):
        redirect_handler.redirect_request(
            None,
            None,
            302,
            "Found",
            {},
            "https://redirect.example.test/private.jpg",
        )
