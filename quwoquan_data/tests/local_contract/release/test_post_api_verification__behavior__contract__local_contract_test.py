"""Public post consumers must prove the releaseimport owner bindings exactly."""
from __future__ import annotations

import hashlib
import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.io import write_json  # noqa: E402
from core.release_layout import payload_digest  # noqa: E402
from content.release.environment import post_api_verification as subject  # noqa: E402
from content.release.environment import public_api_client as public_api_subject  # noqa: E402
from content.release.environment.public_api_client import (  # noqa: E402
    PublicApiOperationEvidence,
    PublicApiResponse,
    PublicGuestSession,
)
from content.release.model import DeploymentEnvironment  # noqa: E402


RELEASE_ID = "release-post-api-a"
VIDEO_ATTRIBUTION = {
    "isOriginal": False,
    "originalCreatorName": "测试作者",
    "platform": "Wikimedia Commons",
    "sourcePostUrl": "https://commons.wikimedia.org/wiki/File:test.webm",
    "attributionText": "测试作者 — CC BY-SA 4.0",
    "rightsBasis": "CC BY-SA 4.0",
    "commercialAuthorizationStatus": "verified",
    "publicationAdmission": "commercial_release",
    "watermarkStatus": "absent",
    "audioRightsStatus": "no_audio",
}
POSTS = (
    {
        "postRef": "article/test-article-a",
        "postId": "post-article-a",
        "contentType": "article",
        "contentIdentity": "work",
        "authorId": "creator-article-a",
        "body": "文章正文",
    },
    {
        "postRef": "image/test-image-a",
        "postId": "post-image-a",
        "contentType": "image",
        "contentIdentity": "work",
        "authorId": "creator-image-a",
        "mediaUrls": [
            "https://media.test/media/image/s/asset/image-a/v1/source.jpg"
        ],
        "coverUrl": "https://media.test/media/image/s/asset/image-a/v1/source.jpg",
    },
    {
        "postRef": "video/test-video-a",
        "postId": "post-video-a",
        "contentType": "video",
        "contentIdentity": "work",
        "authorId": "creator-video-a",
        "mediaUrls": [
            "https://media.test/media/video/s/asset/video-a/v1/source.mp4"
        ],
        "coverUrl": (
            "https://media.test/media/image/s/asset/video-cover-a/v1/source.jpg"
        ),
        "videoUrl": "https://media.test/media/video/s/asset/video-a/v1/source.mp4",
        "sourceAttribution": VIDEO_ATTRIBUTION,
    },
)
CREATORS = tuple(
    {
        "creatorRef": f"creator-{index}",
        "authorId": row["authorId"],
        "personaId": f"author-profile-{index}",
        "displayName": f"内容作者 {index}",
        "avatarAssetId": None if index == 2 else f"creator-avatar-{index}",
        "avatarSha256": None
        if index == 2
        else "sha256:" + hashlib.sha256(b"\xff\xd8\xff\xe0").hexdigest(),
        "avatarPublicSliceKey": None
        if index == 2
        else f"media/avatar/s/asset/creator-avatar-{index}/v1/source.jpg",
    }
    for index, row in enumerate(POSTS, start=1)
)
CREATORS_BY_AUTHOR = {row["authorId"]: row for row in CREATORS}


def _projected_post(row: dict[str, object]) -> dict[str, object]:
    creator = CREATORS_BY_AUTHOR[str(row["authorId"])]
    return {
        **row,
        "authorDisplayName": creator["displayName"],
        "authorAvatarUrl": (
            "https://media.test/" + str(creator["avatarPublicSliceKey"])
            if creator["avatarPublicSliceKey"]
            else ""
        ),
    }


