#!/usr/bin/env python3
"""Run local-gamma T3 checks against the Docker mirror."""

import argparse
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "quwoquan_service/contracts/metadata/_shared/test_fixtures/app_gamma_seed_manifest.json"
METADATA_ROOT = ROOT / "quwoquan_service/contracts/metadata"
COMPOSE_FILE = ROOT / "quwoquan_service/docker-compose.gamma-local.yaml"


def http_get(url: str, timeout: int = 5) -> Tuple[int, bytes]:
    ctx = ssl._create_unverified_context()
    req = urllib.request.Request(url, headers={"X-Test-Local-Gamma": "true"})
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
    return {
        "_id": post_id,
        "authorId": post.get("authorId", ""),
        "profileSubjectId": post.get("profileSubjectId") or post.get("authorId", ""),
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


def gamma_content_fixture_spec() -> Tuple[Path, list[str]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    content_item = next(
        (item for item in manifest.get("seedRefs", []) if item.get("domain") == "content"),
        None,
    )
    if not isinstance(content_item, dict):
        raise RuntimeError("app_gamma_seed_manifest.json missing content domain entry")
    fixture_rel = str(content_item.get("fixturePath") or "").strip()
    refs = [str(ref) for ref in content_item.get("refs", []) if str(ref).strip()]
    if not fixture_rel or not refs:
        raise RuntimeError("gamma content seed manifest entry must declare fixturePath and refs")
    return METADATA_ROOT / fixture_rel, refs


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
    js_path = ROOT / "artifacts/local-gamma/seed-content.js"
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
dbh.posts.deleteMany({$or: [{_id: /^fixture_/}, {postId: /^fixture_/}]});
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


def endpoint_checks(base_url: str, enabled_domains: Set[str]) -> List[Dict[str, Any]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    checks = []  # type: List[Dict[str, Any]]
    for item in manifest.get("seedRefs", []):
        domain = item.get("domain", "")
        for path in item.get("verifiedEndpoints", []):
            check = {"domain": domain, "path": path}  # type: Dict[str, Any]
            if domain not in enabled_domains:
                check["status"] = "not_ready"
                checks.append(check)
                continue
            try:
                status, body = http_get(base_url.rstrip("/") + path, timeout=8)
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
    cases = [
        {
            "name": "content_api_contract",
            "path": "test/cloud/content/api_contract_runner.dart",
            "defines": [
                "--dart-define=API_CONTRACT_ENV=gamma",
                f"--dart-define=API_CONTRACT_BASE_URL={base_url}",
                "--dart-define=LOCAL_GAMMA_T3_SCOPE=content",
                f"--dart-define=TEST_AUTH_TOKEN={token}",
            ],
        },
        {
            "name": "chat_api_contract",
            "path": "test/cloud/chat/api_contract_runner.dart",
            "defines": [
                "--dart-define=API_CONTRACT_ENV=gamma",
                f"--dart-define=API_CONTRACT_BASE_URL={base_url}",
                f"--dart-define=TEST_AUTH_TOKEN={token}",
            ],
        },
        {
            "name": "product_ops_api_contract",
            "path": "test/cloud/ops/api_contract_runner.dart",
            "defines": [
                "--dart-define=API_CONTRACT_ENV=gamma",
                f"--dart-define=API_CONTRACT_PRODUCT_OPS_BASE_URL={product_ops_base_url}",
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
        default=os.environ.get("LOCAL_GAMMA_GATEWAY_BASE_URL", "http://127.0.0.1:18080"),
    )
    parser.add_argument(
        "--product-ops-base-url",
        default=os.environ.get("LOCAL_GAMMA_PRODUCT_OPS_BASE_URL", "http://127.0.0.1:18086"),
    )
    parser.add_argument("--report", default="artifacts/local-gamma/t3_report.json")
    parser.add_argument("--enabled-domain", action="append", default=["content", "chat"])
    parser.add_argument("--skip-seed", action="store_true")
    parser.add_argument("--skip-flutter-contracts", action="store_true")
    parser.add_argument("--test-auth-token", default="local-gamma-token")
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
        "endpoints": [],
        "apiContracts": [],
    }

    report["health"] = wait_url(args.base_url.rstrip("/") + "/healthz", args.wait_seconds)
    report["productOpsHealth"] = wait_url(
        args.product_ops_base_url.rstrip("/") + "/healthz",
        args.wait_seconds,
    )
    if report["health"].get("status") != "passed" or report["productOpsHealth"].get("status") != "passed":
        report["status"] = "gate_block"
    else:
        report["seed"] = {"status": "skipped"} if args.skip_seed else seed_content()
        report["endpoints"] = endpoint_checks(args.base_url, enabled_domains)
        report["apiContracts"] = (
            [{"name": "flutter_contracts", "status": "skipped"}]
            if args.skip_flutter_contracts
            else run_flutter_contracts(args.base_url, args.product_ops_base_url, args.test_auth_token)
        )
        failed = any(item.get("status") == "failed" for item in report["endpoints"])
        contract_failed = any(item.get("status") == "failed" for item in report["apiContracts"])
        not_ready = any(item.get("status") == "not_ready" for item in report["endpoints"])
        if report["seed"].get("status") == "failed" or failed or contract_failed:
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
