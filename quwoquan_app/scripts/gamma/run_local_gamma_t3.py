#!/usr/bin/env python3
"""Run local-gamma T3 checks against the Docker mirror."""

import argparse
import contextlib
import hashlib
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.local_environment_auth import (  # noqa: E402
    LocalAcceptanceSession as LocalGammaAcceptanceSession,
    open_local_acceptance_session,
)
from quwoquan_ops.cli.lib.output_paths import env_run_dir  # noqa: E402

MANIFEST = ROOT / "quwoquan_service/contracts/metadata/_shared/test_fixtures/app_gamma_seed_manifest.json"
METADATA_ROOT = ROOT / "quwoquan_service/contracts/metadata"
# stackctl injects QWQ_RUN_ROOT. A standalone probe creates the same kind of
# timestamped run evidence instead of leaking reports into local process state.
GAMMA_RUN_ROOT = Path(
    os.environ.get("QWQ_RUN_ROOT")
    or env_run_dir("gamma", "local-gamma-t3", target="gamma-local")
)
COMPOSE_FILE = ROOT / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
COMPOSE_PROJECT = os.environ.get("LOCAL_GAMMA_COMPOSE_PROJECT") or os.environ.get(
    "COMPOSE_PROJECT_NAME", "quwoquan_service"
)
CONTRACT_GRAPH = ROOT / "quwoquan_service/generated/contract_graph.json"
RAW_INTERACTION_STATS_RE = re.compile(r"[0-9０-９]+\s*(赞|评|转|转发)")
COUNT_SUBJECT_RE = re.compile(r"[0-9０-９]+\s*(人|位)")
DISPLAY_STATEMENT_BANNED_FRAGMENTS = (
    "共同好友",
    "都来这里互动过",
    "在这里互动过",
    "同读者",
    "相近主题",
    "TA的内容",
    "相关圈子",
    "我的连接",
    "我的影响力",
    "你和这里",
    "你和这个圈子",
    "你们有共同",
    "为你推荐的相关内容",
    "最近在看这些",
)
DISPLAY_OBJECT_TARGET_TYPES = {"user", "circle", "homepage", "post", "task"}
DEFAULT_ENABLED_DOMAINS = ("content", "chat", "circle", "entity", "user")
_ACTIVE_SESSION: Optional[LocalGammaAcceptanceSession] = None


def gamma_probe_idempotency_key(purpose: str) -> str:
    """Return a retry-stable key scoped to one immutable Gamma verification run."""
    normalized = re.sub(r"[^a-z0-9-]+", "-", purpose.strip().lower()).strip("-")
    if not normalized:
        raise ValueError("Gamma probe idempotency purpose must not be empty")
    run_digest = hashlib.sha256(str(GAMMA_RUN_ROOT.resolve()).encode("utf-8")).hexdigest()[:16]
    return f"gamma-t3-{normalized}-v1-{run_digest}"


def load_manifest() -> Dict[str, Any]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


@contextlib.contextmanager
def local_gamma_dns_override():
    original_getaddrinfo = socket.getaddrinfo

    def getaddrinfo(host: object, *args: object, **kwargs: object):
        if isinstance(host, str) and host.endswith(".quwoquan-env.test"):
            host = "127.0.0.1"
        return original_getaddrinfo(host, *args, **kwargs)

    socket.getaddrinfo = getaddrinfo  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.getaddrinfo = original_getaddrinfo  # type: ignore[assignment]


def flutter_contract_base_url(url: str) -> str:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if host.endswith(".quwoquan-env.test"):
        local_host = host.replace(".quwoquan-env.test", ".localhost")
        port = f":{parsed.port}" if parsed.port else ""
        return urlunsplit(
            (parsed.scheme, f"{local_host}{port}", parsed.path, parsed.query, parsed.fragment)
        )
    return url


def default_request_headers() -> Dict[str, str]:
    if _ACTIVE_SESSION is None:
        return {}
    return {"Authorization": _ACTIVE_SESSION.authorization_header()}


