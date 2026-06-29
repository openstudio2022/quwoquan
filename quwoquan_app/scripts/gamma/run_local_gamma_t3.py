#!/usr/bin/env python3
"""Run local-gamma T3 checks against the Docker mirror."""

import argparse
import contextlib
import json
import os
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
COMPOSE_FILE = ROOT / "quwoquan_service/docker-compose.gamma-local.yaml"
CONTENT_SERVICE_YAML = METADATA_ROOT / "content/post/service.yaml"


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


def http_get(url: str, timeout: int = 5) -> Tuple[int, bytes]:
    ctx = ssl._create_unverified_context()
    # Carry the fixture viewer id so header-scoped reads (e.g. GET /v1/me,
    # 我的主页) resolve the current user. Public reads simply ignore it.
    request_headers = {
            "X-Test-Local-Gamma": "true",
            "X-Client-User-Id": "fixture_user_current",
    }
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
    request_headers = {
        "X-Test-Local-Gamma": "true",
        "X-Client-User-Id": "fixture_user_current",
    }
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
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
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


def seed_entity(base_url: str) -> Dict[str, Any]:
    """Publish an entity homepage through the runtime API and return its id.

    Homepage detail/bundle reads come from the homepage-state snapshot, so we
    seed through the real candidate -> publish flow (drift-proof) instead of
    writing private snapshot state directly. The published id resolves the
    `{homepageId}` template in the manifest verifiedEndpoints.
    """
    try:
        status, body = http_request(
            base_url.rstrip("/") + "/v1/homepages/candidates",
            method="POST",
            body={
                "title": "契约主页验证",
                "subtitle": "local-gamma T3 entity seed",
                "homepageType": "sight",
                "city": "杭州",
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
    js_path = ROOT / "state/local/gamma/seed-content.js"
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
    cmd = [
        "docker",
        "compose",
        "-f",
        str(COMPOSE_FILE),
        "exec",
        "-T",
        "mongodb",
        "mongosh",
        "--quiet",
    ]
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


def endpoint_checks(
    base_url: str,
    enabled_domains: Set[str],
    runtime_refs: Dict[str, str],
) -> List[Dict[str, Any]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    route_methods = content_route_methods()
    checks = []  # type: List[Dict[str, Any]]
    for item in manifest.get("seedRefs", []):
        domain = item.get("domain", "")
        for path in item.get("verifiedEndpoints", []):
            check = {"domain": domain, "path": path}  # type: Dict[str, Any]
            if domain not in enabled_domains:
                check["status"] = "not_ready"
                checks.append(check)
                continue
            # entity verifiedEndpoints carry a `{homepageId}` template resolved from
            # the runtime publish seed; content carries comment-id refs. Both resolve
            # via runtime_refs; circle/chat paths have no refs and pass through.
            resolved_path = resolve_probe_path(path, runtime_refs)
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


def run_flutter_contracts(base_url: str, product_ops_base_url: str, token: str) -> List[Dict[str, Any]]:
    checks = []  # type: List[Dict[str, Any]]
    flutter_base_url = flutter_contract_base_url(base_url)
    flutter_product_ops_base_url = flutter_contract_base_url(product_ops_base_url)
    cases = [
        {
            "name": "content_api_contract",
            "path": "test/cloud/content/api_contract_runner.dart",
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
            "path": "test/cloud/chat/api_contract_runner.dart",
            "defines": [
                "--dart-define=API_CONTRACT_ENV=gamma",
                f"--dart-define=API_CONTRACT_BASE_URL={flutter_base_url}",
                "--dart-define=API_CONTRACT_ALLOW_BAD_CERT=true",
                f"--dart-define=TEST_AUTH_TOKEN={token}",
            ],
        },
        {
            "name": "product_ops_api_contract",
            "path": "test/cloud/ops/api_contract_runner.dart",
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
    parser.add_argument("--report", default="artifacts/local-gamma/t3_report.json")
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
    parser.add_argument("--wait-seconds", type=int, default=45)
    args = parser.parse_args()

    enabled_domains = set(args.enabled_domain)
    report = {  # type: Dict[str, Any]
        "status": "running",
        "baseUrl": args.base_url,
        "productOpsBaseUrl": args.product_ops_base_url,
        "enabledDomains": sorted(enabled_domains),
        "health": {},
        "productOpsHealth": {},
        "seed": {},
        "domainSeeds": {},
        "runtimeSetup": {},
        "endpoints": [],
        "apiContracts": [],
    }

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
                setup = setup_comment_thread(args.base_url)
                report["runtimeSetup"] = setup
                runtime_refs = {
                    "fixture_comment_parent_001": str(setup.get("parentCommentId") or ""),
                    "fixture_comment_reply_001": str(setup.get("replyCommentId") or ""),
                }
                if not args.skip_seed and "circle" in enabled_domains:
                    circle_seed = seed_circle()
                    report["domainSeeds"]["circle"] = circle_seed
                if not args.skip_seed and "user" in enabled_domains:
                    report["domainSeeds"]["user"] = seed_user()
                if not args.skip_seed and "entity" in enabled_domains:
                    entity_seed = seed_entity(args.base_url)
                    report["domainSeeds"]["entity"] = entity_seed
                    if entity_seed.get("status") == "passed":
                        runtime_refs["{homepageId}"] = str(entity_seed.get("homepageId") or "")
                report["endpoints"] = endpoint_checks(args.base_url, enabled_domains, runtime_refs)
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
