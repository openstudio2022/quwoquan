from __future__ import annotations

import pytest

from content.source.research.scale_source_pool_video_materialize import (
    _derive_audio_rights,
)


@pytest.mark.parametrize(
    ("has_audio", "authorization_status", "proof_url", "expected"),
    [
        (
            True,
            "verified",
            "https://provider.example/authorization/video-1",
            ("licensed", "https://provider.example/authorization/video-1"),
        ),
        (False, "verified", "https://provider.example/authorization/video-1", ("no_audio", None)),
        (True, "verified", "http://provider.example/proof", ("unverified", None)),
        (True, "unverified", "https://provider.example/proof", ("unverified", None)),
    ],
)
def test_missing_source_attribution_derives_audio_rights_from_frozen_video_spec(
    has_audio: bool,
    authorization_status: str,
    proof_url: str,
    expected: tuple[str, str | None],
) -> None:
    spec = {
        "commercialAuthorizationStatus": authorization_status,
        "authorizationProofUrl": proof_url,
        "termsUrl": "https://provider.example/terms",
        "mediaProbe": {"hasAudio": has_audio},
    }

    assert (
        _derive_audio_rights(
            source_attribution=None,
            plan_video_spec=spec,
        )
        == expected
    )
