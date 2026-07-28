"""Public post consumers must prove the releaseimport owner bindings exactly."""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest


ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.io import write_json  # noqa: E402
from content.release.environment import post_api_verification as subject  # noqa: E402
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
        "authorId": "creator-article-a",
        "body": "文章正文",
    },
    {
        "postRef": "image/test-image-a",
        "postId": "post-image-a",
        "contentType": "image",
        "authorId": "creator-image-a",
        "mediaUrls": ["https://media.test/image-a.jpg"],
        "coverUrl": "https://media.test/image-a.jpg",
    },
    {
        "postRef": "video/test-video-a",
        "postId": "post-video-a",
        "contentType": "video",
        "authorId": "creator-video-a",
        "mediaUrls": ["https://media.test/video-a.mp4"],
        "coverUrl": "https://media.test/video-a.jpg",
        "videoUrl": "https://media.test/video-a.mp4",
        "sourceAttribution": VIDEO_ATTRIBUTION,
    },
)
CREATORS = tuple(
    {
        "creatorRef": f"creator-{index}",
        "authorId": row["authorId"],
        "subAccountId": f"author-profile-{index}",
        "displayName": f"内容作者 {index}",
    }
    for index, row in enumerate(POSTS, start=1)
)


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
        write_json(
            release
            / "payload/objects/creators"
            / creator["creatorRef"]
            / "profile.json",
            {
                "schema": "quwoquan_data.creator_profile",
                "creatorId": creator["creatorRef"],
                "authorId": creator["authorId"],
                "subAccountId": creator["subAccountId"],
                "displayName": creator["displayName"],
            },
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
    return release


def _write_import_report(root: Path, *, environment: DeploymentEnvironment) -> Path:
    report = root / "env" / environment.value / "runs/data-release" / RELEASE_ID / "apply-001/import.json"
    write_json(
        report,
        {
            "schema": "quwoquan.content_import_report",
            "status": "active",
            "environment": environment.value,
            "releaseId": RELEASE_ID,
            "counts": {"postsLoaded": len(POSTS), "entitiesLoaded": 0},
            "postBindings": [
                {
                    "postRef": f"posts/{row['postRef']}",
                    "postId": row["postId"],
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


class _PostApiHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        request = urlparse(self.path)
        if request.path.startswith("/content/posts/"):
            post_id = request.path.rsplit("/", 1)[-1]
            payload = next((row for row in POSTS if row["postId"] == post_id), None)
        elif request.path == "/content/feed":
            content_type = parse_qs(request.query).get("type", [""])[0]
            payload = {"items": [row for row in POSTS if row["contentType"] == content_type]}
        elif request.path.startswith("/user/"):
            sub_account_id = request.path.rsplit("/", 1)[-1]
            creator = next(
                (row for row in CREATORS if row["subAccountId"] == sub_account_id),
                None,
            )
            payload = (
                {
                    "subAccountId": creator["subAccountId"],
                    "displayName": creator["displayName"],
                    "subjectType": "creator",
                }
                if creator
                else None
            )
        else:
            payload = None
        if payload is None:
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        return


def _write_pagination_contract(path: Path) -> None:
    path.write_text(
        "types:\n  Pagination:\n    fields:\n      - name: limit\n        max: 2\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    "environment",
    [
        DeploymentEnvironment.ALPHA,
        DeploymentEnvironment.BETA,
        DeploymentEnvironment.GAMMA,
    ],
)
def test_post_api_verification__binds_releaseimport_posts__contract__local_contract(
    environment: DeploymentEnvironment,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    release = _write_release(tmp_path)
    import_report = _write_import_report(tmp_path, environment=environment)
    creator_import_report = _write_creator_import_report(tmp_path, environment=environment)
    pagination = tmp_path / "service-pagination.yaml"
    _write_pagination_contract(pagination)
    monkeypatch.setattr(subject, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(subject, "SERVICE_PAGINATION_CONTRACT_PATH", pagination)

    def _get_bytes(_client, url: str, **_kwargs):
        if url.endswith(".mp4"):
            return SimpleNamespace(
                status=206,
                content_type="video/mp4",
                content_range="bytes 0-15/128",
                body=b"\x00\x00\x00\x18ftypisomtest",
            )
        return SimpleNamespace(
            status=206,
            content_type="image/jpeg",
            content_range="bytes 0-3/64",
            body=b"\xff\xd8\xff\xe0",
        )

    monkeypatch.setattr(subject.PublicApiClient, "get_bytes", _get_bytes)
    server = HTTPServer(("127.0.0.1", 0), _PostApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        report = subject.write_post_api_verification(
            environment=environment,
            release_id=RELEASE_ID,
            run_id="consumer-api-001",
            release_root=release,
            importer_report_path=import_report,
            creator_importer_report_path=creator_import_report,
            output_path=tmp_path / "env" / environment.value / "runs/data-release" / RELEASE_ID / "consumer-api-001/post-api-verification.json",
            api_base_url=f"http://127.0.0.1:{server.server_port}",
            insecure_tls=False,
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)

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
    assert {row["sourceAttributionReady"] for row in payload["posts"]} == {True}
    assert sum(row["mediaProbeCount"] for row in payload["posts"]) == 3


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
    monkeypatch.setattr(subject, "SERVICE_PAGINATION_CONTRACT_PATH", pagination)

    with pytest.raises(subject.PostApiVerificationError, match="do not exactly match"):
        subject.write_post_api_verification(
            environment=DeploymentEnvironment.BETA,
            release_id=RELEASE_ID,
            run_id="consumer-api-002",
            release_root=release,
            importer_report_path=import_report,
            creator_importer_report_path=creator_import_report,
            output_path=tmp_path / "env/beta/runs/data-release" / RELEASE_ID / "consumer-api-002/post-api-verification.json",
            api_base_url="http://127.0.0.1:1",
            insecure_tls=False,
        )


def test_video_media_probe_requires_range_and_playable_header() -> None:
    client = SimpleNamespace(
        get_bytes=lambda _url: SimpleNamespace(
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
