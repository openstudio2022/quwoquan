"""公开 release 读回保持精确身份、媒体字节与匿名交付，不保留研究专轨。

spec_ref: specs/feature-tree/runtime/runtime-media/spec.md#sit-001
spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/feed-fallback-degrade/spec.md#gwt-001
"""
from __future__ import annotations

import hashlib
import io
import json
from argparse import Namespace

import pytest

from quwoquan_ops.cli.probes import environment_probe_transport as transport
from quwoquan_ops.cli.probes import run_environment_integration_probe as probe

AVATAR = "media/avatar/s/asset/avatar-a/v1/source.jpg"
IMAGE = "media/image/s/asset/image-a/v1/source.webp"
VIDEO = "media/video/s/asset/video-a/v1/source.mp4"
MEDIA_ORIGIN = "https://cdn.gamma.quwoquan.com"


def _args() -> Namespace:
    return Namespace(
        env="gamma", base_url="https://api.gamma.quwoquan.com",
        product_ops_base_url="", media_image_base_url="", release_readiness="",
        test_auth_token="", require_non_empty_content_feed=True,
        expected_discovery_post_id=[], expected_homepage_recommend_post_id=[],
        expected_video_post_id=[], expected_premium_video_post_id=[],
        release_search_canary=[], release_sample=[], release_creator_profile=[],
        only_check=[], retry_attempts=2, retry_sleep_seconds=0.0,
        request_timeout_seconds=3,
    )


def _creator() -> dict[str, str]:
    return {
        "creatorRef": "creator-a", "authorId": "author-a", "personaId": "persona-a",
        "displayName": "灯塔观察员", "avatarAssetId": "avatar-a", "avatarDeliveryRef": AVATAR,
    }


def _asset(key: str, body: bytes, mime: str) -> dict:
    return {
        "assetId": key.split("/")[4], "version": 1,
        "kind": "video" if mime.startswith("video/") else "image",
        "publicSliceKey": key, "bytes": len(body), "contentType": mime,
        "sha256": "sha256:" + hashlib.sha256(body).hexdigest(),
    }


class _Response:
    def __init__(self, body: bytes, status: int, headers: dict) -> None:
        self.stream = io.BytesIO(body)
        self.status, self.headers = status, headers

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self, size=-1):
        return self.stream.read(size)


def _urlopen(assets: dict[str, tuple[dict, bytes]], seen: list, *, drift: str = ""):
    def open_url(request, timeout):
        assert not request.has_header("Authorization")
        assert timeout == 3
        seen.append(request)
        key = request.full_url.removeprefix(MEDIA_ORIGIN + "/").split("?", 1)[0]
        asset, body = assets[key]
        if request.get_method() == "HEAD":
            return _Response(b"", 200, {"Cache-Control": "no-store"})
        headers = {
            "Content-Type": asset["contentType"], "Content-Length": str(len(body)),
            "ETag": '"immutable-a"', "Cache-Control": "public, max-age=31536000, immutable",
            "Access-Control-Allow-Origin": "*", "X-QWQ-Media-Cache-Key": "/" + key,
        }
        status = 200
        if request.has_header("Range"):
            status = 206
            headers["Content-Range"] = f"bytes 0-{len(body)-1}/{len(body)}"
        if drift == "hash":
            body = b"x" * len(body)
        if drift == "mime":
            headers["Content-Type"] = "text/html"
        if drift == "empty":
            body = b""
        if drift == "range":
            status = 200
            headers.pop("Content-Range", None)
        if drift == "length":
            body += b"extra"
        return _Response(body, status, headers)
    return open_url