def _write_release(root: Path) -> Path:
    release = root / "data/releases" / RELEASE_ID
    write_json(
        release / "payload/desired_state.json",
        {
            "schema": "quwoquan_data.release_desired_state",
            "releaseId": RELEASE_ID,
            "desiredRefs": {
                "posts": [row["postRef"] for row in POSTS],
                "entities": [],
                "creators": [row["creatorRef"] for row in CREATORS],
            },
            "actions": [],
        },
    )
    for creator in CREATORS:
        profile = {
            "schema": "quwoquan_data.creator_profile",
            "creatorId": creator["creatorRef"],
            "authorId": creator["authorId"],
            "personaId": creator["personaId"],
            "displayName": creator["displayName"],
        }
        if creator["avatarAssetId"]:
            profile["avatarAsset"] = {
                "assetId": creator["avatarAssetId"],
                "kind": "avatar",
                "sha256": creator["avatarSha256"],
            }
        write_json(
            release
            / "payload/objects/creators"
            / creator["creatorRef"]
            / "profile.json",
            profile,
        )
    for post in POSTS:
        manifest = {"contentType": post["contentType"]}
        if post["contentType"] == "video":
            manifest["sourceAttribution"] = VIDEO_ATTRIBUTION
        write_json(
            release
            / "payload/objects/posts"
            / post["postRef"]
            / "manifest.json",
            manifest,
        )
    write_json(
        release / "payload/media_manifest.json",
        {
            "schema": "quwoquan_data.release_media_manifest",
            "releaseId": RELEASE_ID,
            "sourceOwner": "qwq_data",
            "assets": [
                {
                    "assetId": creator["avatarAssetId"],
                    "kind": "avatar",
                    "version": 1,
                    "contentType": "image/jpeg",
                    "publicSliceKey": creator["avatarPublicSliceKey"],
                    "sha256": creator["avatarSha256"],
                    "bytes": 4,
                    "ownerRefs": [f"creators/{creator['creatorRef']}"],
                    "rightsSnapshotRefs": [
                        f"rights/creators/{creator['creatorRef']}.json"
                    ],
                }
                for creator in CREATORS
                if creator["avatarAssetId"]
            ]
            + [
                {
                    "assetId": "image-a",
                    "kind": "image",
                    "version": 1,
                    "contentType": "image/jpeg",
                    "publicSliceKey": "media/image/s/asset/image-a/v1/source.jpg",
                    "sha256": "sha256:"
                    + hashlib.sha256(b"\xff\xd8\xff\xe0").hexdigest(),
                    "bytes": 4,
                    "ownerRefs": ["posts/image/test-image-a"],
                    "rightsSnapshotRefs": ["rights/image-a.json"],
                },
                {
                    "assetId": "video-cover-a",
                    "kind": "image",
                    "version": 1,
                    "contentType": "image/jpeg",
                    "publicSliceKey": (
                        "media/image/s/asset/video-cover-a/v1/source.jpg"
                    ),
                    "sha256": "sha256:"
                    + hashlib.sha256(b"\xff\xd8\xff\xe0").hexdigest(),
                    "bytes": 4,
                    "ownerRefs": ["posts/video/test-video-a"],
                    "rightsSnapshotRefs": ["rights/video-cover-a.json"],
                },
                {
                    "assetId": "video-a",
                    "kind": "video",
                    "version": 1,
                    "contentType": "video/mp4",
                    "publicSliceKey": "media/video/s/asset/video-a/v1/source.mp4",
                    "sha256": "sha256:"
                    + hashlib.sha256(b"\x00\x00\x00\x18ftypisomtest").hexdigest(),
                    "bytes": 16,
                    "ownerRefs": ["posts/video/test-video-a"],
                    "rightsSnapshotRefs": ["rights/video-a.json"],
                },
            ],
            "issues": [],
            "counts": {
                "assets": sum(1 for creator in CREATORS if creator["avatarAssetId"])
                + 3,
                "issues": 0,
            },
        },
    )
    return release


def _write_import_report(root: Path, *, environment: DeploymentEnvironment) -> Path:
    report = root / "env" / environment.value / "runs/data-release" / RELEASE_ID / "apply-001/import.json"
    write_json(
        report,
        {
            "schema": "quwoquan.content_import_report",
            "status": "imported",
            "environment": environment.value,
            "releaseId": RELEASE_ID,
            "sourceOwner": "qwq_data",
            "manifestDigest": payload_digest(
                root / "data" / "releases" / RELEASE_ID
            ),
            "mode": "sync",
            "deletePolicy": "tombstone",
            "counts": {"postsLoaded": len(POSTS), "entitiesLoaded": 0},
            "postBindings": [
                {
                    "postRef": row["postRef"],
                    "postId": row["postId"],
                    "contentId": f"content-{row['postId']}",
                    "contentVersion": 1,
                    "usageScope": "commercial",
                    "contentType": row["contentType"],
                    "authorId": row["authorId"],
                }
                for row in POSTS
            ],
            "auditEvents": [],
        },
    )
    return report


