"""Media and fresh-guest contracts for public post API verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator
from tests.local_contract.release.test_post_api_verification__behavior__contract__local_contract_test import (
    VIDEO_ATTRIBUTION,
    DeploymentEnvironment,
    PublicApiResponse,
    public_api_subject,
    subject,
)

_SIGNED_IMAGE_BYTES = b"\xff\xd8\xff\xe0"
_SIGNED_ORIGINAL_URL = (
    "https://signed-media.secret.test/media/private/original.jpg"
    "?X-Amz-Signature=signature-secret"
    "&X-Amz-Credential=credential-secret"
    "&token=token-secret"
)
_SIGNED_SECRET_MARKERS = (
    "signed-media.secret.test",
    "/media/private/original.jpg",
    "X-Amz-Signature",
    "signature-secret",
    "X-Amz-Credential",
    "credential-secret",
    "token=",
    "token-secret",
)


def _signed_asset() -> subject.ReleaseMediaAssetCase:
    return subject.ReleaseMediaAssetCase(
        asset_id="research-image-a",
        kind="image",
        public_url="media/objects/sha256/aa/bb/research-image-a.jpg",
        delivery_ref="media/objects/sha256/aa/bb/research-image-a.jpg",
        expected_bytes=len(_SIGNED_IMAGE_BYTES),
        expected_sha256="sha256:"
        + hashlib.sha256(_SIGNED_IMAGE_BYTES).hexdigest(),
        expected_mime_type="image/jpeg",
    )


class _SignedMediaClient:
    def __init__(self, binary_response: SimpleNamespace) -> None:
        self.binary_response = binary_response
        self.requested_urls: list[str] = []

    def post_json(self, path: str, **_kwargs: object) -> PublicApiResponse:
        assert path == "content/media/research-image-a/original:access"
        return PublicApiResponse(
            status=200,
            payload={"originalUrl": _SIGNED_ORIGINAL_URL},
        )

    def get_bytes(self, url: str, **_kwargs: object) -> SimpleNamespace:
        self.requested_urls.append(url)
        return self.binary_response


def _assert_signed_secret_absent(value: object) -> None:
    serialized = json.dumps(value, ensure_ascii=False)
    for marker in _SIGNED_SECRET_MARKERS:
        assert marker not in serialized


def test_research_signed_media_success_report_keeps_request_url_process_local() -> None:
    client = _SignedMediaClient(
        SimpleNamespace(
            status=200,
            content_type="image/jpeg",
            content_range="",
            body=_SIGNED_IMAGE_BYTES,
            etag='"server-etag"',
        )
    )

    signed_probe = subject._research_signed_media_probe(client, _signed_asset())

    assert client.requested_urls == [_SIGNED_ORIGINAL_URL]
    assert signed_probe == {
        "targetEvidence": signed_probe["targetEvidence"],
        "status": 200,
        "mimeType": "image/jpeg",
        "bytes": len(_SIGNED_IMAGE_BYTES),
        "sha256": "sha256:" + hashlib.sha256(_SIGNED_IMAGE_BYTES).hexdigest(),
        "hashVerified": True,
    }
    assert signed_probe["targetEvidence"].startswith(
        "hostClass=dns,pathHash=sha256:"
    )
    schema_path = (
        Path(__file__).resolve().parents[4]
        / "quwoquan_data/schema/release/post_api_verification.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    signed_probe_schema = schema["$defs"]["signedImageProbe"]
    assert "publicUrl" not in signed_probe_schema["properties"]
    assert schema["$defs"]["researchMediaProbe"]["properties"]["signedProbe"][
        "oneOf"
    ][0]["$ref"] == "#/$defs/signedImageProbe"
    Draft202012Validator(signed_probe_schema).validate(signed_probe)
    _assert_signed_secret_absent({"signedProbe": signed_probe})


@pytest.mark.parametrize(
    ("binary_response", "expected_error"),
    [
        (
            SimpleNamespace(
                status=403,
                content_type="application/json",
                content_range="",
                body=b"denied",
            ),
            "status=403",
        ),
        (
            SimpleNamespace(
                status=200,
                content_type="text/plain",
                content_range="",
                body=_SIGNED_IMAGE_BYTES,
            ),
            "MIME mismatch",
        ),
        (
            SimpleNamespace(
                status=200,
                content_type="image/jpeg",
                content_range="",
                body=b"\xff\xd8\xff\xe1",
            ),
            "hash differs",
        ),
    ],
    ids=("http-status", "mime", "hash"),
)
def test_research_signed_media_failure_receipt_never_contains_signed_url(
    binary_response: SimpleNamespace,
    expected_error: str,
) -> None:
    client = _SignedMediaClient(binary_response)

    with pytest.raises(subject.PostApiVerificationError) as failure:
        subject._research_signed_media_probe(client, _signed_asset())

    assert client.requested_urls == [_SIGNED_ORIGINAL_URL]
    assert expected_error in str(failure.value)
    _assert_signed_secret_absent({"error": str(failure.value)})

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


def test_research_verification__rejects_commercial_release_class(
    tmp_path: Path,
) -> None:
    """research 相位只能核验 research release；类别错配必须 fail-closed。"""
    import json as _json

    release_root = tmp_path / "release"
    (release_root / "payload").mkdir(parents=True)
    (release_root / "payload/release.json").write_text(
        _json.dumps({"releaseId": "research-001", "releaseClass": "commercial"}),
        encoding="utf-8",
    )
    with pytest.raises(
        subject.PostApiVerificationError,
        match="readiness phase research cannot verify a commercial release",
    ):
        subject.write_post_api_verification(
            environment=DeploymentEnvironment.ALPHA,
            release_id="research-001",
            run_id="verify-001",
            release_root=release_root,
            importer_report_path=tmp_path / "import.json",
            creator_importer_report_path=tmp_path / "creator-import.json",
            output_path=tmp_path / "post-api-verification.json",
            api_base_url="https://api.alpha.example.test",
            media_delivery_base_url="https://media.alpha.example.test",
            readiness_phase="research",
        )