def http_get(
    url: str,
    timeout: int = 5,
    *,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[int, bytes]:
    ctx = ssl._create_unverified_context()
    request_headers = default_request_headers()
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(
        url,
        headers=request_headers,
    )
    with local_gamma_dns_override():
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.status, resp.read()


def http_request(
    url: str,
    *,
    method: str = "GET",
    body: Optional[Dict[str, Any]] = None,
    timeout: int = 5,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[int, bytes]:
    ctx = ssl._create_unverified_context()
    request_headers = default_request_headers()
    if headers:
        request_headers.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        url,
        data=data,
        headers=request_headers,
        method=method,
    )
    with local_gamma_dns_override():
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.status, resp.read()


def wait_url(url: str, timeout_seconds: int) -> Dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            status, _ = http_get(url, timeout=3)
            if 200 <= status < 300:
                return {"status": "passed", "httpStatus": status}
            last_error = f"http {status}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            time.sleep(1)
    return {"status": "failed", "error": last_error}


def fixture_post_to_doc(post: Dict[str, Any]) -> Dict[str, Any]:
    post_id = (post.get("postId") or post.get("id") or "").strip()
    created_at = post.get("createdAt") or "2026-01-01T00:00:00Z"
    media_urls = post.get("imageUrls") or post.get("mediaUrls") or []
    if not media_urls and post.get("coverUrl") and post.get("contentType") == "image":
        media_urls = [post["coverUrl"]]
    thumbnail_url = post.get("thumbnailUrl") or post.get("coverUrl") or ""
    duration_ms = int(post.get("durationMs") or 0)
    media_items = list(post.get("mediaItems") or [])
    if not media_items and post.get("videoUrl"):
        media_items.append(
            {
                "kind": "video",
                "url": post["videoUrl"],
                "coverUrl": thumbnail_url,
                "durationMs": duration_ms,
                "width": post.get("width"),
                "height": post.get("height"),
            }
        )
    width = post.get("width")
    height = post.get("height")
    device_info = dict(post.get("deviceInfo") or {})
    if width is not None:
        width = int(width)
        device_info.setdefault("width", width)
        device_info.setdefault("imageWidth", width)
    if height is not None:
        height = int(height)
        device_info.setdefault("height", height)
        device_info.setdefault("imageHeight", height)
    if duration_ms > 0:
        device_info.setdefault("durationMs", duration_ms)
    revision_source = json.dumps(
        {
            "postId": post_id,
            "contentType": post.get("contentType") or post.get("type", ""),
            "title": post.get("title", ""),
            "body": post.get("body", ""),
            "mediaUrls": media_urls,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    doc = {
        "_id": post_id,
        "postId": post_id,
        "postRef": post_id,
        "version": 1,
        "contentDigest": "sha256:"
        + hashlib.sha256(revision_source.encode("utf-8")).hexdigest(),
        "authorId": post.get("authorId", ""),
        "subAccountId": post.get("subAccountId") or post.get("authorId", ""),
        "authorDisplayNameSnapshot": post.get("displayName", ""),
        "authorAvatarUrlSnapshot": post.get("authorAvatarUrl") or post.get("avatarUrl", ""),
        "personaContextVersion": 1,
        "contentType": post.get("contentType") or post.get("type", ""),
        "contentIdentity": post.get("contentIdentity") or post.get("identity", ""),
        "title": post.get("title", ""),
        "body": post.get("body", ""),
        "tags": post.get("tags") or [],
        "mediaUrls": media_urls,
        "mediaItems": media_items,
        "coverUrl": post.get("coverUrl", ""),
        "thumbnailUrl": thumbnail_url,
        "videoUrl": post.get("videoUrl", ""),
        "durationMs": duration_ms,
        "locationName": post.get("locationName", ""),
        "status": "published",
        "visibility": "public",
        "assistantUsePolicy": "allow",
        "circleId": post.get("circleId", ""),
        "circleIds": post.get("circleIds") or [],
        "summary": post.get("summary", ""),
        "likeCount": int(post.get("likeCount") or 0),
        "commentCount": int(post.get("commentCount") or 0),
        "favoriteCount": int(post.get("favoriteCount") or 0),
        "shareCount": int(post.get("shareCount") or 0),
        "moderationStatus": "approved",
        "createdAt": created_at,
        "updatedAt": created_at,
        "publishedAt": created_at,
        "lastActiveAt": created_at,
    }
    if device_info:
        doc["deviceInfo"] = device_info
    if width is not None:
        doc["width"] = width
    if height is not None:
        doc["height"] = height
    return doc


def gamma_domain_fixture_spec(domain: str) -> Tuple[str, List[str]]:
    """Return the (metadata-relative fixturePath, refs) for a seed domain."""
    manifest = load_manifest()
    item = next(
        (item for item in manifest.get("seedRefs", []) if item.get("domain") == domain),
        None,
    )
    if not isinstance(item, dict):
        raise RuntimeError(f"app_gamma_seed_manifest.json missing {domain} domain entry")
    fixture_rel = str(item.get("fixturePath") or "").strip()
    refs = [str(ref) for ref in item.get("refs", []) if str(ref).strip()]
    if not fixture_rel or not refs:
        raise RuntimeError(f"gamma {domain} seed manifest entry must declare fixturePath and refs")
    return fixture_rel, refs


def gamma_content_fixture_spec() -> Tuple[Path, List[str]]:
    fixture_rel, refs = gamma_domain_fixture_spec("content")
    return METADATA_ROOT / fixture_rel, refs


def mongo_published_port() -> str:
    return os.environ.get("LOCAL_GAMMA_MONGO_PORT", "19410")


def compose_command(*args: str) -> List[str]:
    return [
        "docker",
        "compose",
        "-p",
        COMPOSE_PROJECT,
        "-f",
        str(COMPOSE_FILE),
        *args,
    ]


def postgres_published_dsn() -> str:
    if os.environ.get("LOCAL_GAMMA_POSTGRES_DSN"):
        return os.environ["LOCAL_GAMMA_POSTGRES_DSN"]
    port = os.environ.get("LOCAL_GAMMA_POSTGRES_PORT", "19400")
    return f"postgres://quwoquan:quwoquan@localhost:{port}/quwoquan?sslmode=disable"


def seed_user() -> Dict[str, Any]:
    """Seed user profile fixtures into the live user PostgreSQL store.

    用户主页 (GET /user/profile/{userId}) and 我的主页 (GET /me) both read
    the user_profiles table. The seed cmd reuses the shared contract fixture
    loader + the generated user_profiles column set, so the persisted row stays
    single-sourced with the service.
    """
    try:
        fixture_rel, refs = gamma_domain_fixture_spec("user")
    except RuntimeError as exc:
        return {"status": "failed", "error": str(exc)}
    # Only user_profile_core backs the homepage reads; relationship/persona/feed
    # refs require backend features (e.g. following-subjects) not yet served.
    profile_refs = [ref for ref in refs if ref == "user_profile_core"] or ["user_profile_core"]
    cmd = [
        "go",
        "run",
        "./services/user-service/cmd/seed",
        "--pg-dsn",
        postgres_published_dsn(),
        "--fixture",
        fixture_rel,
        "--refs",
        ",".join(profile_refs),
    ]
    result = subprocess.run(
        cmd,
        cwd=ROOT / "quwoquan_service",
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return {
        "status": "passed" if result.returncode == 0 else "failed",
        "fixture": fixture_rel,
        "refs": profile_refs,
        "output": result.stdout[-2000:],
    }


def seed_circle() -> Dict[str, Any]:
    """Seed circle fixtures into the live circle MongoDB via the circle seed cmd.

    The seed command reuses the circle domain model + shared contract fixture
    loader, so the persisted document shape stays single-sourced with the
    service (no second hand-shaped representation, unlike a mongosh JSON blob).
    """
    try:
        fixture_rel, refs = gamma_domain_fixture_spec("circle")
    except RuntimeError as exc:
        return {"status": "failed", "error": str(exc)}
    cmd = [
        "go",
        "run",
        "./services/circle-service/cmd/seed",
        "--mongo-uri",
        f"mongodb://localhost:{mongo_published_port()}/?directConnection=true",
        "--database",
        "quwoquan_circle",
        "--fixture",
        fixture_rel,
        "--refs",
        ",".join(refs),
    ]
    result = subprocess.run(
        cmd,
        cwd=ROOT / "quwoquan_service",
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return {
        "status": "passed" if result.returncode == 0 else "failed",
        "fixture": fixture_rel,
        "refs": refs,
        "output": result.stdout[-2000:],
    }


def seed_chat() -> Dict[str, Any]:
    """Seed chat contract fixtures into gamma chat MongoDB.

    chat-service/cmd/seed-fixture loads messages/chat test fixtures and keeps
    memberCount / roster / group avatar metadata single-sourced with alpha.
    """
    refs = ["chat_core", "chat_contacts_core"]
    cmd = [
        "go",
        "run",
        "./cmd/seed-fixture",
        "--mongo-uri",
        f"mongodb://localhost:{mongo_published_port()}/?directConnection=true",
        "--database",
        "quwoquan_chat",
    ]
    for ref in refs:
        cmd.extend(["--seed-ref", ref])
    result = subprocess.run(
        cmd,
        cwd=ROOT / "quwoquan_service/services/chat-service",
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return {
        "status": "passed" if result.returncode == 0 else "failed",
        "refs": refs,
        "output": result.stdout[-2000:],
    }


def seed_entity(base_url: str) -> Dict[str, Any]:
    """Publish an entity homepage through the runtime API and return its id.

    Homepage detail/bundle reads come from the authoritative homepages
    collection, so we seed through the real candidate -> publish flow instead
    of writing private aggregate state directly. The published id resolves the
    `{homepageId}` template in the manifest verifiedEndpoints.

    introductionMarkdown/introductionAssets 与数据工程 page.md 三段结构同构
    （frontmatter 封面 / 正文章节 / 页尾相关图片），保证 introduction API 在
    gamma 走真实投影路径而非 generic fallback。
    """
    seed_intro_markdown = (
        "---\ncoverImage: asset://契约主页_cover_西湖全景_1_a1b2c3d4\n---\n\n"
        "# 契约主页验证\n\n## 概况\n\nlocal-gamma T3 introduction seed：真实三段结构正文。\n\n"
        "## 相关图片\n\n:::gallery\nasset://契约主页_detail_断桥残雪_1_b2c3d4e5\n:::\n"
    )
    seed_intro_assets = [
        {
            "assetId": "契约主页_cover_西湖全景_1_a1b2c3d4",
            "url": "https://media.quwoquan.invalid/media/objects/sha256/aa/bb/" + "a" * 64 + ".jpg",
            "caption": "西湖全景",
            "role": "cover",
        },
        {
            "assetId": "契约主页_detail_断桥残雪_1_b2c3d4e5",
            "url": "https://media.quwoquan.invalid/media/objects/sha256/cc/dd/" + "c" * 64 + ".jpg",
            "caption": "断桥残雪",
            "role": "related",
        },
    ]
    try:
        status, body = http_request(
            base_url.rstrip("/") + "/homepages/candidates",
            method="POST",
            body={
                "title": "契约主页验证",
                "subtitle": "local-gamma T3 entity seed",
                "homepageType": "sight",
                "city": "杭州",
                "introductionMarkdown": seed_intro_markdown,
                "introductionAssets": seed_intro_assets,
            },
            timeout=8,
        )
        resp = json.loads(body.decode("utf-8"))
        homepage_id = str(resp.get("_id") or resp.get("homepageId") or "").strip()
        if not homepage_id:
            return {"status": "failed", "httpStatus": status, "error": "candidate create returned no homepage id"}
        pub_status, _ = http_request(
            base_url.rstrip("/") + f"/homepages/candidates/{homepage_id}:publish",
            method="POST",
            timeout=8,
        )
        if not 200 <= pub_status < 300:
            return {"status": "failed", "httpStatus": pub_status, "error": "publish did not return 2xx"}
        return {"status": "passed", "homepageId": homepage_id}
    except urllib.error.HTTPError as exc:
        return {"status": "failed", "httpStatus": exc.code, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "error": str(exc)}


def seed_content() -> Dict[str, Any]:
    fixture_path, refs = gamma_content_fixture_spec()
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    docs_by_id: Dict[str, Dict[str, Any]] = {}
    for ref in refs:
        seed_set = fixture.get("seedSets", {}).get(ref)
        if not isinstance(seed_set, dict):
            continue
        for post in seed_set.get("posts", []) or []:
            doc = fixture_post_to_doc(post)
            docs_by_id[str(doc["_id"])] = doc
    docs = list(docs_by_id.values())
    js_path = GAMMA_RUN_ROOT / "seed-content.js"
    js_path.parent.mkdir(parents=True, exist_ok=True)
    js_path.write_text(
        """
const docs = %s;
const dateFields = ["createdAt", "updatedAt", "publishedAt", "lastActiveAt"];
for (const doc of docs) {
  for (const key of dateFields) {
    if (doc[key]) doc[key] = new Date(doc[key]);
  }
}
const dbh = db.getSiblingDB("quwoquan_content");
const ids = docs.map((doc) => doc._id);
const feedDocs = docs.map((doc) => ({
  postId: doc._id,
  authorId: doc.authorId || "",
  creatorProfileId: doc.subAccountId || doc.authorId || "",
  creatorDisclosure: {},
  experienceClaimMode: "",
  authorQualitySignals: {},
  contentType: doc.contentType || "",
  contentIdentity: doc.contentIdentity || "",
  title: doc.title || "",
  tagRefs: Array.isArray(doc.tags) ? doc.tags : [],
  coverUrl: doc.coverUrl || "",
  thumbnailUrl: doc.thumbnailUrl || "",
  videoUrl: doc.videoUrl || "",
  coverStrategy: "",
  coverFrameTimeMs: 0,
  durationMs: Number(doc.durationMs || 0),
  width: Number(doc.width || 0),
  height: Number(doc.height || 0),
  mediaItems: Array.isArray(doc.mediaItems) ? doc.mediaItems : [],
  status: "published",
  visibility: "public",
  assistantUsePolicy: doc.assistantUsePolicy || "allow",
  entityRefs: [],
  semanticMentions: null,
  contentVertical: "",
  sourceTaskId: "",
  conditionProfile: {},
  likeCount: Number(doc.likeCount || 0),
  commentCount: Number(doc.commentCount || 0),
  shareCount: Number(doc.shareCount || 0),
  viewCount: 0,
  createdAt: doc.createdAt,
  publishedAt: doc.publishedAt,
  updatedAt: doc.updatedAt,
}));
try {
  // The Gamma fixture set includes stable non-fixture IDs. Remove precisely
  // this execution's Posts and their derived feed rows before insertion so a
  // rerun is idempotent. The content seed writes both objects atomically at
  // the script level: a public Post without its rm_discovery_feed row makes
  // the comment-count relay retry forever and therefore breaks readiness.
  const deleted = ids.length > 0
    ? dbh.posts.deleteMany({_id: {$in: ids}})
    : {deletedCount: 0};
  const deletedFeed = ids.length > 0
    ? dbh.rm_discovery_feed.deleteMany({postId: {$in: ids}})
    : {deletedCount: 0};
  if (docs.length > 0) dbh.posts.insertMany(docs, {ordered: true});
  if (feedDocs.length > 0) dbh.rm_discovery_feed.insertMany(feedDocs, {ordered: true});
  const storedCount = ids.length > 0
    ? dbh.posts.countDocuments({_id: {$in: ids}})
    : 0;
  const storedFeedCount = ids.length > 0
    ? dbh.rm_discovery_feed.countDocuments({postId: {$in: ids}})
    : 0;
  if (storedCount !== docs.length) {
    throw new Error(`seed verification failed: stored ${storedCount}/${docs.length}`);
  }
  if (storedFeedCount !== feedDocs.length) {
    throw new Error(`feed seed verification failed: stored ${storedFeedCount}/${feedDocs.length}`);
  }
  printjson({
    insertedCount: docs.length,
    deletedCount: deleted.deletedCount || 0,
    storedCount,
    feedInsertedCount: feedDocs.length,
    feedDeletedCount: deletedFeed.deletedCount || 0,
    storedFeedCount,
  });
} catch (error) {
  print(error && error.stack ? error.stack : String(error));
  quit(1);
}
"""
        % json.dumps(docs, ensure_ascii=False),
        encoding="utf-8",
    )
    cmd = compose_command(
        "exec",
        "-T",
        "mongodb",
        "mongosh",
        "--quiet",
    )
    result = subprocess.run(
        cmd,
        input=js_path.read_text(encoding="utf-8"),
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=ROOT / "quwoquan_service",
        check=False,
    )
    return {
        "status": "passed" if result.returncode == 0 else "failed",
        "insertedCount": len(docs) if result.returncode == 0 else 0,
        "output": result.stdout[-2000:],
    }


def seed_content_social_graph(viewer_id: str) -> Dict[str, Any]:
    viewer_id = viewer_id.strip()
    if not viewer_id:
        return {"status": "failed", "error": "authenticated persona id is required"}
    report_path = GAMMA_RUN_ROOT / "content_social_graph_seed_report.json"
    cmd = [
        "python3",
        "quwoquan_service/services/seed-box/scripts/apply_content_social_graph_seed.py",
        "--container",
        "quwoquan_service-mongodb-1",
        "--db",
        "quwoquan_content",
        "--report",
        str(report_path),
        "--viewer-id",
        viewer_id,
    ]
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    payload: Dict[str, Any] = {
        "status": "passed" if result.returncode == 0 else "failed",
        "output": result.stdout[-2000:],
        "report": str(report_path.relative_to(ROOT)),
    }
    if report_path.exists():
        try:
            payload["applied"] = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            payload["applied"] = {"status": "unparseable"}
    return payload


def seed_content_object_cards(viewer_id: str) -> Dict[str, Any]:
    """N2-2：应用混合对象卡（entity_homepage）验收种子（亲和/想去/实体档案/homepage 锚点）。"""
    viewer_id = viewer_id.strip()
    if not viewer_id:
        return {"status": "failed", "error": "authenticated persona id is required"}
    report_path = GAMMA_RUN_ROOT / "content_object_cards_seed_report.json"
    cmd = [
        "python3",
        "quwoquan_service/services/seed-box/scripts/apply_content_object_cards_seed.py",
        "--container",
        "quwoquan_service-mongodb-1",
        "--db",
        "quwoquan_content",
        "--report",
        str(report_path),
        "--viewer-id",
        viewer_id,
    ]
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    payload: Dict[str, Any] = {
        "status": "passed" if result.returncode == 0 else "failed",
        "output": result.stdout[-2000:],
        "report": str(report_path.relative_to(ROOT)),
    }
    if report_path.exists():
        try:
            payload["applied"] = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            payload["applied"] = {"status": "unparseable"}
    return payload


def seed_content_moment_channel() -> Dict[str, Any]:
    """应用 manifest supplementary fixture，保证推荐频道有新鲜可召回内容。"""
    report_path = GAMMA_RUN_ROOT / "content_moment_channel_seed_report.json"
    cmd = [
        "python3",
        "quwoquan_service/services/seed-box/scripts/apply_content_moment_channel_seed.py",
        "--container",
        "quwoquan_service-mongodb-1",
        "--redis-container",
        "quwoquan_service-redis-1",
        "--db",
        "quwoquan_content",
        "--report",
        str(report_path),
    ]
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    payload: Dict[str, Any] = {
        "status": "passed" if result.returncode == 0 else "failed",
        "output": result.stdout[-2000:],
        "report": str(report_path.relative_to(ROOT)),
    }
    if report_path.exists():
        try:
            payload["applied"] = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            payload["applied"] = {"status": "unparseable"}
    return payload


def setup_comment_thread(base_url: str) -> Dict[str, Any]:
    """Create runtime-only comment fixtures through the public API.

    Posts are fixture-seeded read data, while Comments remain content-service
    aggregate state. Creating the thread through the generated public contract
    exercises Comment persistence, outbox and projections instead of writing
    Mongo documents behind the service boundary.
    """
    try:
        status, body = http_request(
            base_url.rstrip() + "/content/posts/fixture_photo_001/comments",
            method="POST",
            body={"content": "主评论示例"},
            timeout=8,
            headers={"Idempotency-Key": gamma_probe_idempotency_key("comment-parent")},
        )
        parent_resp = json.loads(body.decode("utf-8"))
        parent_id = str(parent_resp.get("id") or "").strip()
        if not parent_id:
            return {
                "status": "failed",
                "httpStatus": status,
                "error": "CreateComment did not return parent comment id",
            }
        reply_status, reply_body = http_request(
            base_url.rstrip() + "/content/posts/fixture_photo_001/comments",
            method="POST",
            body={"content": "回复示例", "replyToCommentId": parent_id},
            timeout=8,
            headers={"Idempotency-Key": gamma_probe_idempotency_key("comment-reply")},
        )
        reply_resp = json.loads(reply_body.decode("utf-8"))
        reply_id = str(reply_resp.get("id") or "").strip()
        if not reply_id:
            return {
                "status": "failed",
                "httpStatus": reply_status,
                "error": "CreateComment did not return reply comment id",
            }
        reaction_status, _ = http_request(
            base_url.rstrip() + f"/content/comments/{parent_id}/reaction",
            method="POST",
            body={"reaction": "like"},
            timeout=8,
            headers={"Idempotency-Key": gamma_probe_idempotency_key("comment-reaction")},
        )
        bind_status, bind_body = http_request(
            base_url.rstrip() + f"/content/comments/{parent_id}/media:bind",
            method="POST",
            body={"attachmentMediaIds": []},
            timeout=8,
            headers={"Idempotency-Key": gamma_probe_idempotency_key("comment-media-bind")},
        )
        bind_resp = json.loads(bind_body.decode("utf-8"))
        return {
            "status": "passed",
            "parentCommentId": parent_id,
            "replyCommentId": reply_id,
            "reaction": {"status": "passed", "httpStatus": reaction_status},
            "mediaBind": {
                "status": "passed",
                "httpStatus": bind_status,
                "version": int(bind_resp.get("version") or 0),
            },
        }
    except urllib.error.HTTPError as exc:
        error_body = exc.read()
        error_code = ""
        try:
            payload = json.loads(error_body.decode("utf-8"))
            error_code = str(payload.get("code") or "").strip()
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        return {
            "status": "failed",
            "httpStatus": exc.code,
            "error": str(exc),
            "errorCode": error_code,
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "error": str(exc)}


def setup_runtime_fixtures(base_url: str, viewer_id: str) -> Dict[str, Any]:
    comment = setup_comment_thread(base_url)
    moment_channel = seed_content_moment_channel()
    social_graph = seed_content_social_graph(viewer_id)
    object_cards = seed_content_object_cards(viewer_id)
    status = "passed"
    if (
        comment.get("status") == "failed"
        or moment_channel.get("status") == "failed"
        or social_graph.get("status") == "failed"
        or object_cards.get("status") == "failed"
    ):
        status = "failed"
    return {
        "status": status,
        "parentCommentId": comment.get("parentCommentId", ""),
        "replyCommentId": comment.get("replyCommentId", ""),
        "commentThread": comment,
        "momentChannelSeed": moment_channel,
        "socialGraphSeed": social_graph,
        "objectCardsSeed": object_cards,
    }


def content_route_methods() -> Dict[str, List[str]]:
    methods: Dict[str, List[str]] = {}
    graph = json.loads(CONTRACT_GRAPH.read_text(encoding="utf-8"))
    for operation in graph.get("operations", []):
        if operation.get("domain") != "content":
            continue
        path = str(operation.get("pathTemplate") or "").strip()
        method = str(operation.get("method") or "").strip().upper()
        if not path or not method:
            continue
        methods.setdefault(path, [])
        if method not in methods[path]:
            methods[path].append(method)
    return methods


def operation_contract_for_path(
    domain: str,
    path: str,
    method: str,
) -> Optional[Dict[str, Any]]:
    graph = json.loads(CONTRACT_GRAPH.read_text(encoding="utf-8"))
    probe_path = path.split("?", 1)[0]
    for operation in graph.get("operations", []):
        if str(operation.get("domain") or "").strip() != domain:
            continue
        if str(operation.get("method") or "").strip().upper() != method.upper():
            continue
        template = str(operation.get("pathTemplate") or "").strip()
        if not template:
            continue
        template_parts = template.strip("/").split("/")
        probe_parts = probe_path.strip("/").split("/")
        if len(template_parts) != len(probe_parts):
            continue
        if all(
            (left.startswith("{") and left.endswith("}")) or left == right
            for left, right in zip(template_parts, probe_parts)
        ):
            return operation
    return None


def endpoint_contract_summary(domain: str, path: str, method: str) -> Dict[str, str]:
    operation = operation_contract_for_path(domain, path, method)
    if operation is None:
        return {}
    commercial = operation.get("commercial")
    if not isinstance(commercial, dict):
        commercial = {}
    return {
        "operationId": str(operation.get("id") or "").strip(),
        "method": str(operation.get("method") or "GET").strip().upper(),
        "authMode": str(operation.get("authMode") or "").strip(),
        "commercialStatus": str(commercial.get("status") or "").strip(),
    }


def route_method_for_path(path: str, route_methods: Dict[str, List[str]]) -> str:
    probe_path = path.split("?", 1)[0]
    for template, methods in route_methods.items():
        template_parts = template.strip("/").split("/")
        probe_parts = probe_path.strip("/").split("/")
        if len(template_parts) != len(probe_parts):
            continue
        matched = True
        for left, right in zip(template_parts, probe_parts):
            if left.startswith("{") and left.endswith("}"):
                continue
            if left != right:
                matched = False
                break
        if matched:
            if "GET" in methods:
                return "GET"
            if "POST" in methods:
                return "POST"
            return methods[0] if methods else "GET"
    return "GET"


def item_verification_scopes(item: Dict[str, Any]) -> Set[str]:
    raw = item.get("verificationScopes", [])
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return set()
    return {str(scope).strip() for scope in raw if str(scope).strip()}


def resolve_verification_scope(
    manifest: Dict[str, Any],
    scope_name: str,
) -> Optional[Dict[str, Any]]:
    scopes = manifest.get("verificationScopes", {})
    if not isinstance(scopes, dict):
        return None
    scope = scopes.get(scope_name)
    return scope if isinstance(scope, dict) else None


def item_in_scope(
    item: Dict[str, Any],
    scope_name: Optional[str],
    scope: Optional[Dict[str, Any]],
) -> bool:
    if not scope_name or scope is None:
        return True
    scopes = item_verification_scopes(item)
    if scope_name in scopes:
        return True
    scope_domains = {
        str(domain).strip()
        for domain in scope.get("domains", [])
        if str(domain).strip()
    }
    return str(item.get("domain") or "").strip() in scope_domains


def scope_runtime_refs(
    scope: Optional[Dict[str, Any]],
    runtime_refs: Dict[str, str],
) -> Dict[str, str]:
    merged = dict(runtime_refs)
    if scope is None:
        return merged
    scope_refs = scope.get("runtimeRefs", {})
    if isinstance(scope_refs, dict):
        for key, value in scope_refs.items():
            placeholder = str(key).strip()
            ref_value = str(value).strip()
            if placeholder and ref_value:
                merged[placeholder] = ref_value
    return merged


def resolve_probe_path(path: str, runtime_refs: Dict[str, str]) -> str:
    resolved = path
    for fixture_id, runtime_id in runtime_refs.items():
        if runtime_id:
            resolved = resolved.replace(fixture_id, runtime_id)
    return resolved


def probe_body_for_path(path: str) -> Dict[str, Any]:
    return {}


def parse_json_body(body: bytes, path: str) -> Any:
    try:
        return json.loads(body.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(f"{path} returned non-JSON body: {exc}") from exc


def expect_dict(value: Any, label: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise AssertionError(f"{label} must be object, got {type(value).__name__}")
    return value


def expect_list(value: Any, label: str) -> List[Any]:
    if not isinstance(value, list):
        raise AssertionError(f"{label} must be array, got {type(value).__name__}")
    return value


def expect_non_empty_string(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise AssertionError(f"{label} must be non-empty string")
    return text


def target_object_type(target: Dict[str, Any]) -> str:
    return str(target.get("objectType") or "").strip()


def target_object_id(target: Dict[str, Any]) -> str:
    return str(target.get("objectId") or "").strip()


def allowed_display_object_target(target: Dict[str, Any]) -> bool:
    return target_object_type(target) in DISPLAY_OBJECT_TARGET_TYPES and bool(target_object_id(target))


def display_statement_needs_representative(reason: Dict[str, Any], primary_text: str) -> bool:
    actor_total = reason.get("actorEvidenceTotalCount")
    if isinstance(actor_total, int) and actor_total > 1:
        return True
    actor_evidence = reason.get("actorEvidence")
    if isinstance(actor_evidence, list) and len(actor_evidence) > 1:
        return True
    return "等" in primary_text or COUNT_SUBJECT_RE.search(primary_text) is not None


def has_meaningful_representative_actor(reason: Dict[str, Any]) -> bool:
    actor = reason.get("representativeActor")
    if not isinstance(actor, dict):
        return False
    display_name = str(actor.get("displayName") or "").strip()
    if not display_name or display_name == "用户" or display_name.startswith("一位"):
        return False
    relation_label = str(actor.get("relationLabel") or "").strip()
    if not relation_label or relation_label in {"相关用户", "其他用户", "用户"}:
        return False
    target = actor.get("target")
    if not isinstance(target, dict):
        return False
    return target_object_type(target) == "user" and bool(target_object_id(target))


def assert_display_statement_text_allowed(
    reason: Dict[str, Any],
    label: str,
    primary_text: str,
) -> None:
    if RAW_INTERACTION_STATS_RE.search(primary_text):
        raise AssertionError(f"{label}.primaryText must not expose raw interaction stats")
    for fragment in DISPLAY_STATEMENT_BANNED_FRAGMENTS:
        if fragment in primary_text:
            raise AssertionError(f"{label}.primaryText contains banned vague fragment: {fragment}")
    if display_statement_needs_representative(reason, primary_text) and not has_meaningful_representative_actor(reason):
        raise AssertionError(
            f"{label}.representativeActor must name a relationship-qualified user for count/equivalent subjects"
        )


def assert_action_hint_contract(
    reason: Dict[str, Any],
    hint: Dict[str, Any],
    label: str,
) -> None:
    action_key = expect_non_empty_string(hint.get("actionKey"), f"{label}.actionKey")
    target = hint.get("target")
    if target is not None:
        target_map = expect_dict(target, f"{label}.target")
        if not allowed_display_object_target(target_map):
            raise AssertionError(f"{label}.target must be a typed, routable object")
    if action_key != "start_companion":
        return
    kind = str(reason.get("kind") or reason.get("source") or "").strip()
    if kind != "coWishlistedEntity":
        raise AssertionError(f"{label}.start_companion must be bound to coWishlistedEntity evidence")
    if str(hint.get("dispatch") or "").strip() != "companion":
        raise AssertionError(f"{label}.start_companion dispatch must equal companion")
    if str(hint.get("targetAvailability") or "available").strip() != "available":
        raise AssertionError(f"{label}.start_companion targetAvailability must be available")
    if target is None:
        raise AssertionError(f"{label}.start_companion must carry a target")
    action_target_id = str(reason.get("actionTargetId") or "").strip()
    if action_target_id and target_object_id(expect_dict(target, f"{label}.target")) != action_target_id:
        raise AssertionError(f"{label}.start_companion target must match actionTargetId")


def assert_reason_primary_contract(reason: Dict[str, Any], label: str) -> None:
    primary_text = expect_non_empty_string(reason.get("primaryText"), f"{label}.primaryText")
    assert_display_statement_text_allowed(reason, label, primary_text)
    spans = expect_list(reason.get("primarySpans"), f"{label}.primarySpans")
    if not spans:
        raise AssertionError(f"{label}.primarySpans must be non-empty")
    span_texts = []
    has_object_target = False
    action_target_id = str(reason.get("actionTargetId") or "").strip()
    for idx, span in enumerate(spans):
        span_map = expect_dict(span, f"{label}.primarySpans[{idx}]")
        span_texts.append(
            expect_non_empty_string(
                span_map.get("text"),
                f"{label}.primarySpans[{idx}].text",
            )
        )
        role = str(span_map.get("role") or "plain").strip()
        target = span_map.get("target")
        if target is not None:
            target_map = expect_dict(target, f"{label}.primarySpans[{idx}].target")
            expect_non_empty_string(
                target_map.get("objectType"),
                f"{label}.primarySpans[{idx}].target.objectType",
            )
            expect_non_empty_string(
                target_map.get("objectId"),
                f"{label}.primarySpans[{idx}].target.objectId",
            )
            if role == "count":
                if str(reason.get("actorEvidenceCompleteness") or "").strip() != "complete":
                    raise AssertionError(
                        f"{label}.primarySpans[{idx}].count target requires complete actorEvidence"
                    )
                if str(target_map.get("routeId") or "").strip() != "myIntersections":
                    raise AssertionError(f"{label}.primarySpans[{idx}].count target must route to myIntersections")
            if role == "object":
                if not allowed_display_object_target(target_map):
                    raise AssertionError(f"{label}.primarySpans[{idx}].object target must be typed and routable")
                if not action_target_id or target_object_id(target_map) == action_target_id:
                    has_object_target = True
    if "".join(span_texts) != primary_text:
        raise AssertionError(f"{label}.primarySpans text does not join back to primaryText")
    if not has_object_target:
        raise AssertionError(f"{label}.primarySpans must include an object span bound to actionTargetId")
    action_hints = reason.get("actionHints")
    if action_hints is not None:
        hints = expect_list(action_hints, f"{label}.actionHints")
        for idx, hint in enumerate(hints):
            hint_map = expect_dict(hint, f"{label}.actionHints[{idx}]")
            assert_action_hint_contract(reason, hint_map, f"{label}.actionHints[{idx}]")


def assert_entity_homepage_bundle(payload: Any, _: Dict[str, Any]) -> None:
    bundle = expect_dict(payload, "entity_homepage_bundle")
    if expect_non_empty_string(bundle.get("objectType"), "entity_homepage_bundle.objectType") != "homepage":
        raise AssertionError("entity_homepage_bundle.objectType must equal homepage")
    expect_non_empty_string(bundle.get("objectId"), "entity_homepage_bundle.objectId")
    reasons = expect_list(bundle.get("intersectionReasons"), "entity_homepage_bundle.intersectionReasons")
    if not reasons:
        raise AssertionError("entity_homepage_bundle.intersectionReasons must be non-empty")
    highlight_items = expect_list(bundle.get("highlightItems"), "entity_homepage_bundle.highlightItems")
    if not highlight_items:
        raise AssertionError("entity_homepage_bundle.highlightItems must be non-empty")
    related_objects = expect_list(bundle.get("relatedObjects"), "entity_homepage_bundle.relatedObjects")
    if not related_objects:
        raise AssertionError("entity_homepage_bundle.relatedObjects must be non-empty")
    for idx, reason in enumerate(reasons):
        assert_reason_primary_contract(
            expect_dict(reason, f"entity_homepage_bundle.intersectionReasons[{idx}]"),
            f"entity_homepage_bundle.intersectionReasons[{idx}]",
        )


def assert_homepage_introduction(payload: Any, _: Dict[str, Any]) -> None:
    intro = expect_dict(payload, "homepage_introduction")
    expect_non_empty_string(intro.get("homepageId"), "homepage_introduction.homepageId")
    sections = expect_list(intro.get("sections"), "homepage_introduction.sections")
    if not sections:
        raise AssertionError("homepage_introduction.sections must be non-empty")
    # seed 带 introductionMarkdown（三段结构），introduction 必须走真实投影：
    # 正文来自 seed 底稿而非 generic fallback，且页尾相关图片小节可见。
    bodies = " ".join(str(section.get("bodyMarkdown") or "") for section in sections if isinstance(section, dict))
    if "introduction seed" not in bodies:
        raise AssertionError("homepage_introduction must project seeded page markdown, not generic fallback")
    related = [
        section for section in sections
        if isinstance(section, dict) and section.get("kind") == "relatedImages" and section.get("assets")
    ]
    if not related:
        raise AssertionError("homepage_introduction must expose relatedImages section from seeded assets")


def assert_homepage_review_summary(payload: Any, _: Dict[str, Any]) -> None:
    review = expect_dict(payload, "homepage_review_summary")
    if not isinstance(review.get("ratingCount"), int):
        raise AssertionError("homepage_review_summary.ratingCount must be int")
    scores = expect_list(review.get("dimensionScores"), "homepage_review_summary.dimensionScores")
    if not scores:
        raise AssertionError("homepage_review_summary.dimensionScores must be non-empty")


def assert_homepage_related_groups(payload: Any, _: Dict[str, Any]) -> None:
    groups_payload = expect_dict(payload, "homepage_related_groups")
    groups = expect_list(groups_payload.get("groups"), "homepage_related_groups.groups")
    if not groups:
        raise AssertionError("homepage_related_groups.groups must be non-empty")
    first = expect_dict(groups[0], "homepage_related_groups.groups[0]")
    expect_non_empty_string(first.get("circleId"), "homepage_related_groups.groups[0].circleId")
    expect_non_empty_string(first.get("name"), "homepage_related_groups.groups[0].name")


def assert_entity_impact_summary(payload: Any, _: Dict[str, Any]) -> None:
    impact = expect_dict(payload, "entity_impact_summary")
    expect_non_empty_string(impact.get("homepageId"), "entity_impact_summary.homepageId")
    items = expect_list(impact.get("items"), "entity_impact_summary.items")
    if not items:
        raise AssertionError("entity_impact_summary.items must be non-empty")
    for idx, item in enumerate(items):
        assert_reason_primary_contract(
            expect_dict(item, f"entity_impact_summary.items[{idx}]"),
            f"entity_impact_summary.items[{idx}]",
        )


def unwrap_data(payload: Any, label: str) -> Dict[str, Any]:
    outer = expect_dict(payload, label)
    if "data" in outer:
        return expect_dict(outer.get("data"), f"{label}.data")
    return outer


def assert_circle_detail(payload: Any, _: Dict[str, Any]) -> None:
    detail = unwrap_data(payload, "circle_detail")
    expect_non_empty_string(detail.get("_id") or detail.get("circleId"), "circle_detail.circleId")
    expect_non_empty_string(detail.get("name"), "circle_detail.name")
    if not isinstance(detail.get("memberCount"), int) or detail.get("memberCount", 0) <= 0:
        raise AssertionError("circle_detail.memberCount must be positive int")


def assert_circle_impact_summary(payload: Any, _: Dict[str, Any]) -> None:
    impact = unwrap_data(payload, "circle_impact_summary")
    expect_non_empty_string(impact.get("circleId"), "circle_impact_summary.circleId")
    items = expect_list(impact.get("items"), "circle_impact_summary.items")
    if not items:
        raise AssertionError("circle_impact_summary.items must be non-empty")
    for idx, item in enumerate(items):
        assert_reason_primary_contract(
            expect_dict(item, f"circle_impact_summary.items[{idx}]"),
            f"circle_impact_summary.items[{idx}]",
        )


def assert_circle_members_page(payload: Any, _: Dict[str, Any]) -> None:
    page = expect_dict(payload, "circle_members_page")
    items = expect_list(page.get("items"), "circle_members_page.items")
    if not items:
        raise AssertionError("circle_members_page.items must be non-empty")
    first = expect_dict(items[0], "circle_members_page.items[0]")
    expect_non_empty_string(first.get("userId"), "circle_members_page.items[0].userId")
    expect_non_empty_string(first.get("role"), "circle_members_page.items[0].role")


def assert_home_feed_object_cards(payload: Any, _: Dict[str, Any]) -> None:
    """N2-2：gamma-local 开启 objectCards 后，首页 recommend feed envelope 必须
    注入可点的 entity_homepage 卡（策略 everyN 锚点 + homepageId 可路由）。"""
    page = expect_dict(payload, "home_feed")
    items = expect_list(page.get("items"), "home_feed.items")
    if not items:
        raise AssertionError("home_feed.items must be non-empty before object cards can anchor")
    cards = expect_list(page.get("objectCards"), "home_feed.objectCards")
    if not cards:
        raise AssertionError(
            "home_feed.objectCards must be non-empty (policy overlay enabled + object cards seed applied)"
        )
    for index, raw in enumerate(cards):
        card = expect_dict(raw, f"home_feed.objectCards[{index}]")
        if card.get("objectKind") != "entity_homepage":
            raise AssertionError(
                f"objectCards[{index}].objectKind must be entity_homepage, got {card.get('objectKind')!r}"
            )
        expect_non_empty_string(card.get("objectId"), f"objectCards[{index}].objectId")
        expect_non_empty_string(card.get("title"), f"objectCards[{index}].title")
        anchor = card.get("anchorIndex")
        if not isinstance(anchor, int) or anchor <= 0:
            raise AssertionError(f"objectCards[{index}].anchorIndex must be positive, got {anchor!r}")


def assert_circle_feed_page(payload: Any, _: Dict[str, Any]) -> None:
    page = expect_dict(payload, "circle_feed_page")
    items = expect_list(page.get("items"), "circle_feed_page.items")
    if not items:
        raise AssertionError("circle_feed_page.items must be non-empty")
    first = expect_dict(items[0], "circle_feed_page.items[0]")
    expect_non_empty_string(first.get("postId") or first.get("id"), "circle_feed_page.items[0].postId")
    expect_non_empty_string(first.get("contentType"), "circle_feed_page.items[0].contentType")


def assert_object_intersections(payload: Any, spec: Dict[str, Any]) -> None:
    page = expect_dict(payload, "object_intersections")
    expected_type = str(spec.get("expectedObjectType") or "").strip()
    if expected_type:
        if expect_non_empty_string(page.get("objectType"), "object_intersections.objectType") != expected_type:
            raise AssertionError(f"object_intersections.objectType must equal {expected_type}")
    expect_non_empty_string(page.get("objectId"), "object_intersections.objectId")
    items = expect_list(page.get("items"), "object_intersections.items")
    if not items:
        raise AssertionError("object_intersections.items must be non-empty")
    for idx, item in enumerate(items):
        assert_reason_primary_contract(
            expect_dict(item, f"object_intersections.items[{idx}]"),
            f"object_intersections.items[{idx}]",
        )


STRICT_ASSERTIONS = {
    "entity_homepage_bundle": assert_entity_homepage_bundle,
    "homepage_introduction": assert_homepage_introduction,
    "homepage_review_summary": assert_homepage_review_summary,
    "homepage_related_groups": assert_homepage_related_groups,
    "entity_impact_summary": assert_entity_impact_summary,
    "circle_detail": assert_circle_detail,
    "circle_impact_summary": assert_circle_impact_summary,
    "circle_members_page": assert_circle_members_page,
    "circle_feed_page": assert_circle_feed_page,
    "home_feed_object_cards": assert_home_feed_object_cards,
    "object_intersections_homepage": assert_object_intersections,
    "object_intersections_circle": assert_object_intersections,
}


def endpoint_checks(
    manifest: Dict[str, Any],
    base_url: str,
    enabled_domains: Set[str],
    runtime_refs: Dict[str, str],
    *,
    scope_name: Optional[str] = None,
    scope: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    route_methods = content_route_methods()
    resolved_refs = scope_runtime_refs(scope, runtime_refs)
    checks = []  # type: List[Dict[str, Any]]
    for item in manifest.get("seedRefs", []):
        domain = item.get("domain", "")
        for path in item.get("verifiedEndpoints", []):
            check = {"domain": domain, "path": path}  # type: Dict[str, Any]
            if not item_in_scope(item, scope_name, scope):
                check["status"] = "out_of_scope"
                checks.append(check)
                continue
            if domain not in enabled_domains:
                check["status"] = "not_ready"
                checks.append(check)
                continue
            # entity verifiedEndpoints carry a `{homepageId}` template resolved from
            # the runtime publish seed; content carries comment-id refs. Both resolve
            # via runtime_refs; circle/chat paths have no refs and pass through.
            resolved_path = resolve_probe_path(path, resolved_refs)
            method = route_method_for_path(resolved_path, route_methods) if domain == "content" else "GET"
            contract = endpoint_contract_summary(domain, resolved_path, method)
            check.update({key: value for key, value in contract.items() if value})
            method = contract.get("method") or method
            check["method"] = method
            if resolved_path != path:
                check["resolvedPath"] = resolved_path
            try:
                if method == "GET":
                    status, body = http_get(base_url.rstrip("/") + resolved_path, timeout=8)
                else:
                    status, body = http_request(
                        base_url.rstrip("/") + resolved_path,
                        method=method,
                        body=probe_body_for_path(resolved_path),
                        timeout=8,
                    )
                check["httpStatus"] = status
                check["bytes"] = len(body)
                if contract.get("commercialStatus") == "blocked":
                    check["status"] = "failed"
                    check["error"] = "blocked operation unexpectedly accepted the request"
                else:
                    check["status"] = "passed" if 200 <= status < 300 else "failed"
            except urllib.error.HTTPError as exc:
                check["httpStatus"] = exc.code
                if contract.get("commercialStatus") == "blocked" and exc.code == 403:
                    check["status"] = "contract_blocked"
                    check["expectedHttpStatus"] = 403
                else:
                    check["status"] = "failed"
                    check["error"] = str(exc)
            except Exception as exc:  # noqa: BLE001
                check["status"] = "failed"
                check["error"] = str(exc)
            checks.append(check)
    return checks


def strict_endpoint_checks(
    base_url: str,
    runtime_refs: Dict[str, str],
    scope: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if scope is None:
        return []
    checks: List[Dict[str, Any]] = []
    resolved_refs = scope_runtime_refs(scope, runtime_refs)
    strict_endpoints = scope.get("strictEndpoints", [])
    if not isinstance(strict_endpoints, list):
        return checks
    for spec in strict_endpoints:
        if not isinstance(spec, dict):
            continue
        path = str(spec.get("path") or "").strip()
        if not path:
            continue
        assertion_name = str(spec.get("assertion") or "").strip()
        check: Dict[str, Any] = {
            "domain": str(spec.get("domain") or "").strip(),
            "path": path,
            "assertion": assertion_name,
        }
        resolved_path = resolve_probe_path(path, resolved_refs)
        if resolved_path != path:
            check["resolvedPath"] = resolved_path
        if assertion_name == "object_intersections_homepage":
            spec = {**spec, "expectedObjectType": "homepage"}
        elif assertion_name == "object_intersections_circle":
            spec = {**spec, "expectedObjectType": "circle"}
        method = str(spec.get("method") or "GET").upper()
        contract = endpoint_contract_summary(check["domain"], resolved_path, method)
        check.update({key: value for key, value in contract.items() if value})
        method = contract.get("method") or method
        try:
            if method == "GET":
                status, body = http_get(base_url.rstrip("/") + resolved_path, timeout=8)
            else:
                status, body = http_request(
                    base_url.rstrip("/") + resolved_path,
                    method=method,
                    body=spec.get("body") if isinstance(spec.get("body"), dict) else None,
                    timeout=8,
                )
            check["method"] = method
            check["httpStatus"] = status
            check["bytes"] = len(body)
            if not 200 <= status < 300:
                raise AssertionError(f"{resolved_path} returned http {status}")
            assertion = STRICT_ASSERTIONS.get(assertion_name)
            if assertion is None:
                raise AssertionError(f"unknown strict assertion: {assertion_name}")
            assertion(parse_json_body(body, resolved_path), spec)
            check["status"] = "passed"
        except urllib.error.HTTPError as exc:
            check["httpStatus"] = exc.code
            if contract.get("commercialStatus") == "blocked" and exc.code == 403:
                check["status"] = "contract_blocked"
                check["expectedHttpStatus"] = 403
            else:
                check["status"] = "failed"
                check["error"] = str(exc)
        except AssertionError as exc:
            check["status"] = "failed"
            check["error"] = str(exc)
        except Exception as exc:  # noqa: BLE001
            check["status"] = "failed"
            check["error"] = str(exc)
        checks.append(check)
    return checks


def run_flutter_contracts(
    base_url: str,
    product_ops_base_url: str,
    enabled_domains: Set[str],
    *,
    include_product_ops: bool,
) -> List[Dict[str, Any]]:
    checks = []  # type: List[Dict[str, Any]]
    flutter_base_url = flutter_contract_base_url(base_url)
    flutter_product_ops_base_url = flutter_contract_base_url(product_ops_base_url)
    cases = [
        {
            "name": "content_api_contract",
            "domain": "content",
            "path": "test/api_integration/cloud/content/api_contract_runner.dart",
            "defines": [
                "--dart-define=API_CONTRACT_ENV=gamma",
                f"--dart-define=API_CONTRACT_BASE_URL={flutter_base_url}",
                "--dart-define=LOCAL_GAMMA_T3_SCOPE=content",
                "--dart-define=API_CONTRACT_ALLOW_BAD_CERT=true",
            ],
        },
        {
            "name": "chat_api_contract",
            "domain": "chat",
            "path": "test/api_integration/cloud/chat/api_contract_runner.dart",
            "defines": [
                "--dart-define=API_CONTRACT_ENV=gamma",
                f"--dart-define=API_CONTRACT_BASE_URL={flutter_base_url}",
                "--dart-define=API_CONTRACT_ALLOW_BAD_CERT=true",
            ],
        },
        {
            "name": "user_identity_api_contract",
            "domain": "user",
            "path": "test/api_integration/cloud/user/user_api_contract_runner.dart",
            "defines": [
                "--dart-define=API_CONTRACT_ENV=gamma",
                f"--dart-define=API_CONTRACT_BASE_URL={flutter_base_url}",
                "--dart-define=API_CONTRACT_ALLOW_BAD_CERT=true",
            ],
        },
        {
            "name": "product_ops_api_contract",
            "domain": "product_ops",
            "path": "test/api_integration/cloud/ops/api_contract_runner.dart",
            "defines": [
                "--dart-define=API_CONTRACT_ENV=gamma",
                f"--dart-define=API_CONTRACT_PRODUCT_OPS_BASE_URL={flutter_product_ops_base_url}",
                f"--dart-define=API_CONTRACT_AUTH_BASE_URL={flutter_base_url}",
                "--dart-define=API_CONTRACT_ALLOW_BAD_CERT=true",
            ],
        },
    ]
    for case in cases:
        if case["domain"] == "product_ops":
            if not include_product_ops:
                continue
        elif case["domain"] not in enabled_domains:
            continue
        if case["name"] == "chat_api_contract":
            chat_inbox = endpoint_contract_summary("chat", "/chat/inbox", "GET")
            if chat_inbox.get("commercialStatus") == "blocked":
                checks.append(
                    {
                        "name": case["name"],
                        "status": "contract_blocked",
                        "operationId": chat_inbox.get("operationId", ""),
                        "commercialStatus": "blocked",
                        "evidence": "endpoint_checks requires metadata-enforced HTTP 403",
                    }
                )
                continue
        cmd = ["flutter", "test", case["path"], *case["defines"]]
        result = subprocess.run(
            cmd,
            cwd=ROOT / "quwoquan_app",
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        checks.append(
            {
                "name": case["name"],
                "status": "passed" if result.returncode == 0 else "failed",
                "exitCode": result.returncode,
                "output": result.stdout[-4000:],
            }
        )
    return checks


def main() -> int:
    global _ACTIVE_SESSION
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "LOCAL_GAMMA_GATEWAY_BASE_URL",
            "https://gamma-api.quwoquan-env.test:19000",
        ),
    )
    parser.add_argument(
        "--product-ops-base-url",
        default=os.environ.get(
            "LOCAL_GAMMA_PRODUCT_OPS_BASE_URL",
            "https://gamma-product-ops.quwoquan-env.test:19010",
        ),
    )
    parser.add_argument("--report", default=str(GAMMA_RUN_ROOT / "t3_report.json"))
    parser.add_argument(
        "--enabled-domain",
        action="append",
        default=None,
    )
    parser.add_argument("--skip-seed", action="store_true")
    parser.add_argument(
        "--seed-only",
        action="store_true",
        help=(
            "Seed content plus the authenticated user-profile prerequisite "
            "(no health wait or Flutter contracts)."
        ),
    )
    parser.add_argument("--skip-flutter-contracts", action="store_true")
    parser.add_argument("--strict-all", action="store_true")
    parser.add_argument(
        "--verification-scope",
        default="",
        help="Only strict-gate the selected manifest verification scope.",
    )
    parser.add_argument("--wait-seconds", type=int, default=45)
    args = parser.parse_args()

    enabled_domain_scope_selected = args.enabled_domain is not None
    enabled_domains = set(args.enabled_domain or DEFAULT_ENABLED_DOMAINS)
    manifest = load_manifest()
    scope_name = args.verification_scope.strip()
    scope = resolve_verification_scope(manifest, scope_name) if scope_name else None
    report = {  # type: Dict[str, Any]
        "status": "running",
        "baseUrl": args.base_url,
        "productOpsBaseUrl": args.product_ops_base_url,
        "enabledDomains": sorted(enabled_domains),
        "verificationScope": scope_name,
        "health": {},
        "productOpsHealth": {},
        "auth": {},
        "seed": {},
        "domainSeeds": {},
        "runtimeSetup": {},
        "endpoints": [],
        "strictEndpoints": [],
        "apiContracts": [],
    }

    if scope_name and scope is None:
        report["status"] = "failed"
        report["strictEndpoints"] = [
            {
                "scope": scope_name,
                "status": "failed",
                "error": "verification scope not found in app_gamma_seed_manifest.json",
            }
        ]
        report_path = ROOT / args.report
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[local-gamma:t3] report: {report_path}")
        print(f"[local-gamma:t3] status: {report['status']}")
        return 1

    if args.seed_only:
        report["seed"] = seed_content()
        # Gamma's environment health probe authenticates as the canonical
        # acceptance principal and calls /user/sync. Seed its typed profile
        # before reporting startup success; otherwise the proxy is healthy
        # while the authenticated B1 path fails with USER.USER.not_found.
        if (
            report["seed"].get("status") == "passed"
            and "user" in enabled_domains
        ):
            report["domainSeeds"]["user"] = seed_user()
        user_seed_failed = (
            report["domainSeeds"].get("user", {}).get("status") == "failed"
        )
        report["status"] = (
            "passed"
            if report["seed"].get("status") == "passed" and not user_seed_failed
            else "failed"
        )
    else:
        report["health"] = wait_url(args.base_url.rstrip("/") + "/healthz", args.wait_seconds)
        report["productOpsHealth"] = (
            {"status": "skipped", "reason": "domain_scoped_verification"}
            if enabled_domain_scope_selected
            else wait_url(
                args.product_ops_base_url.rstrip("/") + "/healthz",
                args.wait_seconds,
            )
        )
        if report["health"].get("status") != "passed" or (
            not enabled_domain_scope_selected
            and report["productOpsHealth"].get("status") != "passed"
        ):
            report["status"] = "gate_block"
        else:
            try:
                _ACTIVE_SESSION = open_local_acceptance_session(
                    args.base_url,
                    environment="gamma",
                    target_name="gamma-local",
                )
            except Exception as exc:  # noqa: BLE001
                report["auth"] = {"status": "failed", "error": type(exc).__name__}
                report["status"] = "gate_block"
                report_path = ROOT / args.report
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(f"[local-gamma:t3] report: {report_path}")
                print(f"[local-gamma:t3] status: {report['status']}")
                return 2
            report["auth"] = {"status": "passed", "principal": "seeded_persona"}
            report["seed"] = {"status": "skipped"} if args.skip_seed else seed_content()
            if report["seed"].get("status") == "failed":
                report["runtimeSetup"] = {"status": "skipped"}
                report["endpoints"] = []
            else:
                setup = setup_runtime_fixtures(args.base_url, _ACTIVE_SESSION.persona_id)
                report["runtimeSetup"] = setup
                runtime_refs = {
                    "fixture_comment_parent_001": str(setup.get("parentCommentId") or ""),
                    "fixture_comment_reply_001": str(setup.get("replyCommentId") or ""),
                    "{activePersonaId}": _ACTIVE_SESSION.persona_id,
                }
                if not args.skip_seed and "circle" in enabled_domains:
                    circle_seed = seed_circle()
                    report["domainSeeds"]["circle"] = circle_seed
                if not args.skip_seed and "chat" in enabled_domains:
                    chat_seed = seed_chat()
                    report["domainSeeds"]["chat"] = chat_seed
                if not args.skip_seed and "user" in enabled_domains:
                    report["domainSeeds"]["user"] = seed_user()
                if not args.skip_seed and "entity" in enabled_domains:
                    entity_seed = seed_entity(args.base_url)
                    report["domainSeeds"]["entity"] = entity_seed
                    if entity_seed.get("status") == "passed":
                        seeded_homepage_id = str(entity_seed.get("homepageId") or "")
                        runtime_refs["{homepageId}"] = seeded_homepage_id
                        # scope runtimeRefs 会把 {homepageId} 固定到社交图 seed 实体
                        # （如 west_lake）；introduction 断言必须打在 seed_entity 走
                        # candidate→publish 灌了 introductionMarkdown 的实体上，
                        # 使用独立占位符避免被 scope 覆盖。
                        runtime_refs["{seededHomepageId}"] = seeded_homepage_id
                report["endpoints"] = endpoint_checks(
                    manifest,
                    args.base_url,
                    enabled_domains,
                    runtime_refs,
                    scope_name=scope_name or None,
                    scope=scope,
                )
                report["strictEndpoints"] = strict_endpoint_checks(
                    args.base_url,
                    runtime_refs,
                    scope,
                )
            report["apiContracts"] = (
                [{"name": "flutter_contracts", "status": "skipped"}]
                if args.skip_flutter_contracts
                else run_flutter_contracts(
                    args.base_url,
                    args.product_ops_base_url,
                    enabled_domains,
                    include_product_ops=not enabled_domain_scope_selected,
                )
            )
            failed = any(item.get("status") == "failed" for item in report["endpoints"])
            strict_failed = any(item.get("status") == "failed" for item in report["strictEndpoints"])
            contract_failed = any(item.get("status") == "failed" for item in report["apiContracts"])
            not_ready = any(item.get("status") == "not_ready" for item in report["endpoints"])
            runtime_setup_failed = report["runtimeSetup"].get("status") == "failed"
            domain_seed_failed = any(
                seed.get("status") == "failed" for seed in report["domainSeeds"].values()
            )
            if (
                report["seed"].get("status") == "failed"
                or runtime_setup_failed
                or domain_seed_failed
                or failed
                or strict_failed
                or contract_failed
            ):
                report["status"] = "failed"
            elif args.strict_all and not_ready:
                report["status"] = "gate_block"
            else:
                report["status"] = "passed"

    report_path = ROOT / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[local-gamma:t3] report: {report_path}")
    print(f"[local-gamma:t3] status: {report['status']}")
    return 0 if report["status"] == "passed" else 2 if report["status"] == "gate_block" else 1


if __name__ == "__main__":
    raise SystemExit(main())
