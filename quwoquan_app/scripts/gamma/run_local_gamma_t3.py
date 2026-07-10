#!/usr/bin/env python3
"""Run local-gamma T3 checks against the Docker mirror."""

import argparse
import contextlib
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
MANIFEST = ROOT / "quwoquan_service/contracts/metadata/_shared/test_fixtures/app_gamma_seed_manifest.json"
METADATA_ROOT = ROOT / "quwoquan_service/contracts/metadata"
# 统一输出根：local-gamma 辅助报告属于本地环境状态，正式运行证据由 stackctl 写入 .qwq_output/env/<env>/runs/<runId>。
LOCAL_GAMMA_ARTIFACT_ROOT = Path(
    os.environ.get(
        "LOCAL_GAMMA_ARTIFACT_ROOT",
        Path(os.environ.get("QWQ_OUTPUT_ROOT", ROOT / ".qwq_output"))
        / "env"
        / "gamma"
        / "local"
        / "gamma-local"
        / "app-artifacts",
    )
)
COMPOSE_FILE = ROOT / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
COMPOSE_PROJECT = os.environ.get("LOCAL_GAMMA_COMPOSE_PROJECT") or os.environ.get(
    "COMPOSE_PROJECT_NAME", "quwoquan_service"
)
CONTENT_SERVICE_YAML = METADATA_ROOT / "content/post/service.yaml"
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


def default_test_auth_token() -> str:
    return (
        os.environ.get("LOCAL_GAMMA_TEST_AUTH_TOKEN")
        or os.environ.get("GAMMA_TEST_AUTH_TOKEN")
        or os.environ.get("TEST_AUTH_TOKEN")
        or "local-gamma-token"
    )


def default_request_headers(viewer_user_id: Optional[str] = "fixture_user_current") -> Dict[str, str]:
    headers = {"X-Test-Local-Gamma": "true"}
    if viewer_user_id is not None and viewer_user_id.strip():
        headers["X-Client-User-Id"] = viewer_user_id.strip()
    return headers