def _write_creator_import_report(root: Path, *, environment: DeploymentEnvironment) -> Path:
    report = (
        root
        / "env"
        / environment.value
        / "runs/data-release"
        / RELEASE_ID
        / "apply-001/creator-import.json"
    )
    write_json(
        report,
        {
            "schema": "quwoquan.user_creator_import_report",
            "status": "active",
            "environment": environment.value,
            "releaseId": RELEASE_ID,
            "sourceOwner": "qwq_data",
            "mode": "sync",
            "projectionDatabase": "quwoquan_user",
            "counts": {
                "creatorsLoaded": len(CREATORS),
                "usersUpserted": len(CREATORS),
                "creatorsUpserted": len(CREATORS),
                "usersRemoved": 0,
                "creatorsRemoved": 0,
            },
            "authorIds": [row["authorId"] for row in CREATORS],
            "verifiedCreatorIds": [row["creatorRef"] for row in CREATORS],
            "generatedAt": "2026-07-23T00:00:00Z",
        },
    )
    return report


def _operation(path: str, page_id: str, *, status: int = 200) -> PublicApiOperationEvidence:
    nonce = uuid.uuid4().hex
    return PublicApiOperationEvidence(
        path=f"/{path.lstrip('/')}",
        page_id=page_id,
        status=status,
        request_id=f"DATA.{page_id}.{nonce}",
        trace_id=f"DATA.readiness.{page_id}.{nonce}",
        started_at="2026-07-28T00:00:00.000Z",
        ended_at="2026-07-28T00:00:00.001Z",
        duration_ms=1,
    )


def _guest_session() -> PublicGuestSession:
    return PublicGuestSession(
        access_token="fresh-guest-token",
        guest_actor_hash="sha256:" + "a" * 64,
        device_actor_id="b" * 32,
        login_operation=_operation(
            "auth/login/anonymous",
            "user.login.anonymous",
        ),
    )


def _get_json(
    client,
    path: str,
    *,
    page_id: str,
    query: dict[str, str] | None = None,
):
    assert client.bearer_token == "fresh-guest-token"
    query = query or {}
    payload = None
    if path.startswith("content/posts/"):
        assert page_id == "content.post.get"
        post_id = path.rsplit("/", 1)[-1]
        payload = next(
            (_projected_post(row) for row in POSTS if row["postId"] == post_id),
            None,
        )
    elif path == "content/feed":
        assert page_id == "content.feed.list"
        content_type = query.get("type", "")
        identity = query.get("identity", "")
        channel_id = query.get("channelId", "")
        rows = [
            {
                key: value
                for key, value in row.items()
                if key not in {"postRef", "sourceAttribution"}
            }
            for row in (_projected_post(post) for post in POSTS)
        ]
        if identity and identity != "work":
            rows = []
        if content_type:
            rows = [row for row in rows if row["contentType"] == content_type]
        if channel_id == "premium_stream":
            rows = [row for row in rows if row["contentType"] == "video"]
        payload = {"items": rows, "objectCards": []}
    elif path.startswith("user/"):
        assert page_id == "user.profile"
        persona_id = path.rsplit("/", 1)[-1]
        creator = next(
            (row for row in CREATORS if row["personaId"] == persona_id),
            None,
        )
        if creator:
            payload = {
                "personaId": creator["personaId"],
                "displayName": creator["displayName"],
                "subjectType": "creator",
                "avatarUrl": (
                    "https://media.test/" + creator["avatarPublicSliceKey"]
                    if creator["avatarPublicSliceKey"]
                    else ""
                ),
            }
    status = 200 if payload is not None else 404
    return PublicApiResponse(
        status=status,
        payload=payload or {},
        operation=_operation(path, page_id, status=status),
    )


