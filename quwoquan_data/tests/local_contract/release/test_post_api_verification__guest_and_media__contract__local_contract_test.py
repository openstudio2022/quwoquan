"""Media and fresh-guest contracts for public post API verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.local_contract.release.test_post_api_verification__behavior__contract__local_contract_test import (
    VIDEO_ATTRIBUTION,
    DeploymentEnvironment,
    PublicApiResponse,
    public_api_subject,
    subject,
)

def test_video_media_probe_requires_range_and_playable_header() -> None:
    client = SimpleNamespace(
        get_bytes=lambda _url, **_kwargs: SimpleNamespace(
            status=200,
            content_type="video/mp4",
            content_range="",
            body=b"not-a-video",
        )
    )

    with pytest.raises(subject.PostApiVerificationError, match="byte ranges"):
        subject._verify_binary_media(
            client,
            "https://media.test/video.mp4",
            expected_kind="video",
        )


def test_video_source_attribution_drift_blocks_consumer_verification() -> None:
    case = subject.PostApiCase(
        post_ref="video/test/1",
        post_id="post-video",
        content_type=subject.ContentType.VIDEO,
        author_id="author-video",
        source_attribution=VIDEO_ATTRIBUTION,
    )

    with pytest.raises(subject.PostApiVerificationError, match="sourceAttribution drift"):
        subject._verify_source_attribution(
            {"sourceAttribution": {**VIDEO_ATTRIBUTION, "rightsBasis": "unknown"}},
            case,
        )


@pytest.mark.parametrize("payload", [{}, {"sourceAttribution": None}])
def test_absent_source_attribution_requires_absent_or_null_live_projection(
    payload: dict[str, object],
) -> None:
    case = subject.PostApiCase(
        post_ref="article/test/1",
        post_id="post-article",
        content_type=subject.ContentType.ARTICLE,
        author_id="author-article",
        source_attribution=None,
    )

    assert subject._verify_source_attribution(payload, case) is True


def test_absent_source_attribution_rejects_partial_live_projection() -> None:
    case = subject.PostApiCase(
        post_ref="article/test/1",
        post_id="post-article",
        content_type=subject.ContentType.ARTICLE,
        author_id="author-article",
        source_attribution=None,
    )

    with pytest.raises(subject.PostApiVerificationError, match="expected absent/null"):
        subject._verify_source_attribution(
            {
                "sourceAttribution": {
                    "isOriginal": False,
                    "collectedAt": "0001-01-01T00:00:00Z",
                }
            },
            case,
        )


def test_public_api_client__fresh_guest_uses_canonical_contract_and_bearer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = []

    class _Response:
        def __init__(self, payload: dict) -> None:
            self.status = 200
            self._payload = json.dumps(payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return self._payload

    class _Opener:
        def open(self, request, *, timeout: float):
            assert timeout > 0
            requests.append(request)
            if request.full_url.endswith("/auth/login/anonymous"):
                return _Response(
                    {
                        "accessToken": "secret-bearer",
                        "ownerId": "uo_01_ad_30a1_00000000000000000000000000",
                        "activePersona": {"personaId": "us_01_30a1_00000000000000000000000000"},
                        "accountState": "anonymous",
                        "identityOrigin": "anonymous_device",
                    }
                )
            return _Response({"items": []})

    monkeypatch.setattr(
        public_api_subject,
        "build_opener",
        lambda *_handlers: _Opener(),
    )
    client = public_api_subject.PublicApiClient(
        base_url="https://api.example.test",
        session_id="readiness-run-a",
        platform="android",
        app_version="1.0.0-readiness",
    )

    guest = client.login_fresh_guest()
    response = client.for_guest(guest).get_json(
        "content/feed",
        page_id="content.feed.list",
        query={"identity": "work", "limit": "20"},
    )

    login_request, feed_request = requests
    login_body = json.loads(login_request.data.decode("utf-8"))
    assert set(login_body) == {
        "installId",
        "deviceFingerprintHash",
        "platform",
        "appVersion",
    }
    assert login_body["deviceFingerprintHash"] == hashlib.sha256(
        f"qwq-anonymous-device-v1:{login_body['installId']}".encode("utf-8")
    ).hexdigest()
    login_headers = {key.lower(): value for key, value in login_request.header_items()}
    feed_headers = {key.lower(): value for key, value in feed_request.header_items()}
    assert login_headers["x-client-page-id"] == "user.login.anonymous"
    assert "authorization" not in login_headers
    assert feed_headers["x-client-page-id"] == "content.feed.list"
    assert feed_headers["authorization"] == "Bearer secret-bearer"
    assert response.operation is not None
    assert response.operation.request_id == feed_headers["x-request-id"]
    assert response.operation.trace_id == feed_headers["x-trace-id"]
    assert guest.guest_actor_hash == "sha256:" + hashlib.sha256(
        (
            "qwq-readiness-guest-v1:"
            "uo_01_ad_30a1_00000000000000000000000000:"
            "us_01_30a1_00000000000000000000000000"
        ).encode("utf-8")
    ).hexdigest()


def test_public_api_client__fresh_guest_rejects_missing_active_persona(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        public_api_subject.PublicApiClient,
        "_request_json",
        lambda *_args, **_kwargs: public_api_subject.PublicApiResponse(
            status=200,
            payload={
                "accessToken": "secret-bearer",
                "ownerId": "uo_01_ad_30a1_00000000000000000000000000",
                "accountState": "anonymous",
                "identityOrigin": "anonymous_device",
            },
        ),
    )

    with pytest.raises(
        public_api_subject.PublicApiClientError,
        match="canonical anonymous session",
    ):
        public_api_subject.PublicApiClient(
            base_url="https://api.example.test"
        ).login_fresh_guest()


def test_public_api_client__fresh_guest_rejects_empty_persona_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        public_api_subject.PublicApiClient,
        "_request_json",
        lambda *_args, **_kwargs: public_api_subject.PublicApiResponse(
            status=200,
            payload={
                "accessToken": "secret-bearer",
                "ownerId": "uo_01_ad_30a1_00000000000000000000000000",
                "activePersona": {"personaId": "   "},
                "accountState": "anonymous",
                "identityOrigin": "anonymous_device",
            },
        ),
    )

    with pytest.raises(
        public_api_subject.PublicApiClientError,
        match="canonical anonymous session",
    ):
        public_api_subject.PublicApiClient(
            base_url="https://api.example.test"
        ).login_fresh_guest()


def test_research_verification__fails_with_typed_identity_adapter_blocker(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        subject.PostApiVerificationError,
        match="DATA.RESEARCH.IDENTITY_ADAPTER_UNAVAILABLE",
    ):
        subject.write_post_api_verification(
            environment=DeploymentEnvironment.ALPHA,
            release_id="research-001",
            run_id="verify-001",
            release_root=tmp_path / "release",
            importer_report_path=tmp_path / "import.json",
            creator_importer_report_path=tmp_path / "creator-import.json",
            output_path=tmp_path / "post-api-verification.json",
            api_base_url="https://api.alpha.example.test",
            media_delivery_base_url="https://media.alpha.example.test",
            readiness_phase="research",
        )