def test_public_readback__recommendation_creator_and_media_bytes__local_contract(monkeypatch):
    args = _args()
    args.test_auth_token = "ordinary-login-token"
    args.media_image_base_url = MEDIA_ORIGIN + "/media/image"
    args.expected_homepage_recommend_post_id = ["post-image-a"]
    args.release_creator_profile = [json.dumps(_creator())]
    args.only_check = ["homepage_recommend", probe.CREATOR_PROFILE_CHECK_NAME,
                       "media_sample", probe.FEED_MEDIA_SLICES_CHECK_NAME]
    assets = {key: (_asset(key, body, mime), body) for key, body, mime in (
        (AVATAR, b"avatar", "image/jpeg"), (IMAGE, b"image", "image/webp"),
        (VIDEO, b"\x00\x00\x00\x18ftypmp42-video", "video/mp4"),
    )}
    monkeypatch.setattr(probe, "_release_probe_identity", lambda _: {
        "media": assets[IMAGE][0], "mediaAssets": [row[0] for row in assets.values()],
    })
    seen = []
    monkeypatch.setattr(transport.urllib.request, "urlopen", _urlopen(assets, seen))

    def fake_request(_method, url, **kwargs):
        if "channelId=recommend" in url:
            assert "Authorization" not in kwargs["headers"]
            return True, 200, json.dumps({"items": [{"postId": "post-image-a",
                "mediaUrls": [IMAGE, VIDEO], "videoUrl": VIDEO}], "objectCards": []})
        if url.endswith("/user/persona-a"):
            return True, 200, json.dumps({"personaId": "persona-a", "displayName": "灯塔观察员",
                                          "avatarUrl": MEDIA_ORIGIN + "/" + AVATAR})
        raise AssertionError(url)

    monkeypatch.setattr(probe, "request", fake_request)
    report = probe.run_checks(args)
    assert report["status"] == "passed", report["findings"]
    checks = {row["name"]: row for row in report["checks"]}
    assert checks["homepage_recommend"]["returnedPostIds"] == ["post-image-a"]
    assert checks[probe.CREATOR_PROFILE_CHECK_NAME]["returnedPersonaId"] == "persona-a"
    assert checks["media_sample"]["mediaReadback"]["hashVerified"]
    slices = checks[probe.FEED_MEDIA_SLICES_CHECK_NAME]
    assert slices["sliceCount"] == 3
    assert all(row["hashVerified"] for row in slices["sliceReadbacks"])
    assert any(row.get("rangeStatus") == 206 for row in slices["sliceReadbacks"])
    assert any(request.has_header("Range") for request in seen)
    assert "ordinary-login-token" not in json.dumps(report)
    assert not any("research" in field.lower() for field in report)


@pytest.mark.parametrize("drift,fragment", [("post", "expected immutable release"),
    ("avatar", "exact release avatar asset"), ("persona", "exact release creator"),
    ("name", "exact release creator")])
def test_public_readback__creator_or_recommendation_drift_blocks__local_contract(monkeypatch, drift, fragment):
    args = _args()
    args.expected_homepage_recommend_post_id = ["post-a"]
    args.release_creator_profile = [json.dumps(_creator())]
    args.only_check = ["homepage_recommend", probe.CREATOR_PROFILE_CHECK_NAME]
    def fake_request(_method, url, **_kwargs):
        if "channelId=recommend" in url:
            return True, 200, json.dumps({"items": [{"postId": "other" if drift == "post" else "post-a"}], "objectCards": []})
        return True, 200, json.dumps({"personaId": "other" if drift == "persona" else "persona-a",
            "displayName": "other" if drift == "name" else "灯塔观察员",
            "avatarUrl": "media/avatar/s/asset/other/v1/source.jpg" if drift == "avatar" else AVATAR})
    monkeypatch.setattr(probe, "request", fake_request)
    report = probe.run_checks(args)
    assert report["status"] == "failed"
    assert any(fragment in finding for finding in report["findings"])


@pytest.mark.parametrize("token", ["", "ordinary-login-token"])
def test_public_feeds__all_use_anonymous_exact_release_ids__local_contract(monkeypatch, token):
    args = _args()
    args.test_auth_token = token
    args.expected_discovery_post_id = ["post-discovery"]
    args.expected_homepage_recommend_post_id = ["post-home"]
    args.expected_video_post_id = args.expected_premium_video_post_id = ["post-video"]
    args.only_check = list(probe.CONTENT_FEED_CHECK_NAMES)
    expected = {"identity=work&sort=recommend": "post-discovery", "channelId=recommend": "post-home",
                "identity=work&type=video": "post-video", "channelId=premium_stream": "post-video"}
    seen = set()
    def fake_request(_method, url, **kwargs):
        assert "Authorization" not in kwargs["headers"]
        for query, post_id in expected.items():
            if query in url:
                seen.add(query)
                return True, 200, json.dumps({"items": [{"postId": post_id}], "objectCards": []})
        raise AssertionError(url)
    monkeypatch.setattr(probe, "request", fake_request)
    assert probe.run_checks(args)["status"] == "passed"
    assert seen == set(expected)


@pytest.mark.parametrize("empty", [False, True])
def test_public_feeds__empty_or_unbound_never_passes__local_contract(monkeypatch, empty):
    args = _args()
    args.only_check = ["content_feed"]
    monkeypatch.setattr(probe, "request", lambda *_, **__: (True, 200, json.dumps({
        "items": [] if empty else [{"postId": "unbound"}], "objectCards": []})))
    report = probe.run_checks(args)
    assert report["status"] == "failed"
    fragment = 'empty "items"' if empty else "requires exact immutable release post IDs"
    assert any(fragment in finding for finding in report["findings"])