def _write_pagination_contract(path: Path) -> None:
    path.write_text(
        "api_routes:\n"
        "  - method: GET\n"
        "    path: /content/feed\n"
        "    operation: GetFeed\n"
        "    pagination:\n"
        "      maximum_items: 2\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("environment", "readiness_phase"),
    [
        (DeploymentEnvironment.ALPHA, "commercial"),
        (DeploymentEnvironment.BETA, "commercial"),
        (DeploymentEnvironment.GAMMA, "commercial"),
        (DeploymentEnvironment.GAMMA, "consumer"),
    ],
)
def test_post_api_verification__binds_releaseimport_posts__contract__local_contract(
    environment: DeploymentEnvironment,
    readiness_phase: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    release = _write_release(tmp_path)
    import_report = _write_import_report(tmp_path, environment=environment)
    creator_import_report = _write_creator_import_report(tmp_path, environment=environment)
    pagination = tmp_path / "service-pagination.yaml"
    _write_pagination_contract(pagination)
    monkeypatch.setattr(subject, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(subject, "CONTENT_POST_OPERATIONS_PATH", pagination)

    def _get_bytes(_client, url: str, **kwargs):
        if url.endswith(".mp4"):
            return SimpleNamespace(
                status=206,
                content_type="video/mp4",
                content_range="bytes 0-15/128",
                body=b"\x00\x00\x00\x18ftypisomtest",
            )
        return SimpleNamespace(
            status=200 if not kwargs.get("byte_range") else 206,
            content_type="image/jpeg",
            content_range="" if not kwargs.get("byte_range") else "bytes 0-3/64",
            body=b"\xff\xd8\xff\xe0",
            etag='"image-etag"',
        )

    monkeypatch.setattr(subject.PublicApiClient, "get_bytes", _get_bytes)
    monkeypatch.setattr(subject.PublicApiClient, "get_json", _get_json)
    search_bodies: list[dict[str, object]] = []

    def _post_json(_client, path: str, *, page_id: str, body, **_kwargs):
        assert path == "search"
        assert page_id == "search.global"
        search_bodies.append(dict(body))
        object_id = str((body.get("ids") or [""])[0])
        post = next((row for row in POSTS if row["postId"] == object_id), None)
        if post is not None:
            assert body["objectTypes"] == ["content.post"]
            assert body["contentTypes"] == [post["contentType"]]
        else:
            assert object_id in {row["personaId"] for row in CREATORS}
            assert body["objectTypes"] == ["user.profile"]
            assert "contentTypes" not in body
        return PublicApiResponse(
            status=200,
            payload={"hits": [{"objectId": object_id}]},
            operation=_operation(path, page_id, status=200),
        )

    monkeypatch.setattr(subject.PublicApiClient, "post_json", _post_json)
    monkeypatch.setattr(
        subject.PublicApiClient,
        "login_fresh_guest",
        lambda _client: _guest_session(),
    )
    report = subject.write_post_api_verification(
        environment=environment,
        release_id=RELEASE_ID,
        run_id="consumer-api-001",
        release_root=release,
        importer_report_path=import_report,
        creator_importer_report_path=creator_import_report,
        output_path=tmp_path
        / "env"
        / environment.value
        / "runs/data-release"
        / RELEASE_ID
        / "consumer-api-001/post-api-verification.json",
        api_base_url="https://api.test",
        media_delivery_base_url="https://media.test",
        readiness_phase=readiness_phase,
    )

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert [row["postRef"] for row in payload["posts"]] == sorted(
        row["postRef"] for row in POSTS
    )
    assert {row["contentType"] for row in payload["posts"]} == {
        "article",
        "image",
        "video",
    }
    assert {row["authorProfileStatus"] for row in payload["posts"]} == {200}
    assert {row["avatarMediaReady"] for row in payload["creators"]} == {
        False,
        True,
    }
    assert {row["avatarProbeCount"] for row in payload["creators"]} == {0, 1}
    assert {
        row["avatarProbe"]["hashVerified"]
        for row in payload["creators"]
        if row["avatarProbe"] is not None
    } == {True}
    default_avatar = next(
        row for row in payload["creators"] if row["usesPlatformDefaultAvatar"]
    )
    assert default_avatar["avatarAssetId"] is None
    assert default_avatar["avatarUrl"] == ""
    assert payload["mediaDeliveryBaseUrl"] == "https://media.test"
    assert {row["sourceAttributionReady"] for row in payload["posts"]} == {True}
    assert sum(row["mediaProbeCount"] for row in payload["posts"]) == 3
    image_probes = [
        probe
        for row in payload["posts"]
        for probe in row["mediaProbes"]
        if probe["kind"] == "image"
    ]
    assert len(image_probes) == 2
    assert {probe["hashVerified"] for probe in image_probes} == {True}
    queries = {row["name"]: row for row in payload["feedQueries"]}
    assert payload["readinessPhase"] == readiness_phase
    assert queries["typed_video"]["query"] == "identity=work&type=video&limit=2"
    assert queries["typed_video"]["matchedPostIds"] == ["post-video-a"]
    if readiness_phase == "commercial":
        assert queries["premium_stream"]["matchedPostIds"] == ["post-video-a"]
        assert len(payload["searchQueries"]) == len(POSTS) + len(CREATORS)
        assert len(search_bodies) == len(POSTS) + len(CREATORS)
    else:
        assert "premium_stream" not in queries
        assert "searchQueries" not in payload
        assert search_bodies == []
    assert payload["guestActorHash"] == "sha256:" + "a" * 64
    assert payload["guestLogin"]["pageId"] == "user.login.anonymous"
    assert {request["pageId"] for row in queries.values() for request in row["requests"]} == {
        "content.feed.list"
    }
    serialized = report.read_text(encoding="utf-8")
    assert "fresh-guest-token" not in serialized
    assert "installId" not in serialized


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"items": []},
        {"items": [], "objectCards": None},
        {"items": [], "objectCards": {}},
    ],
)
def test_visible_release_feed__rejects_invalid_object_cards_envelope__local_contract(
    payload: object,
) -> None:
    client = SimpleNamespace(
        get_json=lambda *_args, **_kwargs: SimpleNamespace(status=200, payload=payload)
    )

    with pytest.raises(
        subject.PostApiVerificationError,
        match="response payload must be an object|lacks objectCards array",
    ):
        subject._verify_visible_release_feed(
            client,
            cases_by_id={},
            creators_by_author={},
            name="discovery_work",
            query={"identity": "work"},
        )