def http_get(
    url: str,
    timeout: int = 5,
    *,
    viewer_user_id: Optional[str] = "fixture_user_current",
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[int, bytes]:
    ctx = ssl._create_unverified_context()
    # Carry the fixture viewer id so header-scoped reads (e.g. GET /v1/me,
    # 我的主页) resolve the current user. Public reads simply ignore it.
    request_headers = default_request_headers(viewer_user_id)
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
    viewer_user_id: Optional[str] = "fixture_user_current",
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[int, bytes]:
    ctx = ssl._create_unverified_context()
    request_headers = default_request_headers(viewer_user_id)
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
    doc = {
        "_id": post_id,
        "postId": post_id,
        "postRef": post_id,
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
        "coverUrl": post.get("coverUrl", ""),
        "videoUrl": post.get("videoUrl", ""),
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

    用户主页 (GET /v1/user/profile/{userId}) and 我的主页 (GET /v1/me) both read
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

    Homepage detail/bundle reads come from the homepage-state snapshot, so we
    seed through the real candidate -> publish flow (drift-proof) instead of
    writing private snapshot state directly. The published id resolves the
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
            base_url.rstrip("/") + "/v1/homepages/candidates",
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
            base_url.rstrip("/") + f"/v1/homepages/candidates/{homepage_id}:publish",
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
    js_path = ROOT / ".qwq_output/env/gamma/local/gamma-local/seed-content.js"
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
dbh.posts.deleteMany({
  $or: [
    {_id: /^fixture_/},
    {postId: /^fixture_/},
    {postRef: /^fixture_/},
    {body: "automated test fixture - safe to delete"},
  ],
});
if (docs.length > 0) dbh.posts.insertMany(docs);
printjson({insertedCount: docs.length});
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


def seed_content_social_graph() -> Dict[str, Any]:
    report_path = LOCAL_GAMMA_ARTIFACT_ROOT / "content_social_graph_seed_report.json"
    cmd = [
        "python3",
        "quwoquan_service/services/seed-box/scripts/apply_content_social_graph_seed.py",
        "--container",
        "quwoquan_service-mongodb-1",
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

    The local gamma mirror hydrates posts from Mongo, while comments live in the
    content-service process. Creating the thread via API keeps T3 aligned with
    runtime behavior instead of writing private in-process state.
    """
    try:
        status, body = http_request(
            base_url.rstrip() + "/v1/content/posts/fixture_photo_001/comments",
            method="POST",
            body={"content": "主评论示例"},
            headers={"X-Client-User-Id": "fixture_user_current"},
            timeout=8,
        )
        parent_resp = json.loads(body.decode("utf-8"))
        parent = parent_resp.get("comment") or {}
        parent_id = str(parent.get("_id") or parent.get("commentId") or "").strip()
        if not parent_id:
            return {
                "status": "failed",
                "httpStatus": status,
                "error": "CreateComment did not return parent comment id",
            }
        reply_status, reply_body = http_request(
            base_url.rstrip() + "/v1/content/posts/fixture_photo_001/comments",
            method="POST",
            body={"content": "回复示例", "replyToCommentId": parent_id},
            headers={"X-Client-User-Id": "fixture_user_commenter"},
            timeout=8,
        )
        reply_resp = json.loads(reply_body.decode("utf-8"))
        reply = reply_resp.get("comment") or {}
        reply_id = str(reply.get("_id") or reply.get("commentId") or "").strip()
        if not reply_id:
            return {
                "status": "failed",
                "httpStatus": reply_status,
                "error": "CreateComment did not return reply comment id",
            }
        return {
            "status": "passed",
            "parentCommentId": parent_id,
            "replyCommentId": reply_id,
        }
    except urllib.error.HTTPError as exc:
        return {"status": "failed", "httpStatus": exc.code, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "error": str(exc)}


def setup_runtime_fixtures(base_url: str) -> Dict[str, Any]:
    comment = setup_comment_thread(base_url)
    social_graph = seed_content_social_graph()
    status = "passed"
    if comment.get("status") == "failed" or social_graph.get("status") == "failed":
        status = "failed"
    return {
        "status": status,
        "parentCommentId": comment.get("parentCommentId", ""),
        "replyCommentId": comment.get("replyCommentId", ""),
        "commentThread": comment,
        "socialGraphSeed": social_graph,
    }


def content_route_methods() -> Dict[str, List[str]]:
    methods: Dict[str, List[str]] = {}
    current_method = ""
    for raw_line in CONTENT_SERVICE_YAML.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("- method:"):
            current_method = line.split(":", 1)[1].strip().upper()
            continue
        if current_method and line.startswith("path:"):
            path = line.split(":", 1)[1].strip()
            methods.setdefault(path, [])
            if current_method not in methods[path]:
                methods[path].append(current_method)
            current_method = ""
    return methods


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
    if path.endswith("/reaction"):
        return {"reaction": "like"}
    if path.endswith("/media:bind"):
        return {}
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
                check["status"] = "passed" if 200 <= status < 300 else "failed"
            except urllib.error.HTTPError as exc:
                check["httpStatus"] = exc.code
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


def run_flutter_contracts(base_url: str, product_ops_base_url: str, token: str) -> List[Dict[str, Any]]:
    checks = []  # type: List[Dict[str, Any]]
    flutter_base_url = flutter_contract_base_url(base_url)
    flutter_product_ops_base_url = flutter_contract_base_url(product_ops_base_url)
    cases = [
        {
            "name": "content_api_contract",
            "path": "test/api_integration/cloud/content/api_contract_runner.dart",
            "defines": [
                "--dart-define=API_CONTRACT_ENV=gamma",
                f"--dart-define=API_CONTRACT_BASE_URL={flutter_base_url}",
                "--dart-define=LOCAL_GAMMA_T3_SCOPE=content",
                "--dart-define=API_CONTRACT_ALLOW_BAD_CERT=true",
                f"--dart-define=TEST_AUTH_TOKEN={token}",
            ],
        },
        {
            "name": "chat_api_contract",
            "path": "test/api_integration/cloud/chat/api_contract_runner.dart",
            "defines": [
                "--dart-define=API_CONTRACT_ENV=gamma",
                f"--dart-define=API_CONTRACT_BASE_URL={flutter_base_url}",
                "--dart-define=API_CONTRACT_ALLOW_BAD_CERT=true",
                f"--dart-define=TEST_AUTH_TOKEN={token}",
            ],
        },
        {
            "name": "product_ops_api_contract",
            "path": "test/api_integration/cloud/ops/api_contract_runner.dart",
            "defines": [
                "--dart-define=API_CONTRACT_ENV=gamma",
                f"--dart-define=API_CONTRACT_PRODUCT_OPS_BASE_URL={flutter_product_ops_base_url}",
                "--dart-define=API_CONTRACT_ALLOW_BAD_CERT=true",
            ],
        },
    ]
    for case in cases:
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
    parser.add_argument("--report", default=str(LOCAL_GAMMA_ARTIFACT_ROOT / "t3_report.json"))
    parser.add_argument(
        "--enabled-domain",
        action="append",
        default=["content", "chat", "circle", "entity", "user"],
    )
    parser.add_argument("--skip-seed", action="store_true")
    parser.add_argument(
        "--seed-only",
        action="store_true",
        help="Only run Mongo content seed (no health wait or flutter contracts).",
    )
    parser.add_argument("--skip-flutter-contracts", action="store_true")
    parser.add_argument("--test-auth-token", default=default_test_auth_token())
    parser.add_argument("--strict-all", action="store_true")
    parser.add_argument(
        "--verification-scope",
        default="",
        help="Only strict-gate the selected manifest verification scope.",
    )
    parser.add_argument("--wait-seconds", type=int, default=45)
    args = parser.parse_args()

    enabled_domains = set(args.enabled_domain)
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
        report["status"] = "passed" if report["seed"].get("status") == "passed" else "failed"
    else:
        report["health"] = wait_url(args.base_url.rstrip("/") + "/healthz", args.wait_seconds)
        report["productOpsHealth"] = wait_url(
            args.product_ops_base_url.rstrip("/") + "/healthz",
            args.wait_seconds,
        )
        if report["health"].get("status") != "passed" or report["productOpsHealth"].get("status") != "passed":
            report["status"] = "gate_block"
        else:
            report["seed"] = {"status": "skipped"} if args.skip_seed else seed_content()
            if report["seed"].get("status") == "failed":
                report["runtimeSetup"] = {"status": "skipped"}
                report["endpoints"] = []
            else:
                setup = setup_runtime_fixtures(args.base_url)
                report["runtimeSetup"] = setup
                runtime_refs = {
                    "fixture_comment_parent_001": str(setup.get("parentCommentId") or ""),
                    "fixture_comment_reply_001": str(setup.get("replyCommentId") or ""),
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
                    args.test_auth_token,
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