def test_public_readback__redacts_ordinary_credentials__local_contract(monkeypatch):
    args = _args()
    args.test_auth_token = "ordinary-login-token"
    args.expected_discovery_post_id = ["post-a"]
    args.only_check = ["content_feed"]
    monkeypatch.setattr(probe, "request", lambda *_, **__: (True, 200, json.dumps({
        "items": [{"postId": "post-a"}], "objectCards": [], "debugEcho": "Bearer ordinary-login-token"})))
    report = probe.run_checks(args)
    assert report["status"] == "passed"
    assert "ordinary-login-token" not in json.dumps(report)
    assert "[REDACTED]" in json.dumps(report)


@pytest.mark.parametrize("key,body,mime,drift", [
    (IMAGE, b"image", "image/webp", "hash"), (IMAGE, b"image", "image/webp", "mime"),
    (IMAGE, b"image", "image/webp", "empty"), (IMAGE, b"image", "image/webp", "length"),
    (VIDEO, b"ftyp-video", "video/mp4", "hash"), (VIDEO, b"ftyp-video", "video/mp4", "range"),
])
def test_public_media__hash_mime_bytes_and_range_drift_blocks__local_contract(monkeypatch, key, body, mime, drift):
    asset = _asset(key, body, mime)
    monkeypatch.setattr(transport.urllib.request, "urlopen", _urlopen({key: (asset, body)}, [], drift=drift))
    with pytest.raises(ValueError):
        probe.probe_public_media(MEDIA_ORIGIN + "/" + key, kind=asset["kind"], asset=asset, timeout=3)


@pytest.mark.parametrize("avatar", ["media/objects/sha256/aa/avatar-a", "media/avatar/s/asset/avatar-a/source.jpg", AVATAR + "?sign=secret"])
def test_public_creator__rejects_private_or_noncanonical_avatar__local_contract(avatar):
    args = _args()
    args.release_creator_profile = [json.dumps({**_creator(), "avatarDeliveryRef": avatar})]
    with pytest.raises(ValueError, match="identity is invalid"):
        probe.build_checks(args)


def test_public_media__declared_retry_keeps_trace_and_budget__local_contract(monkeypatch):
    import urllib.error

    body = b"image"
    asset = _asset(IMAGE, body, "image/webp")
    successful_open = _urlopen({IMAGE: (asset, body)}, [])
    calls = []
    delays = []
    transient = json.dumps({"nature": "transient", "recovery": {
        "action": "retry", "afterSeconds": 0.25,
    }}).encode()

    def open_url(request, timeout):
        calls.append(request)
        if len(calls) == 1:
            raise urllib.error.HTTPError(request.full_url, 503, "unavailable", {}, io.BytesIO(transient))
        return successful_open(request, timeout)

    monkeypatch.setattr(transport.urllib.request, "urlopen", open_url)
    monkeypatch.setattr(transport.time, "sleep", delays.append)
    evidence = probe.probe_public_media(
        MEDIA_ORIGIN + "/" + IMAGE, kind="image", asset=asset,
        timeout=3, retry_attempts=2, retry_sleep_seconds=0,
    )
    assert evidence["hashVerified"]
    assert evidence["retriedAttempts"] == [{"attempt": 1, "statusCode": 503, "declaredAfterSeconds": 0.25}]
    assert delays == [0.25]
    assert len(calls) == 2


def test_public_media__unbound_video_still_requires_range_and_playable_header__local_contract(monkeypatch):
    body = b"\x00\x00\x00\x18ftypmp42-video"
    asset = _asset(VIDEO, body, "video/mp4")
    monkeypatch.setattr(transport.urllib.request, "urlopen", _urlopen({VIDEO: (asset, body)}, []))
    evidence = probe.probe_public_media(MEDIA_ORIGIN + "/" + VIDEO, kind="video", timeout=3)
    assert evidence["status"] == 206
    assert evidence["hashVerified"] is False
    monkeypatch.setattr(transport.urllib.request, "urlopen", _urlopen({VIDEO: (asset, body)}, [], drift="range"))
    with pytest.raises(ValueError, match="byte ranges"):
        probe.probe_public_media(MEDIA_ORIGIN + "/" + VIDEO, kind="video", timeout=3)