def test_feed_item_match__accepts_canonical_projection_subset__local_contract() -> None:
    case = SimpleNamespace(
        post_ref="article/test-article-a",
        author_id="creator-article-a",
        content_type=SimpleNamespace(value="article"),
    )
    creator = SimpleNamespace(
        display_name="内容作者 1",
        avatar_url=(
            "https://media.test/media/avatar/s/asset/creator-avatar-1/v1/source.jpg"
        ),
    )

    matched = subject._feed_item_matches_release(
        {
            "postId": "post-article-a",
            "contentType": "article",
            "contentIdentity": "work",
            "authorId": "creator-article-a",
            "authorDisplayName": "内容作者 1",
            "authorAvatarUrl": (
                "https://media.test/media/avatar/s/asset/creator-avatar-1/v1/source.jpg"
            ),
        },
        cases_by_id={"post-article-a": case},
        creators_by_author={"creator-article-a": creator},
        endpoint="canonical subset feed",
    )

    assert matched == "post-article-a"


def test_author_profile__rejects_avatar_version_query__local_contract() -> None:
    canonical_url = (
        "https://media.test/media/avatar/s/asset/creator-avatar-1/v1/source.jpg"
    )
    creator = SimpleNamespace(
        persona_id="author-profile-1",
        creator_ref="creator-1",
        display_name="内容作者 1",
        avatar_url=canonical_url,
        avatar_asset_id="creator-avatar-1",
    )
    client = SimpleNamespace(
        get_json=lambda *_args, **_kwargs: PublicApiResponse(
            status=200,
            payload={
                "personaId": creator.persona_id,
                "displayName": creator.display_name,
                "avatarUrl": f"{canonical_url}?v=1",
            },
            operation=_operation("user/author-profile-1", "user.profile", status=200),
        )
    )

    with pytest.raises(
        subject.PostApiVerificationError,
        match="creator public avatar URL drift",
    ):
        subject._verify_author_profile(client, creator)


@pytest.mark.parametrize("missing_field", ["authorDisplayName", "authorAvatarUrl"])
def test_feed_item_match__rejects_missing_creator_snapshot__local_contract(
    missing_field: str,
) -> None:
    case = SimpleNamespace(
        post_ref="article/test-article-a",
        author_id="creator-article-a",
        content_type=SimpleNamespace(value="article"),
    )
    creator = SimpleNamespace(
        display_name="内容作者 1",
        avatar_url=(
            "https://media.test/media/avatar/s/asset/creator-avatar-1/v1/source.jpg"
        ),
    )
    item = {
        "postId": "post-article-a",
        "contentType": "article",
        "contentIdentity": "work",
        "authorId": "creator-article-a",
        "authorDisplayName": "内容作者 1",
        "authorAvatarUrl": creator.avatar_url,
    }
    item.pop(missing_field)

    with pytest.raises(
        subject.PostApiVerificationError,
        match=rf"lacks required {missing_field}",
    ):
        subject._feed_item_matches_release(
            item,
            cases_by_id={"post-article-a": case},
            creators_by_author={"creator-article-a": creator},
            endpoint="creator snapshot feed",
        )


@pytest.mark.parametrize("unknown_field", ["sourceTaskId", "qualityScore"])
def test_feed_item_match__rejects_unknown_projection_field__local_contract(
    unknown_field: str,
) -> None:
    item = {
        "postId": "post-article-a",
        "contentType": "article",
        "contentIdentity": "work",
        "authorId": "creator-article-a",
        unknown_field: "must-not-pass",
    }

    with pytest.raises(
        subject.PostApiVerificationError,
        match=rf"unknown ContentPostProjection fields: {unknown_field}",
    ):
        subject._feed_item_matches_release(
            item,
            cases_by_id={},
            creators_by_author={},
            endpoint="unknown field feed",
        )


def test_post_api_verification__rejects_incomplete_releaseimport_binding__contract__local_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    release = _write_release(tmp_path)
    import_report = _write_import_report(tmp_path, environment=DeploymentEnvironment.BETA)
    creator_import_report = _write_creator_import_report(tmp_path, environment=DeploymentEnvironment.BETA)
    report_payload = json.loads(import_report.read_text(encoding="utf-8"))
    report_payload["postBindings"] = report_payload["postBindings"][:-1]
    import_report.write_text(json.dumps(report_payload, ensure_ascii=False), encoding="utf-8")
    pagination = tmp_path / "service-pagination.yaml"
    _write_pagination_contract(pagination)
    monkeypatch.setattr(subject, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(subject, "CONTENT_POST_OPERATIONS_PATH", pagination)

    with pytest.raises(subject.PostApiVerificationError, match="do not exactly match"):
        subject.write_post_api_verification(
            environment=DeploymentEnvironment.BETA,
            release_id=RELEASE_ID,
            run_id="consumer-api-002",
            release_root=release,
            importer_report_path=import_report,
            creator_importer_report_path=creator_import_report,
            output_path=tmp_path / "env/beta/runs/data-release" / RELEASE_ID / "consumer-api-002/post-api-verification.json",
            api_base_url="https://api.test",
            media_delivery_base_url="https://media.test",
        )


def test_post_api_verification__rejects_import_manifest_digest_drift__local_contract(
    tmp_path: Path,
) -> None:
    release = _write_release(tmp_path)
    import_report = _write_import_report(
        tmp_path,
        environment=DeploymentEnvironment.GAMMA,
    )
    creator_import_report = _write_creator_import_report(
        tmp_path,
        environment=DeploymentEnvironment.GAMMA,
    )
    report_payload = json.loads(import_report.read_text(encoding="utf-8"))
    report_payload["manifestDigest"] = "sha256:" + "0" * 64
    import_report.write_text(
        json.dumps(report_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(subject.PostApiVerificationError, match="manifestDigest"):
        subject.write_post_api_verification(
            environment=DeploymentEnvironment.GAMMA,
            release_id=RELEASE_ID,
            run_id="consumer-api-digest-drift",
            release_root=release,
            importer_report_path=import_report,
            creator_importer_report_path=creator_import_report,
            output_path=tmp_path
            / "env/gamma/runs/data-release"
            / RELEASE_ID
            / "consumer-api-digest-drift/post-api-verification.json",
            api_base_url="https://api.test",
            media_delivery_base_url="https://media.test",
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
